from typing import Annotated, ClassVar, Literal, Optional

from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import StateGraph
from pydantic import Field, model_validator

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts import InMemoryPromptRegistry, LocalPromptRegistry
from duo_workflow_service.agent_platform.experimental.components.agent.nodes import (
    AgentFinalOutput,
    AgentNode,
    FinalResponseNode,
    ToolNode,
)
from duo_workflow_service.agent_platform.experimental.components.agent.ui_log import (
    UILogEventsAgent,
    UILogWriterAgentTools,
)
from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
    RouterProtocol,
)
from duo_workflow_service.agent_platform.experimental.components.registry import (
    register_component,
)
from duo_workflow_service.agent_platform.experimental.state import (
    FlowState,
    FlowStateKeys,
    IOKey,
    IOKeyTemplate,
)
from duo_workflow_service.agent_platform.experimental.ui_log import (
    UIHistory,
    default_ui_log_writer_class,
)
from duo_workflow_service.tools.toolset import Toolset
from lib.internal_events import InternalEventsClient

__all__ = ["AgentComponent", "RoutingError"]


class RoutingError(Exception):
    """Exception raised when edge routers encounter unexpected conditions."""


@register_component(decorators=[inject])
class AgentComponent(BaseComponent):
    _final_answer_key: ClassVar[IOKeyTemplate] = IOKeyTemplate(
        target="context",
        subkeys=[IOKeyTemplate.COMPONENT_NAME_TEMPLATE, "final_answer"],
    )

    _outputs: ClassVar[tuple[IOKeyTemplate, ...]] = (
        IOKeyTemplate(
            target="conversation_history",
            subkeys=[IOKeyTemplate.COMPONENT_NAME_TEMPLATE],
        ),
        IOKeyTemplate(target="status"),
        _final_answer_key,
    )

    supported_environments: ClassVar[tuple[str, ...]] = ("platform",)

    prompt_id: str
    prompt_version: Optional[str] = None
    toolset: Toolset
    tool_arguments_binding: list[IOKey] = Field(default_factory=list)

    prompt_registry: LocalPromptRegistry | InMemoryPromptRegistry = Provide[
        ContainerApplication.pkg_prompts.prompt_registry
    ]
    internal_event_client: InternalEventsClient = Provide[
        ContainerApplication.internal_event.client
    ]

    ui_log_events: list[UILogEventsAgent] = Field(default_factory=list)
    ui_role_as: Literal["agent", "tool"] = "agent"

    _allowed_input_targets = tuple(FlowState.__annotations__.keys())

    @model_validator(mode="before")
    @classmethod
    def parse_tool_arguments_binding(cls, data: dict) -> dict:
        """Parse tool_arguments_binding from configuration."""
        if "tool_arguments_binding" in data:
            data["tool_arguments_binding"] = IOKey.parse_keys(
                data["tool_arguments_binding"]
            )
        return data

    @model_validator(mode="after")
    def validate_tool_arguments_binding(self):
        """Validate that binding parameter names map to actual tool parameters.
        
        This validation ensures that bound arguments correspond to parameters
        that exist in at least one tool in the toolset.
        """
        if not self.tool_arguments_binding:
            return self

        # Collect all bound argument names using the new get_key_name() method
        bound_args = set()
        for binding in self.tool_arguments_binding:
            param_name = binding.get_key_name()
            bound_args.add(param_name)

        # Check that at least one tool accepts each bound argument
        for arg_name in bound_args:
            arg_found_in_tool = False
            for tool in self.toolset.bindable:
                if hasattr(tool, "args_schema") and tool.args_schema:
                    tool_params = tool.args_schema.model_fields.keys()
                    if arg_name in tool_params:
                        arg_found_in_tool = True
                        break
            
            if not arg_found_in_tool:
                import warnings
                warnings.warn(
                    f"Bound argument '{arg_name}' does not match any tool parameter in toolset. "
                    f"This binding will have no effect."
                )

        return self

    def _agent_node_router(self, state: FlowState) -> str:
        history: list[BaseMessage] = state[FlowStateKeys.CONVERSATION_HISTORY].get(
            self.name,
            [],
        )
        if not history:
            raise RoutingError(f"Conversation history not found for {self.name}")

        last_message = history[-1]

        if not isinstance(last_message, AIMessage):
            raise RoutingError(
                f"Last message is not AIMessage for component {self.name}"
            )

        if not last_message.tool_calls:
            raise RoutingError(f"Tool calls not found for component {self.name}")

        if any(
            tool_call["name"] == AgentFinalOutput.tool_title
            for tool_call in last_message.tool_calls
        ):
            return f"{self.name}#final_response"
        return f"{self.name}#tools"

    def __entry_hook__(self) -> Annotated[str, "Entry node name"]:
        return f"{self.name}#agent"

    def attach(self, graph: StateGraph, router: RouterProtocol) -> None:
        tools = self.toolset.bindable + [AgentFinalOutput]
        tool_choice = "any"  # make sure the LLM always uses a tool to respond.

        prompt = self.prompt_registry.get(
            self.prompt_id, self.prompt_version, tools=tools, tool_choice=tool_choice  # type: ignore[arg-type]
        )

        node_agent = AgentNode(
            name=self.__entry_hook__(),
            component_name=self.name,
            prompt=prompt,
            inputs=self.inputs,
            flow_id=self.flow_id,
            flow_type=self.flow_type,
            internal_event_client=self.internal_event_client,
        )
        node_tools = ToolNode(
            name=f"{self.name}#tools",
            component_name=self.name,
            toolset=self.toolset,
            tool_arguments_binding=self.tool_arguments_binding,
            flow_id=self.flow_id,
            flow_type=self.flow_type,
            internal_event_client=self.internal_event_client,
            ui_history=UIHistory(
                events=self.ui_log_events, writer_class=UILogWriterAgentTools
            ),
        )
        node_final_response = FinalResponseNode(
            name=f"{self.name}#final_response",
            component_name=self.name,
            output=self._final_answer_key.to_iokey(
                {IOKeyTemplate.COMPONENT_NAME_TEMPLATE: self.name}
            ),
            ui_history=UIHistory(
                events=self.ui_log_events,
                writer_class=default_ui_log_writer_class(
                    events_class=UILogEventsAgent, ui_role_as=self.ui_role_as
                ),
            ),
        )

        graph.add_node(self.__entry_hook__(), node_agent.run)
        graph.add_node(node_tools.name, node_tools.run)
        graph.add_node(node_final_response.name, node_final_response.run)

        graph.add_conditional_edges(
            node_agent.name,
            self._agent_node_router,
        )
        graph.add_edge(node_tools.name, node_agent.name)

        graph.add_conditional_edges(
            node_final_response.name,
            router.route,
        )
