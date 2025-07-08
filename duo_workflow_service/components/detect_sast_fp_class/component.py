import logging
from duo_workflow_service.entities import UiChatLog, MessageTypeEnum, ToolStatus
from datetime import datetime, timezone

class DetectSastFpComponent:
    def __init__(self, entry_node="class_component_entry", exit_node="class_component_exit"):
        self.entry_node = entry_node
        self.exit_node = exit_node

    def attach(self, graph):
        graph.add_node(self.entry_node, self.start)
        graph.add_node(self.exit_node, self.end)
        graph.add_edge(self.entry_node, self.exit_node)
        return self.entry_node

    async def start(self, state):
        log_entry = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content="Entered DetectSastFpComponent.start node",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )
        state = dict(state)
        state.setdefault("ui_chat_log", []).append(log_entry)
        return state

    async def end(self, state):
        log_entry = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content="Entered DetectSastFpComponent.end node",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )
        state = dict(state)
        state.setdefault("ui_chat_log", []).append(log_entry)
        return state 