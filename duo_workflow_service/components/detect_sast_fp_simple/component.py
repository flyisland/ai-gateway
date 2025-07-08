import logging
from duo_workflow_service.entities import UiChatLog, MessageTypeEnum, ToolStatus
from datetime import datetime, timezone

def attach(graph, entry_node, exit_node):
    graph.add_node(entry_node, start_fp_detect_component)
    graph.add_node(exit_node, end_fp_detect_component)
    graph.add_edge(entry_node, exit_node)
    return entry_node

async def start_fp_detect_component(state):
    log_entry = UiChatLog(
        message_type=MessageTypeEnum.TOOL,
        message_sub_type=None,
        content="Entered start_fp_detect_component node",
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.SUCCESS,
        correlation_id=None,
        tool_info=None,
        context_elements=None,
    )
    state = dict(state)
    state.setdefault("ui_chat_log", []).append(log_entry)
    return state

async def end_fp_detect_component(state):
    log_entry = UiChatLog(
        message_type=MessageTypeEnum.TOOL,
        message_sub_type=None,
        content="Entered end_fp_detect_component node",
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.SUCCESS,
        correlation_id=None,
        tool_info=None,
        context_elements=None,
    )
    state = dict(state)
    state.setdefault("ui_chat_log", []).append(log_entry)
    return state 