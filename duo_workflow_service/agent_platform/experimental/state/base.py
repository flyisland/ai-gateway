from enum import StrEnum
from typing import NotRequired, TypedDict

from duo_workflow_service.agent_platform.v1.state.base import (
    BaseIOKey,
    FlowState,
    FlowStateKeys,
    IOKey,
    IOKeyFactory,
    IOKeyTemplate,
    RuntimeIOKey,
    conversation_history_replace_reducer,
    create_nested_dict,
    get_vars_from_state,
    merge_nested_dict,
    merge_nested_dict_reducer,
)

__all__ = [
    "FlowEvent",
    "FlowEventType",
    "FlowState",
    "FlowStateKeys",
    "merge_nested_dict",
    "create_nested_dict",
    "merge_nested_dict_reducer",
    "BaseIOKey",
    "IOKey",
    "IOKeyTemplate",
    "IOKeyFactory",
    "RuntimeIOKey",
    "get_vars_from_state",
    "conversation_history_replace_reducer",
]


class FlowEventType(StrEnum):
    RESPONSE = "response"
    APPROVE = "approve"
    REJECT = "reject"


class FlowEvent(TypedDict):
    event_type: FlowEventType
    message: NotRequired[str]
