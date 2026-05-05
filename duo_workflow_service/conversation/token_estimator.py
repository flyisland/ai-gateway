from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.utils import count_tokens_approximately


def _estimate_arbitrary_messages(messages: list[BaseMessage]) -> int:
    """Estimate token count for a list of messages.

    Uses actual token counts from AIMessage usage_metadata when available,
    and approximates tokens for other messages using the token counter.

    Args:
        messages: List of messages to estimate tokens for

    Returns:
        Estimated total token count for all messages
    """
    true_tokens = 0
    messages_to_estimate = []

    for msg in messages:
        if (
            isinstance(msg, AIMessage)
            and msg.usage_metadata
            and msg.usage_metadata.get("output_tokens", 0) != 0
        ):
            true_tokens += msg.usage_metadata.get("output_tokens", 0)
        else:
            messages_to_estimate.append(msg)

    return true_tokens + count_tokens_approximately(messages=messages_to_estimate)


def _estimate_complete_history(messages: list[BaseMessage]) -> int:
    """Estimate total token count for complete message history.

    Uses the most recent AIMessage's usage_metadata as a base (if available)
    and counts tokens for trailing messages. Falls back to counting all
    messages if no usage metadata is found.

    Args:
        messages: List of messages to estimate tokens for

    Returns:
        Estimated total token count for the message history
    """
    if not messages:
        return 0

    base_token = 0
    latest_ai_msg_index = 0

    for index, msg in enumerate(reversed(messages)):
        if isinstance(msg, AIMessage) and msg.usage_metadata:
            total_tokens = msg.usage_metadata.get("total_tokens", 0)
            if total_tokens > 0:
                base_token = total_tokens
                latest_ai_msg_index = index
                break

    if base_token == 0:
        return count_tokens_approximately(messages=messages)

    if latest_ai_msg_index == 0:
        return base_token

    trailing_messages = messages[-latest_ai_msg_index:]
    return base_token + count_tokens_approximately(messages=trailing_messages)


def count_tokens(messages: list[BaseMessage], *, is_complete_history: bool) -> int:
    """Estimate the total token count for a list of messages.

    Delegates to _estimate_complete_history when the messages represent the
    full conversation history (leveraging cumulative usage_metadata), or to
    _estimate_arbitrary_messages for an arbitrary subset.

    Args:
        messages: List of messages to estimate tokens for.
        is_complete_history: If True, treat messages as the complete
            conversation history and use cumulative token metadata when
            available. If False, estimate each message independently.

    Returns:
        Estimated total token count.
    """
    return (
        _estimate_complete_history(messages=messages)
        if is_complete_history
        else _estimate_arbitrary_messages(messages=messages)
    )
