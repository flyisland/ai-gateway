from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import structlog
from langgraph.types import StateSnapshot

from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    TaskStatus,
    ToolStatus,
    UiChatLog,
    WorkflowState,
)
from lib.internal_events.event_enum import CategoryEnum

FINISHED_STATUSES = [TaskStatus.COMPLETED, TaskStatus.CANCELLED]


class PlanTerminatorAgent:
    _workflow_id: str
    _workflow_type: Optional[str]

    def __init__(self, workflow_id: str, workflow_type: Optional[str] = None):
        self._workflow_id = workflow_id
        self._workflow_type = workflow_type
        self.log = structlog.stdlib.get_logger("workflow").bind(workflow_id=workflow_id)

    async def run(self, state: Union[StateSnapshot, WorkflowState]) -> Dict[str, Any]:
        state_dict = state.values if isinstance(state, StateSnapshot) else state

        if state_dict.get("plan") is None or "steps" not in state_dict["plan"]:
            return {"plan": {"steps": []}}

        needs_updates = any(
            step["status"] not in FINISHED_STATUSES
            for step in state_dict["plan"]["steps"]
        )

        if not needs_updates:
            return {"plan": state_dict.get("plan", {})}

        updated_steps = []
        for step in state_dict["plan"]["steps"]:
            step_copy = step.copy()
            if step_copy["status"] not in FINISHED_STATUSES:
                step_copy["status"] = TaskStatus.CANCELLED
            updated_steps.append(step_copy)

        message = "Your request was valid but Workflow failed to complete it. Please try again."

        self.log.info(f"PlanTerminator: {message}")

        result = {"plan": {"steps": updated_steps}}
        
        # Don't add workflow_end message for issue-to-MR workflows
        if self._workflow_type != CategoryEnum.WORKFLOW_ISSUE_TO_MERGE_REQUEST:
            result["ui_chat_log"] = [
                UiChatLog(
                    message_type=MessageTypeEnum.WORKFLOW_END,
                    message_sub_type=None,
                    content=message,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    status=ToolStatus.FAILURE,
                    correlation_id=None,
                    tool_info=None,
                    additional_context=None,
                )
            ]

        return result
