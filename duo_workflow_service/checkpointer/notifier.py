import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Union

from langchain.load.dump import dumps
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers.string import StrOutputParser

from contract import contract_pb2
from duo_workflow_service.checkpointer.gitlab_workflow import (
    WORKFLOW_STATUS_TO_CHECKPOINT_STATUS,
)
from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    UiChatLog,
    WorkflowStatusEnum,
)


class UserInterface:
    def __init__(
        self,
        outbox: asyncio.Queue,
        goal: str,
    ):
        self.outbox = outbox
        self.goal = goal
        self.ui_chat_log: list[UiChatLog] = []
        self.status = WorkflowStatusEnum.NOT_STARTED
        self.steps: list[dict] = []

    async def send_event(
        self,
        type: str,
        state: Union[dict, tuple[BaseMessage, dict]],
        stream: bool,
    ):
        if type == "values" and isinstance(state, dict):
            self.status = state["status"]
            self.steps = state.get("plan", {}).get("steps", [])

            new_ui_chat_log = deepcopy(state["ui_chat_log"])
            diff = [item | { "id": i } for i, item in enumerate(new_ui_chat_log) if item not in self.ui_chat_log]
            self.ui_chat_log = new_ui_chat_log

            return await self._execute_action(diff)

        if not stream:
            return

        if type == "messages":
            (message, _) = state
            content = StrOutputParser().invoke(message) or ""

            if not content:
                return

            return await self._execute_action([
                { "message_type": "agent_delta", "content": content, "id": len(self.ui_chat_log) }
            ])

    async def _execute_action(self, content):
        action = contract_pb2.Action(
            uiUpdate=contract_pb2.UiUpdate(
                status=WORKFLOW_STATUS_TO_CHECKPOINT_STATUS[self.status],
                chat_log_delta=dumps(content),
            ),
        )

        return await self.outbox.put(action)
