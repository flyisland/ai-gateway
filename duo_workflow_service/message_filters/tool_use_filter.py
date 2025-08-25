"""
Filter for removing orphaned tool_use blocks from conversation history.

LLMs require each tool_use block (AIMessage with tool_calls) to have a corresponding 
tool_result block (ToolMessage). This filter removes AIMessages with tool_calls that 
don't have corresponding ToolMessages to prevent LLM errors.
"""

from typing import List
import structlog
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

log = structlog.stdlib.get_logger("tool_use_filter")


def filter_orphaned_tool_use_blocks(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Filter out AIMessages with tool_calls that don't have corresponding ToolMessages.
    
    This prevents LLM errors that occur when a tool_use block is not followed by a 
    tool_result block. The function identifies orphaned tool_use blocks and removes them
    from the conversation history.
    
    Uses an optimized approach that only checks the last tool request to avoid
    unnecessary processing and correctly handles valid pending tool requests.
    
    Args:
        messages: List of conversation messages
        
    Returns:
        Filtered list of messages with orphaned tool_use blocks removed
    """
    if not messages:
        return messages
    
    # Find the last tool request (AIMessage with tool_calls)
    last_tool_request_index = None
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if isinstance(message, AIMessage) and hasattr(message, "tool_calls") and message.tool_calls:
            last_tool_request_index = i
            break
    
    # If no tool requests found, return messages as-is
    if last_tool_request_index is None:
        return messages
    
    # If the last tool request is the last message, it's a valid pending request
    if last_tool_request_index == len(messages) - 1:
        return messages
    
    # Get the tool_call_ids from the last tool request
    last_tool_request = messages[last_tool_request_index]
    expected_tool_call_ids = {tool_call["id"] for tool_call in last_tool_request.tool_calls}
    
    # If no valid tool_call_ids, the request is orphaned
    if not expected_tool_call_ids:
        filtered_messages = messages[:last_tool_request_index] + messages[last_tool_request_index + 1:]
        log.info(
            "Filtered orphaned tool_use block from conversation history (no tool_call_ids)",
            orphaned_count=1,
            original_count=len(messages),
            filtered_count=len(filtered_messages),
            tool_calls=[tc.get("name") for tc in last_tool_request.tool_calls]
        )
        return filtered_messages
    
    # Collect all tool responses that follow this tool request
    tool_responses = set()
    for j in range(last_tool_request_index + 1, len(messages)):
        msg = messages[j]
        if isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id and tool_call_id in expected_tool_call_ids:
                tool_responses.add(tool_call_id)
        elif isinstance(msg, AIMessage):
            # Stop at the next AI message
            break
    
    # If all tool_calls have responses, keep all messages
    if expected_tool_call_ids.issubset(tool_responses):
        return messages
    
    # The last tool request is orphaned, remove it
    filtered_messages = messages[:last_tool_request_index] + messages[last_tool_request_index + 1:]
    
    log.info(
        "Filtered orphaned tool_use block from conversation history",
        orphaned_count=1,
        original_count=len(messages),
        filtered_count=len(filtered_messages),
        tool_calls=[tc.get("name") for tc in messages[last_tool_request_index].tool_calls]
    )
    
    return filtered_messages


def apply_tool_use_filter_to_conversation_history(
    conversation_history: dict[str, List[BaseMessage]]
) -> dict[str, List[BaseMessage]]:
    """
    Apply tool_use filtering to all agents in conversation history.
    
    Args:
        conversation_history: Dictionary mapping agent names to their message lists
        
    Returns:
        Filtered conversation history with orphaned tool_use blocks removed
    """
    filtered_history = {}
    
    for agent_name, messages in conversation_history.items():
        filtered_messages = filter_orphaned_tool_use_blocks(messages)
        filtered_history[agent_name] = filtered_messages
    
    return filtered_history