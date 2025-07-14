import structlog
from duo_workflow_service.agent_platform.experimental.components import BaseComponent, RouterProtocol


from duo_workflow_service.agent_platform.experimental.state import FlowState, FlowStateKeys, IOKey, get_vars_from_state, create_nested_dict
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field, ConfigDict

from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, ToolCall
from langchain_core.output_parsers import PydanticToolsParser, StrOutputParser
from langchain_core.tools import BaseTool
from langgraph.constants import END
from langgraph.graph import StateGraph
from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import ValidationError

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts import LocalPromptRegistry, Prompt


from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    NamedTuple,
    Optional,
    Protocol,
    Self,
    Type,
    TypedDict,
)

from duo_workflow_service.entities.state import WorkflowStatusEnum
from duo_workflow_service.security.prompt_security import PromptSecurity, SecurityException
from duo_workflow_service.token_counter.approximate_token_counter import ApproximateTokenCounter
from duo_workflow_service.tools.toolset import Toolset
from duo_workflow_service.monitoring import duo_workflow_metrics
from lib.internal_events.event_enum import EventEnum, EventPropertyEnum
from lib.internal_events import InternalEventAdditionalProperties, InternalEventsClient
from lib.internal_events.event_enum import CategoryEnum, EventEnum, EventLabelEnum
from anthropic import APIStatusError
from duo_workflow_service.errors.error_handler import ModelError, ModelErrorHandler

InjectedValue = None


__all__ = ["AgentComponent", "EndComponent"]

class EndComponent(BaseComponent):
    def __entry_hook__(self):
        return END #"terminate_graph"
    
    def attach(self, graph: StateGraph, router: RouterProtocol) -> None:
        graph.add_node(self.__entry_hook__(), self._terminate_flow)
        graph.add_edge(self.__entry_hook__(), END)
    
    async def _terminate_flow(self, state: FlowState) -> dict:
        return { FlowStateKeys.STATUS.value: WorkflowStatusEnum.COMPLETED.value } # WorkflowStatusEnum

class AgentFinalOutput(BaseModel):
    """A final response to the user."""

    final_response: str = Field(
        description="The final response to the user to comunicate work completion"
    )

    tool_title: ClassVar[str] = "final_response_tool"

    model_config = ConfigDict(title="final_response_tool", frozen=True)


class AgentNode:
    name: str
    _prompt: Prompt

    _inputs: list[IOKey]

    _component_name: str

    _internal_event_client: InternalEventsClient
    _approximate_token_counter: ApproximateTokenCounter

    _flow_id: str
    _flow_type: CategoryEnum
    _error_handler: ModelErrorHandler


    def __init__(
        self,
        flow_id: str,
        flow_type: CategoryEnum,
        name: str,
        prompt: Prompt,
        inputs: list[IOKey],
        component_name: str,
        internal_event_client: InternalEventsClient,
    ):
        self._flow_id = flow_id
        self._flow_type = flow_type
        self.name = name
        self._prompt = prompt
        self._inputs = inputs
        self._component_name = component_name
        self._internal_event_client = internal_event_client
        self._approximate_token_counter = ApproximateTokenCounter(component_name)
        self._error_handler = ModelErrorHandler()

    async def run(self, state: FlowState) -> dict:
        history = state[FlowStateKeys.CONVERSATION_HISTORY.value].get(self._component_name, [])

        variables = get_vars_from_state(self._inputs, state)
        model_name = getattr(self._prompt.model, "model_name", "unknown")
        request_type = f"{self._component_name}_completion"

        while True:
            try:
                with duo_workflow_metrics.time_llm_request(
                    model=model_name, request_type=request_type
                ):
                    completion: AIMessage = await self._prompt.ainvoke(
                        input={**variables, "history": history}
                    )

                self._track_tokens_data(completion, history)
                duo_workflow_metrics.count_llm_response(
                    model=model_name,
                    request_type=request_type,
                    stop_reason=(
                        completion.response_metadata.get("stop_reason")
                        if completion.response_metadata
                        else None
                    ),
                )

                return {
                    FlowStateKeys.CONVERSATION_HISTORY.value: {self._component_name: [completion]},
                }
            except APIStatusError as e:
                error_message = str(e)
                status_code = e.response.status_code
                model_error = ModelError(
                    error_type=self._error_handler.get_error_type(status_code),
                    status_code=status_code,
                    message=error_message,
                )

                await self._error_handler.handle_error(model_error)
    
    
    def _track_tokens_data(self, message, history):
        estimated = self._approximate_token_counter.count_tokens(history)
        usage_metadata = message.usage_metadata if message.usage_metadata else {}

        additional_properties = InternalEventAdditionalProperties(
            label=self._component_name,
            property=EventPropertyEnum.WORKFLOW_ID.value,
            value=self._flow_id,
            input_tokens=usage_metadata.get("input_tokens"),
            output_tokens=usage_metadata.get("output_tokens"),
            total_tokens=usage_metadata.get("total_tokens"),
            estimated_input_tokens=estimated,
        )
        self._internal_event_client.track_event(
            event_name=EventEnum.TOKEN_PER_USER_PROMPT.value,
            additional_properties=additional_properties,
            category=self._flow_type
        )

