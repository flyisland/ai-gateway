from typing import ClassVar, Literal

from dependency_injector.wiring import Provide, inject
from langgraph.graph import StateGraph
from pydantic import Field

from ai_gateway.container import ContainerApplication
from duo_workflow_service.agent_platform.experimental.components import (
    register_component,
)
from duo_workflow_service.agent_platform.experimental.components.base import (
    BaseComponent,
    RouterProtocol,
)
from duo_workflow_service.agent_platform.experimental.components.deterministic_step.nodes import (
    DeterministicStepNode,
)
from duo_workflow_service.agent_platform.experimental.components.deterministic_step.ui_log import (
    UILogEventsDeterministicStep,
    UILogWriterDeterministicStep,
)
from duo_workflow_service.agent_platform.experimental.state import IOKeyTemplate
from duo_workflow_service.agent_platform.experimental.ui_log import UIHistory
from duo_workflow_service.tools.toolset import Toolset

__all__ = ["DeterministicStepComponent"]

from lib.internal_events import InternalEventsClient


@register_component(decorators=[inject])
class DeterministicStepComponent(BaseComponent):
    _tool_responses_key: ClassVar[IOKeyTemplate] = IOKeyTemplate(
        target="context",
        subkeys=[IOKeyTemplate.COMPONENT_NAME_TEMPLATE, "tool_responses"],
    )
    _tool_error_key: ClassVar[IOKeyTemplate] = IOKeyTemplate(
        target="context",
        subkeys=[IOKeyTemplate.COMPONENT_NAME_TEMPLATE, "error"],
    )

    _execution_result_key: ClassVar[IOKeyTemplate] = IOKeyTemplate(
        target="context",
        subkeys=[IOKeyTemplate.COMPONENT_NAME_TEMPLATE, "execution_result"],
    )

    _outputs: ClassVar[tuple[IOKeyTemplate, ...]] = (
        IOKeyTemplate(target="ui_chat_log"),
        _tool_responses_key,
        _tool_error_key,
        _execution_result_key,
    )

    internal_event_client: InternalEventsClient = Provide[
        ContainerApplication.internal_event.client
    ]

    tool_name: str
    toolset: Toolset

    _allowed_input_targets: ClassVar[tuple[str, ...]] = (
        "context",
        "conversation_history",
    )

    ui_log_events: list[UILogEventsDeterministicStep] = Field(default_factory=list)
    ui_role_as: Literal["tool"] = "tool"

    def __entry_hook__(self) -> str:
        return f"{self.name}#deterministic_step"

    def attach(self, graph: StateGraph, router: RouterProtocol) -> None:
        node = DeterministicStepNode(
            name=self.__entry_hook__(),
            tool_name=self.tool_name,
            component_name=self.name,
            inputs=self.inputs,
            toolset=self.toolset,
            flow_id=self.flow_id,
            flow_type=self.flow_type,
            internal_event_client=self.internal_event_client,
            ui_history=UIHistory(
                events=self.ui_log_events, writer_class=UILogWriterDeterministicStep
            ),
            tool_responses_key=self._tool_responses_key.to_iokey(
                {IOKeyTemplate.COMPONENT_NAME_TEMPLATE: self.name}
            ),
            tool_error_key=self._tool_error_key.to_iokey(
                {IOKeyTemplate.COMPONENT_NAME_TEMPLATE: self.name}
            ),
            execution_result_key=self._execution_result_key.to_iokey(
                {IOKeyTemplate.COMPONENT_NAME_TEMPLATE: self.name}
            ),
        )

        graph.add_node(self.__entry_hook__(), node.run)
        graph.add_conditional_edges(self.__entry_hook__(), router.route)
