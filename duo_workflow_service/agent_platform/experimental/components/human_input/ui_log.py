from datetime import datetime, timezone
from enum import auto
from typing import Optional

from duo_workflow_service.agent_platform.experimental.ui_log import (
    BaseUILogEvents,
    BaseUILogWriter,
)
from duo_workflow_service.entities import (
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
)

__all__ = [
    "UILogEventsHumanInput",
    "UILogWriterHumanInput",
]


class UILogEventsHumanInput(BaseUILogEvents):
    ON_USER_INPUT_PROMPT = auto()
    ON_USER_INPUT_RECEIVED = auto()


class UILogWriterHumanInput(BaseUILogWriter):
    @property
    def events_type(self) -> type[UILogEventsHumanInput]:
        return UILogEventsHumanInput

    def _log_success(
        self,
        message: str,
        **kwargs,
    ) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.REQUEST,
            content=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=None,
            additional_context=kwargs.get("additional_context", []),
            message_sub_type=None,
        )

    def _log_error(
        self,
        message: str,
        **kwargs,
    ) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.REQUEST,
            content=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.FAILURE,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=None,
            additional_context=kwargs.get("additional_context", []),
            message_sub_type=None,
        )

    def _log_warning(
        self,
        message: str,
        **kwargs,
    ) -> UiChatLog:
        return UiChatLog(
            message_type=MessageTypeEnum.REQUEST,
            content=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=kwargs.get("correlation_id"),
            tool_info=None,
            additional_context=kwargs.get("additional_context", []),
            message_sub_type=None,
        )