class FinalResponseNode:
    name: str
    _component_name: str
    _output: Optional[IOKey]

    def __init__(self, component_name: str, name: str, output: Optional[IOKey]):
        self._component_name = component_name
        self.name = name
        self._output = output

    async def run(self, state: FlowState) -> dict:
        last_message = state[FlowStateKeys.CONVERSATION_HISTORY.value].get(self._component_name, [])[-1]

        final_response: ToolCall = next(
            (
                tool_call
                for tool_call in last_message.tool_calls
                if tool_call["name"] == AgentFinalOutput.tool_title
            ),
            None
        )

        parsed_response = AgentFinalOutput(**final_response["args"])

        updates = {
            FlowStateKeys.CONVERSATION_HISTORY.value: {self._component_name: [ToolMessage(content="", tool_call_id=final_response['id'])]},
        }

        if self._output:
            updates[self._output.target] = create_nested_dict(
                self._output.subkeys, parsed_response.final_response
            )
        
        return updates

class ReflexionNode:
    name: str
    _NEXT_STEP_PROMPT =  f"What is the next task? Call the `{AgentFinalOutput.tool_title}` tool if your task is complete"
    _component_name: str

    def __init__(self, component_name: str, name: str):
        self._component_name = component_name
        self.name = name

    async def run(self, _state: FlowState) -> dict:
        return {
            FlowStateKeys.CONVERSATION_HISTORY.value: {self._component_name: [HumanMessage(content=self._NEXT_STEP_PROMPT)]},
        }

class ToolNode:
    name: str
    _component_name: str
    _toolset: Toolset
    _flow_id: str
    _flow_type: CategoryEnum
    _internal_event_client: InternalEventsClient
    _logger: structlog.stdlib.BoundLogger

    def __init__(
            self, 
            name: str, 
            component_name: str, 
            toolset: Toolset,
            flow_id: str,
            flow_type: CategoryEnum,
            internal_event_client: InternalEventsClient,
        ):
        self.name = name
        self._component_name = component_name
        self._toolset = toolset
        self._flow_id = flow_id
        self._flow_type = flow_type
        self._internal_event_client = internal_event_client
        self._logger = structlog.stdlib.get_logger("agent_platform")
        

    async def run(self, state: FlowState) -> dict:
        conversation_history = state[FlowStateKeys.CONVERSATION_HISTORY].get(
            self._component_name, []
        )

        # TODO: add ability to register all tool calls in a follow up 
        # context = state["context"].get(self.component_name, {})
        # context.setdefault("tool_calls", [])

        last_message = conversation_history[-1]
        tool_calls = getattr(last_message, "tool_calls", [])
        tools_responses = []

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_call_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id")

            if tool_name not in self._toolset:
                response = "Tool {tool_name} not found"
            else:
                response = await self._execute_tool(
                    tool=self._toolset[tool_name],
                    tool_call_args=tool_call_args 
                )

            tools_responses.append(
                ToolMessage(
                    content=self._sanitize_response(
                        response=response, 
                        tool_name=tool_name
                    ), 
                    tool_call_id=tool_call_id
                )
            )

        return {
            FlowStateKeys.CONVERSATION_HISTORY.value: {
                self._component_name: tools_responses,
            },
        }

    async def _execute_tool(
        self, tool_call_args: dict[str, Any], tool: BaseTool
    ) -> ToolMessage:
        try:
            with duo_workflow_metrics.time_tool_call(tool_name=tool.name):
                tool_call_result = await tool.arun(tool_call_args)
            
            self._track_internal_event(
                event_name=EventEnum.WORKFLOW_TOOL_SUCCESS,
                tool_name=tool.name,
            )

            return tool_call_result
        except TypeError as e:
            return self._format_type_error_response(tool=tool, error=e)
        except ValidationError as e:
            return self._format_validation_error(tool_name=tool.name, error=e)
        except Exception as e:
            return self._format_execution_error(tool_name=tool.name, error=e)

    def _sanitize_response(self, response: str, tool_name: str) -> str:
        try:
            return PromptSecurity.apply_security(
                response=response, tool_name=tool_name
            )
        except SecurityException as e:
            self._logger.error(
                f"Security validation failed for tool {tool_name}: {e}"
            )
            raise

    def _track_internal_event(
        self,
        event_name: EventEnum,
        tool_name,
        extra=None,
    ):
        if extra is None:
            extra = {}
        additional_properties = InternalEventAdditionalProperties(
            label=EventLabelEnum.WORKFLOW_TOOL_CALL_LABEL.value,
            property=tool_name,
            value=self._flow_id,
            **extra,
        )
        self._internal_event_client.track_event(
            event_name=event_name.value,
            additional_properties=additional_properties,
            category=self._flow_type,
        )

    def _format_type_error_response(
        self,
        tool: BaseTool,
        error: TypeError
    ) -> str:
        schema = (
            f"The schema is: {tool.args_schema.model_json_schema()}"
            if tool.args_schema
            else "The tool does not accept any argument"
        )

        response = (
            f"Tool {tool.name} execution failed due to wrong arguments."
            f" You must adhere to the tool args schema! {schema}"
        )

        self._track_internal_event(
            event_name=EventEnum.WORKFLOW_TOOL_FAILURE,
            tool_name=tool.name,
            extra={"error": str(error)},
        )

        return response

    def _format_validation_error(
        self,
        tool_name: str,
        error: ValidationError,
    ) -> str:
        self._track_internal_event(
            event_name=EventEnum.WORKFLOW_TOOL_FAILURE,
            tool_name=tool_name,
            extra={"error": str(error)},
        )
        return f"Tool {tool_name} raised validation error {str(error)}"

    def _format_execution_error(
        self,
        tool_name: str,
        error: Exception,
    ) -> str:
        self._track_internal_event(
            event_name=EventEnum.WORKFLOW_TOOL_FAILURE,
            tool_name=tool_name,
            extra={"error": str(error)},
        )

        return f"Tool runtime exception due to {str(error)}"

