from typing import Annotated, ClassVar, Optional

from dependency_injector.wiring import Provide, inject
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from pydantic import Field

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts import LocalPromptRegistry
from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
    RouterProtocol,
)
from duo_workflow_service.agent_platform.experimental.components.human_input.ui_log import (
    UILogEventsHumanInput,
    UILogWriterHumanInput,
)
from duo_workflow_service.agent_platform.experimental.components.registry import (
    register_component,
)
from duo_workflow_service.agent_platform.experimental.state import (
    FlowState,
    FlowStateKeys,
    IOKeyTemplate,
)
from duo_workflow_service.agent_platform.experimental.ui_log import UIHistory
from duo_workflow_service.entities.event import WorkflowEvent, WorkflowEventType
from duo_workflow_service.entities.state import WorkflowStatusEnum
from lib.internal_events import InternalEventsClient

__all__ = ["HumanInputComponent"]


@register_component(decorators=[inject])
class HumanInputComponent(BaseComponent):
    _responds_to_component: ClassVar[IOKeyTemplate] = IOKeyTemplate(
        target="conversation_history",
        subkeys=[IOKeyTemplate.RESPOND_TO_COMPONENT_NAME_TEMPLATE],
    )

    _outputs: ClassVar[tuple[IOKeyTemplate, ...]] = (
        IOKeyTemplate(target="status"),
        _responds_to_component,
    )

    supported_environments: ClassVar[tuple[str, ...]] = ("platform",)

    responds_to: str
    prompt_id: Optional[str] = None
    prompt_version: Optional[str] = None

    prompt_registry: LocalPromptRegistry = Provide[
        ContainerApplication.pkg_prompts.prompt_registry
    ]
    internal_event_client: InternalEventsClient = Provide[
        ContainerApplication.internal_event.client
    ]

    ui_log_events: list[UILogEventsHumanInput] = Field(default_factory=list)

    _allowed_input_targets = tuple(FlowState.__annotations__.keys())

    def __entry_hook__(self) -> Annotated[str, "Components entry node name"]:
        return f"{self.name}#request"

    def attach(self, graph: StateGraph, router: RouterProtocol) -> None:
        # Add the request node (initiates user input request)
        graph.add_node(f"{self.name}#request", self._request_user_input)
        
        # Add the fetch node (waits for and processes user input)
        graph.add_node(f"{self.name}#fetch", self._fetch_user_input)

        # Connect request -> fetch
        graph.add_edge(f"{self.name}#request", f"{self.name}#fetch")

        # Connect fetch to router for next step
        graph.add_conditional_edges(
            f"{self.name}#fetch",
            router.route,
        )

    async def _request_user_input(self, state: FlowState) -> dict:
        """Request user input and transition to INPUT_REQUIRED status."""
        ui_history = UIHistory(
            events=self.ui_log_events, writer_class=UILogWriterHumanInput
        )

        # Emit user input prompt if configured
        if (
            UILogEventsHumanInput.ON_USER_INPUT_PROMPT in self.ui_log_events
            and self.prompt_id
            and self.prompt_version
        ):
            prompt_content = self._get_prompt_content()
            ui_history.log.success(
                prompt_content,
                event=UILogEventsHumanInput.ON_USER_INPUT_PROMPT,
            )

        # Update status to INPUT_REQUIRED and emit UI logs
        update = {FlowStateKeys.STATUS: WorkflowStatusEnum.INPUT_REQUIRED.value}
        update.update(ui_history.pop_state_updates())

        return update

    async def _fetch_user_input(self, state: FlowState) -> dict:
        """Fetch user input via interrupt and write to conversation history."""
        event: WorkflowEvent = interrupt("Workflow interrupted; waiting for user input.")

        # Handle different event types
        if event["event_type"] == WorkflowEventType.STOP:
            return {FlowStateKeys.STATUS: WorkflowStatusEnum.CANCELLED.value}

        if event["event_type"] == WorkflowEventType.RESUME:
            return {FlowStateKeys.STATUS: WorkflowStatusEnum.EXECUTION.value}

        if event["event_type"] == WorkflowEventType.MESSAGE:
            message = event.get("message", "")
            
            # Create UI log for received input if configured
            ui_history = UIHistory(
                events=self.ui_log_events, writer_class=UILogWriterHumanInput
            )
            
            if UILogEventsHumanInput.ON_USER_INPUT_RECEIVED in self.ui_log_events:
                ui_history.log.success(
                    f"Received user input: {message}",
                    event=UILogEventsHumanInput.ON_USER_INPUT_RECEIVED,
                    correlation_id=event.get("correlation_id"),
                )

            # Create HumanMessage and write to conversation history
            human_message = HumanMessage(content=message)
            
            # Use IOKeyTemplate replacement to get the correct output key
            replacements = {
                IOKeyTemplate.RESPOND_TO_COMPONENT_NAME_TEMPLATE: self.responds_to
            }
            output_key = self._responds_to_component.to_iokey(replacements)
            
            update = {
                FlowStateKeys.STATUS: WorkflowStatusEnum.EXECUTION.value,
                output_key.target: {
                    output_key.subkeys[0]: [human_message]  # type: ignore[index]
                }
            }
            update.update(ui_history.pop_state_updates())
            
            return update

        # Default case - return to INPUT_REQUIRED if unknown event type
        return {FlowStateKeys.STATUS: WorkflowStatusEnum.INPUT_REQUIRED.value}

    def _get_prompt_content(self) -> str:
        """Get prompt content from the prompt registry."""
        if not self.prompt_id or not self.prompt_version:
            return "Please provide your input:"
        
        try:
            prompt = self.prompt_registry.get(self.prompt_id, self.prompt_version)
            # Extract the human-readable content from the prompt
            if hasattr(prompt, 'messages') and prompt.messages:
                # Find the first human or system message for display
                for message in prompt.messages:
                    if hasattr(message, 'content') and message.content:
                        return str(message.content)
            elif hasattr(prompt, 'template'):
                return str(prompt.template)
            return "Please provide your input:"
        except Exception:
            return "Please provide your input:"

    @property
    def outputs(self) -> tuple:
        """Override outputs to include RESPOND_TO_COMPONENT_NAME_TEMPLATE replacement."""
        replacements = {
            IOKeyTemplate.COMPONENT_NAME_TEMPLATE: self.name,
            IOKeyTemplate.RESPOND_TO_COMPONENT_NAME_TEMPLATE: self.responds_to,
        }
        return tuple(output.to_iokey(replacements) for output in self._outputs)