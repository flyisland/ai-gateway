from enum import StrEnum
from typing import (
    Annotated,
    Any,
    ClassVar,
    Final,
    Literal,
    NotRequired,
    Optional,
    Self,
    TypedDict,
    get_args,
    get_origin,
)

import structlog
from langchain_core.messages import BaseMessage, SystemMessage, trim_messages
from pydantic import BaseModel, ConfigDict, Field, model_validator

# TODO: Remove dependency on legacy duo workflow packages
from duo_workflow_service.entities.state import (
    MAX_CONTEXT_TOKENS,
    UiChatLog,
    WorkflowStatusEnum,
    _conversation_history_reducer,
    _deduplicate_additional_context,
    _pretrim_large_messages,
    _restore_message_consistency,
    _ui_chat_log_reducer,
    get_messages_profile,
)
from duo_workflow_service.token_counter.approximate_token_counter import (
    ApproximateTokenCounter,
)

logger = structlog.stdlib.get_logger("experimental_state")

__all__ = [
    "FlowEvent",
    "FlowEventType",
    "FlowState",
    "FlowStateKeys",
    "merge_nested_dict",
    "create_nested_dict",
    "merge_nested_dict_reducer",
    "IOKey",
    "IOKeyTemplate",
    "get_vars_from_state",
    "_conversation_history_replace_reducer",
]


class FlowEventType(StrEnum):
    RESPONSE = "response"
    APPROVE = "approve"
    REJECT = "reject"


class FlowEvent(TypedDict):
    event_type: FlowEventType
    message: NotRequired[str]


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