class AgentComponent(BaseComponent):
    prompt_id: str
    prompt_version: str
    toolset: Toolset

    prompt_registry: LocalPromptRegistry
    internal_event_client: InternalEventsClient

    _allowed_input_targets = tuple(FlowState.__annotations__.keys())
    _allowed_output_targets = tuple(FlowState.__annotations__.keys())

    @inject
    def __init__(
        self,
        name: str,
        flow_id: str,
        flow_type: CategoryEnum,
        inputs: list[IOKey],
        prompt_id: str,
        prompt_version: str,
        toolset: Toolset,
        output: Optional[IOKey] = None,
        prompt_registry: LocalPromptRegistry = Provide[
            ContainerApplication.pkg_prompts.prompt_registry
        ],
        internal_event_client: InternalEventsClient = Provide[
            ContainerApplication.internal_event.client
        ],
        **kwargs
    ):
        super().__init__(
            name=name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=inputs,
            output=output,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            toolset=toolset,
            prompt_registry=prompt_registry,
            internal_event_client=internal_event_client,
            **kwargs
        )


    def _agent_node_router(
        self, state: FlowState
    ) -> str:
        history: list[BaseMessage] = state[FlowStateKeys.CONVERSATION_HISTORY.value][self.name]
        last_message = history[-1]
        if isinstance(last_message, AIMessage) and len(last_message.tool_calls) > 0:
            if any(
                tool_call["name"] == AgentFinalOutput.tool_title
                for tool_call in last_message.tool_calls
            ):
                return f"{self.name}#final_response"
            return f"{self.name}#tools"
        
        return f"{self.name}#reflexion"

    def __entry_hook__(self) -> Annotated[str, "Entry node name"]:
        return f"{self.name}#agent"

    def attach(
        self, graph: StateGraph, router: RouterProtocol
    ) -> None:
        tools = self.toolset.bindable
        tools += [AgentFinalOutput]
        tool_choice = "any"  # make sure the LLM always uses a tool to respond.

        prompt = self.prompt_registry.get(
            self.prompt_id, self.prompt_version, tools=tools, tool_choice=tool_choice
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
            flow_id=self.flow_id,
            flow_type=self.flow_type,
            internal_event_client=self.internal_event_client,
        )
        node_final_response = FinalResponseNode(
            name=f"{self.name}#final_response",
            component_name=self.name,
            output=self.output,
        )
        node_reflexion = ReflexionNode(
            name=f"{self.name}#reflexion",
            component_name=self.name,
        )


        graph.add_node(self.__entry_hook__(), node_agent.run)
        graph.add_node(node_tools.name, node_tools.run)
        graph.add_node(node_final_response.name, node_final_response.run)
        graph.add_node(node_reflexion.name, node_reflexion.run)

        graph.add_conditional_edges(
            node_agent.name,
            self._agent_node_router,
        )
        graph.add_edge(node_tools.name, node_agent.name)
        graph.add_edge(node_reflexion.name, node_agent.name)

        graph.add_conditional_edges(
            node_final_response.name,
            router.route,
        )
