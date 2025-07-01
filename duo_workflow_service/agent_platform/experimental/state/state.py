from enum import StrEnum
from typing import (
    Annotated,
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    TypedDict,
    TypeVar,
    get_origin,
)

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict, model_validator

# TODO: Remove dependency on legacy duo workflow packages
from duo_workflow_service.entities.state import (
    UiChatLog,
    _conversation_history_reducer,
    _ui_chat_log_reducer,
)


class WorkflowStatusEnum(StrEnum):
    NOT_STARTED = "not_started"
    PLANNING = "planning"
    EXECUTION = "execution"
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    INPUT_REQUIRED = "input_required"
    PLAN_APPROVAL_REQUIRED = "plan_approval_required"
    TOOL_CALL_APPROVAL_REQUIRED = "tool_call_approval_required"
    APPROVAL_ERROR = "approval_error"


def merge_nested_dict(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(existing, dict):
        existing = {}
    if not isinstance(new, dict):
        return new

    result = existing.copy()

    for key, value in new.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = merge_nested_dict(result[key], value)
        else:
            # Overwrite or add new key-value pair
            result[key] = value

    return result


def create_nested_dict(keys: list[str], value: Any) -> dict[str, Any]:
    if not keys:
        return {}

    result: dict[str, Any] = {}
    current = result

    # Navigate through all keys except the last one
    for key in keys[:-1]:
        current[key] = {}
        current = current[key]

    # Set the value at the last key
    current[keys[-1]] = value

    return result


class HasBaseStateFields(TypedDict):
    status: WorkflowStatusEnum
    conversation_history: dict[str, list[BaseMessage]]
    context: dict[str, Any]
    ui_chat_log: list[UiChatLog]


T = TypeVar("T", bound=HasBaseStateFields)


class IOKey(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    target: str
    subkeys: Optional[list[str]] = None

    _target_separator: ClassVar[str] = ":"
    _key_separator: ClassVar[str] = "."

    @model_validator(mode="after")
    def parse_valid_target(self):

        allowed_targets = HasBaseStateFields.__annotations__.keys()
        if self.target not in allowed_targets:
            raise ValueError(
                f"Invalid target: {self.target} allowed targets are {allowed_targets}"
            )

        targets_with_subkeys = {
            t
            for t, a in HasBaseStateFields.__annotations__.items()
            if get_origin(a) is dict
        }

        if (
            self.target not in targets_with_subkeys
            and self.subkeys
            and len(self.subkeys) > 0
        ):
            raise ValueError(f"{self.target} does not support subkeys")

        return self

    @classmethod
    def parse_keys(cls, keys: list[str]) -> list["IOKey"]:
        return [cls.parse_key(key) for key in keys]

    @classmethod
    def parse_key(cls, key: str) -> "IOKey":
        target, _, remaining = key.partition(cls._target_separator)

        if not remaining:
            subkeys = None
        else:
            subkeys = remaining.split(cls._key_separator)

        return cls(target=target, subkeys=subkeys)

    def read_from_state(self, state: HasBaseStateFields) -> dict[str, Any]:
        current = state[self.target]  # type: ignore[literal-required]
        if self.subkeys is None or len(self.subkeys) == 0:
            return {self.target: current}

        for key in self.subkeys:  # pylint: disable=not-an-iterable
            current = current[key]

        return {self.subkeys[-1]: current}  # pylint: disable=unsubscriptable-object


def get_vars_from_state(inputs: list[IOKey], state: T) -> dict[str, Any]:
    variables: dict[str, Any] = {}

    for inp in inputs:
        variables = merge_nested_dict(variables, inp.read_from_state(state))

    return variables


def merge_nested_dict_reducer(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """Reducer specifically for nested dictionary fields."""
    return merge_nested_dict(left or {}, right or {})


class FlowState(TypedDict):
    status: WorkflowStatusEnum
    conversation_history: Annotated[
        Dict[str, List[BaseMessage]], _conversation_history_reducer
    ]
    ui_chat_log: Annotated[List[UiChatLog], _ui_chat_log_reducer]
    context: Annotated[dict[str, Any], merge_nested_dict_reducer]
