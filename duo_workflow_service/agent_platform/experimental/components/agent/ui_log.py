# Re-export UILogEventsAgent and UILogWriterAgentTools from v1
# to prevent code duplication. The experimental implementation has been promoted to v1.
from enum import auto

from duo_workflow_service.agent_platform.v1.components.agent.ui_log import (  # noqa: F401
    UILogWriterAgentTools as V1UILogWriterAgentTools,
)

__all__ = [
    "UILogEventsAgent",
    "UILogWriterAgentTools",
]

from duo_workflow_service.agent_platform.v1.ui_log import BaseUILogEvents


class UILogEventsAgent(BaseUILogEvents):
    """Overwrite experimental events to include new tool approval request event."""

    ON_AGENT_FINAL_ANSWER = auto()
    ON_TOOL_EXECUTION_SUCCESS = auto()
    ON_TOOL_EXECUTION_FAILED = auto()
    ON_TOOL_APPROVAL_REQUEST = auto()


class UILogWriterAgentTools(V1UILogWriterAgentTools):
    """Override to use experimental UILogEventsAgent."""

    @property
    def events_type(self) -> type[UILogEventsAgent]:  # type: ignore[override]
        return UILogEventsAgent
