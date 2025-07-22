from datetime import datetime, timezone
from typing import Any, Dict, Optional
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.prompt_values import ChatPromptValue, PromptValue
from langchain_core.runnables import Runnable, RunnableConfig

import structlog
from ai_gateway.prompts import Prompt, jinja2_formatter
from ai_gateway.prompts.config.base import PromptConfig
from duo_workflow_service.entities.state import (
    ChatWorkflowState,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)

log = structlog.stdlib.get_logger("history_compactor")


class HistoryCompactorPromptTemplate(Runnable[ChatWorkflowState, PromptValue]):
    def __init__(self, prompt_template: dict[str, str]):
        self.prompt_template = prompt_template

    def invoke(
        self,
        input: ChatWorkflowState,
        config: Optional[RunnableConfig] = None,
        **_kwargs: Any,
    ) -> PromptValue:
        messages = []
        agent_name = _kwargs["agent_name"]
        conversation_history = input.get("conversation_history", {}).get(agent_name, [])
        history_text = self._format_conversation_history(conversation_history)

        if "system" in self.prompt_template:
            system_content = jinja2_formatter(
                self.prompt_template["system"],
                conversation_history=history_text
            )
            messages.append(SystemMessage(content=system_content))

        return ChatPromptValue(messages=messages)

    def _format_conversation_history(self, conversation_history: list[BaseMessage]) -> str:
        formatted_messages = []
        for msg in conversation_history:
            if hasattr(msg, 'type'):
                msg_type = msg.type
            else:
                msg_type = type(msg).__name__.lower().replace('message', '')

            content = getattr(msg, 'content', str(msg))
            formatted_messages.append(f"{msg_type}: {content}")

        return "\n\n".join(formatted_messages)


class HistoryCompactor(Prompt[ChatWorkflowState, BaseMessage]):
    @classmethod
    def _build_prompt_template(cls, config: PromptConfig) -> Runnable:
        return HistoryCompactorPromptTemplate(config.prompt_template)

    async def run(self, input: ChatWorkflowState) -> Dict[str, Any]:
        try:
            agent_response = await super().ainvoke(input=input, agent_name=self.name)
            compacted_content = StrOutputParser().invoke(agent_response) or ""

            return compacted_content

        except Exception as error:
            log.warning(f"Error compacting history: {error}")

            error_message = HumanMessage(
                content=f"There was an error compacting the conversation history: {error}"
            )

            return {
                "conversation_history": {self.name: [error_message]},
                "status": WorkflowStatusEnum.INPUT_REQUIRED,
                "ui_chat_log": [
                    UiChatLog(
                        message_type=MessageTypeEnum.AGENT,
                        message_sub_type=None,
                        content="There was an error compacting the conversation history. Please try again.",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        status=ToolStatus.FAILURE,
                        correlation_id=None,
                        tool_info=None,
                        additional_context=None,
                    )
                ],
            }
