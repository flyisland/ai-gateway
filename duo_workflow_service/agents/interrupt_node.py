from duo_workflow_service.entities import DuoWorkflowStateType
from langgraph.types import interrupt
from duo_workflow_service.entities.state import UiChatLog
from langchain_core.messages import HumanMessage
from duo_workflow_service.entities.event import WorkflowEvent
from duo_workflow_service.entities.state import ChatFlowEventType
from duo_workflow_service.entities.state import (
    WorkflowStatusEnum,
    ApprovalStateRejection,
    MessageTypeEnum,
    ToolStatus
)
from datetime import datetime, timezone
import structlog
from typing import Any

log = structlog.stdlib.get_logger("interrupt_node")


class InterruptNode:
    _agent_name: str

    def __init__(
        self, agent_name: str
    ) -> None:
        self._agent_name = agent_name

    async def run(self, state: DuoWorkflowStateType):
        event: WorkflowEvent = interrupt("Workflow interrupted")
        state_update: dict[str, Any] = {"status": WorkflowStatusEnum.EXECUTION}
        new_message = None

        if event.get("event_type") == ChatFlowEventType.REJECT:
            new_message = event.get("message")
            state_update["approval"] = ApprovalStateRejection(
                            message=new_message
                        )
        elif event.get("event_type") == ChatFlowEventType.RESPONSE:
            conversation_history = state["conversation_history"].get(self._agent_name, [])
            new_message = event.get("message")

            updated_history = conversation_history + [HumanMessage(
                            content=event.get("message"),
                            additional_kwargs={
                                "additional_context": event.get("additional_context")
                            },
                        )]

            state_update["conversation_history"] = {
                self._agent_name: updated_history
            }

        if new_message and new_message != "null":
            new_message_chat_log = UiChatLog(
                message_type=MessageTypeEnum.USER,
                message_sub_type=None,
                content=new_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=ToolStatus.SUCCESS,
                correlation_id=None,
                tool_info=None,
                additional_context=event.get("additional_context"),
            )
            state_update["ui_chat_log"] = [new_message_chat_log]

        log.info("INTERRUPT_NODE" * 50)
        log.info(state_update)
        return state_update
