"""
Filter for removing orphaned tool use blocks from conversation history.

LLMs require each tool use block (AIMessage with tool_calls) to have a corresponding
tool result block (ToolMessage). This filter removes AIMessages with tool_calls that
don't have corresponding ToolMessages to prevent LLM errors.
"""

from typing import List
import structlog
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

log = structlog.stdlib.get_logger("tool_use_filter")


def filter_orphaned_tool_use_blocks(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Filter out AIMessages with tool_calls that don't have corresponding ToolMessages.

    This prevents LLM errors that occur when a tool use block is not followed by a
    tool result block. The function identifies orphaned tool use blocks and removes them
    from the conversation history.

    Uses an optimized approach that only checks the last tool use block to avoid
    unnecessary processing and correctly handles valid pending tool use blocks.

    Args:
        messages: List of conversation messages

    Returns:
        Filtered list of messages with orphaned tool use blocks removed
    """
    if not messages:
        return messages

    # Find the last tool use block (AIMessage with tool_calls)
    last_tool_use_index = None
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if isinstance(message, AIMessage) and hasattr(message, "tool_calls") and message.tool_calls:
            last_tool_use_index = i
            break

    if last_tool_use_index is None:
        return messages

    # If the last tool use block is the last message, it's a valid pending tool use
    if last_tool_use_index == len(messages) - 1:
        return messages

    # Get the tool_call_ids from the last tool use block
    last_tool_use_block = messages[last_tool_use_index]
    expected_tool_call_ids = {tool_call["id"] for tool_call in last_tool_use_block.tool_calls}

    # Collect all tool result blocks that follow this tool use block
    tool_result_ids = set()
    for j in range(last_tool_use_index + 1, len(messages)):
        msg = messages[j]
        if isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id and tool_call_id in expected_tool_call_ids:
                tool_result_ids.add(tool_call_id)
        elif isinstance(msg, AIMessage):
            # Stop at the next AI message
            break

    # If all tool_calls have corresponding tool result blocks, keep all messages
    if expected_tool_call_ids.issubset(tool_result_ids):
        return messages

    # The last tool use block is orphaned, remove it
    filtered_messages = messages[:last_tool_use_index] + messages[last_tool_use_index + 1:]

    log.info(
        "Filtered orphaned tool use block from conversation history",
        orphaned_count=1,
        original_count=len(messages),
        filtered_count=len(filtered_messages),
        tool_calls=[tc.get("name") for tc in messages[last_tool_use_index].tool_calls]
    )

    return filtered_messages