def merge_nested_dict_reducer(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """Reducer specifically for nested dictionary fields."""
    return merge_nested_dict(left or {}, right or {})


def _conversation_history_replace_reducer(
    current: dict[str, list[BaseMessage]], new: Optional[dict[str, list[BaseMessage]]]
) -> dict[str, list[BaseMessage]]:
    """Replace-based conversation history reducer for experimental flows.

    Unlike the append-based reducer in v1, this reducer replaces conversation history
    per component rather than automatically appending. This enables components to
    implement context management strategies such as summarization, compression, or
    selective message retention. Components must explicitly include existing messages
    in their return value to preserve conversation history.

    Args:
        current: Current conversation history state mapping component names to message lists
        new: New conversation history updates from component execution

    Returns:
        Updated conversation history with per-component replacements applied
    """
    reduced = {**current}

    if new is None:
        return reduced

    for agent_name, new_messages in new.items():
        if not new_messages:
            continue

        token_counter = ApproximateTokenCounter(agent_name)

        # Log incoming message profile
        new_msg_roles, new_msg_token = get_messages_profile(
            messages=new_messages,
            token_counter=token_counter,
            include_tool_tokens=False,
        )

        logger.info(
            f"Replace reducer processing {agent_name} with "
            f"new messages roles: {new_msg_roles}, token size: {new_msg_token}; "
            f"total token size including tool specs: {new_msg_token + token_counter.tool_tokens}",
            new_msg_token=new_msg_token,
            total_tokens_before_trimming=new_msg_token + token_counter.tool_tokens,
        )

        # Pre-trim large individual messages
        processed_messages = _pretrim_large_messages(new_messages, token_counter)

        if not processed_messages:
            continue

        # Replace strategy: overwrites existing messages for this component
        reduced[agent_name] = processed_messages

        pretrimmed_msg_roles, pretrimmed_msg_token = get_messages_profile(
            messages=reduced[agent_name],
            token_counter=token_counter,
            include_tool_tokens=False,
        )

        logger.info(
            f"Finished pretrim with messages roles: {pretrimmed_msg_roles}, message token: {pretrimmed_msg_token}, "
            f"estimated token size including tool specs: {pretrimmed_msg_token + token_counter.tool_tokens}",
            total_tokens_after_pretrimming=pretrimmed_msg_token
            + token_counter.tool_tokens,
        )

        # Deduplicate additional context
        deduplicated_messages = _deduplicate_additional_context(reduced[agent_name])

        try:
            # Trim to fit within token limits
            trimmed_messages = trim_messages(
                deduplicated_messages,
                max_tokens=MAX_CONTEXT_TOKENS,
                strategy="last",
                token_counter=token_counter.count_tokens,
                start_on="human",
                include_system=True,
                allow_partial=False,
            )

            reduced[agent_name] = _restore_message_consistency(trimmed_messages)

            # Fallback if trimming resulted in empty or invalid messages
            if not reduced[agent_name] or len(reduced[agent_name]) == 1:
                system_messages = [
                    msg for msg in new_messages if isinstance(msg, SystemMessage)
                ]
                non_system_messages = [
                    msg for msg in new_messages if not isinstance(msg, SystemMessage)
                ]

                min_non_system = min(3, len(non_system_messages))
                fallback_messages = (
                    system_messages + non_system_messages[-min_non_system:]
                )

                reduced[agent_name] = _restore_message_consistency(fallback_messages)

                logger.warning(
                    "Trim resulted in empty messages/invalid messages - falling back to minimal context",
                    agent_name=agent_name,
                )

        except Exception as e:
            logger.error(
                f"Error during message trimming: {str(e)}",
                agent_name=agent_name,
                exc_info=True,
            )
            # Fallback: keep system messages plus recent messages
            system_messages = [
                msg for msg in new_messages if isinstance(msg, SystemMessage)
            ]
            non_system_messages = [
                msg for msg in new_messages if not isinstance(msg, SystemMessage)
            ]

            fallback_messages = system_messages + non_system_messages[-5:]
            reduced[agent_name] = _restore_message_consistency(fallback_messages)

        posttrimmed_msg_roles, posttrimmed_msg_token = get_messages_profile(
            messages=reduced[agent_name],
            token_counter=token_counter,
            include_tool_tokens=False,
        )

        logger.info(
            f"Finished posttrim with messages roles: {posttrimmed_msg_roles}, message token: {posttrimmed_msg_token}, "
            f"estimated token size including tool specs: {posttrimmed_msg_token + token_counter.tool_tokens}",
            total_tokens_before_trimming=new_msg_token + token_counter.tool_tokens,
            total_tokens_after_posttrimming=posttrimmed_msg_token
            + token_counter.tool_tokens,
        )

    return reduced


class FlowStateKeys:
    STATUS: Literal["status"] = "status"
    CONVERSATION_HISTORY: Literal["conversation_history"] = "conversation_history"
    UI_CHAT_LOG: Final[str] = "ui_chat_log"
    CONTEXT: Final[str] = "context"


class FlowState(TypedDict):
    status: WorkflowStatusEnum
    conversation_history: Annotated[
        dict[str, list[BaseMessage]], _conversation_history_replace_reducer
    ]
    ui_chat_log: Annotated[list[UiChatLog], _ui_chat_log_reducer]
    context: Annotated[dict[str, Any], merge_nested_dict_reducer]


class IOKey(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    target: str
    subkeys: Optional[list[str]] = None
    alias: Optional[str] = None
    literal: Optional[bool] = False

    _target_separator: ClassVar[str] = ":"
    _key_separator: ClassVar[str] = "."

    class _AliasedIOKeyConfig(BaseModel):
        from_: str = Field(alias="from")
        as_: Optional[str] = Field(default=None, alias="as")
        literal_: Optional[bool] = Field(default=False, alias="literal")

    @model_validator(mode="after")
    def parse_valid_target(self) -> Self:
        if self.literal:
            if not self.alias or self.alias.strip() == "":
                raise ValueError("Field 'as' is required when using 'literal: true'")
        else:
            allowed_targets = FlowState.__annotations__.keys()
            if self.target not in allowed_targets:
                raise ValueError(
                    f"Invalid target: {self.target} allowed targets are {allowed_targets}"
                )

            targets_with_subkeys: set[str] = set([])

            for attribute, annotation in FlowState.__annotations__.items():
                annotation_type = get_origin(annotation)

                if annotation_type is None:
                    continue

                if annotation_type is dict:
                    targets_with_subkeys.add(attribute)
                elif (
                    annotation_type is Annotated
                    and get_origin(get_args(annotation)[0]) is dict
                ):
                    targets_with_subkeys.add(attribute)

            if self.target not in targets_with_subkeys and self.subkeys:
                raise ValueError(f"{self.target} does not support subkeys")

        return self

    @classmethod
    def parse_keys(cls, keys: list[str | dict]) -> list[Self]:
        return [cls.parse_key(key) for key in keys]

    @classmethod
    def parse_key(cls, key: str | dict) -> Self:
        alias: Optional[str] = None
        literal: Optional[bool] = False

        if isinstance(key, dict):
            key_config = cls._AliasedIOKeyConfig(**key)
            key = key_config.from_
            alias = key_config.as_
            literal = key_config.literal_

        subkeys = None
        if literal:
            target = key
        else:
            target, _, remaining = key.partition(cls._target_separator)

            if remaining:
                subkeys = remaining.split(cls._key_separator)

        return cls(target=target, subkeys=subkeys, alias=alias, literal=literal)

    def template_variable_from_state(self, state: FlowState) -> dict[str, Any]:
        # self.target presence in state is validated in parse_valid_target
        # thereby state[self.target] will always succeed
        if self.literal:
            return {self.alias: self.target}  # type: ignore[dict-item]

        value = self.value_from_state(state)
        if self.alias:
            return {self.alias: value}

        if not self.subkeys:
            return {self.target: value}

        return {self.subkeys[-1]: value}  # pylint: disable=unsubscriptable-object

    def value_from_state(self, state: FlowState) -> Any:
        # self.target presence in state is validated in parse_valid_target
        # thereby state[self.target] will always succeed
        current = state[self.target]  # type: ignore[literal-required]
        if self.subkeys:
            for key in self.subkeys:  # pylint: disable=not-an-iterable
                current = current[key]
        return current

    def to_nested_dict(self, value: Any) -> dict[str, Any]:
        """Generate nested dictionary matching target and subkeys list, with value supplied as argument.

        Args:
            value: The value to be placed at the nested location

        Returns:
            A nested dictionary with the structure matching target and subkeys

        Examples:
            IOKey(target="context", subkeys=["project", "name"]).to_nested_dict("test")
            # Returns: {"context": {"project": {"name": "test"}}}

            IOKey(target="status").to_nested_dict("active")
            # Returns: {"status": "active"}
        """
        if self.subkeys:
            # Create nested structure: target -> subkeys -> value
            keys = [self.target] + self.subkeys
        else:
            # Simple structure: target -> value
            keys = [self.target]

        return create_nested_dict(keys, value)


class IOKeyTemplate(IOKey):
    COMPONENT_NAME_TEMPLATE: ClassVar[str] = "<name>"
    SENDS_RESPONSE_TO_COMPONENT_NAME_TEMPLATE: ClassVar[str] = (
        "<sends_response_to_component>"
    )

    def to_iokey(self, replacements: dict[str, str]) -> IOKey:
        return IOKey(target=self.target, subkeys=self._resolved_subkeys(replacements))

    def _resolved_subkeys(self, replacements: dict[str, str]) -> list[str] | None:
        if not self.subkeys:
            return None

        return [
            replacements.get(subkey, subkey)
            for subkey in self.subkeys  # pylint: disable=not-an-iterable
        ]


def get_vars_from_state(inputs: list[IOKey], state: FlowState) -> dict[str, Any]:
    variables: dict[str, Any] = {}

    for inp in inputs:
        variables = merge_nested_dict(
            variables, inp.template_variable_from_state(state)
        )

    return variables
