from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import structlog
from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.prompt_values import ChatPromptValue, PromptValue
from langchain_core.runnables import Runnable, RunnableConfig

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts import Prompt, jinja2_formatter
from ai_gateway.prompts.config.base import PromptConfig
from duo_workflow_service.entities.state import (
    ChatWorkflowState,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from lib.internal_events import InternalEventsClient

log = structlog.stdlib.get_logger("history_compactor")


class HistoryCompactorPromptTemplate(Runnable[ChatWorkflowState, PromptValue]):
    def __init__(self, prompt_template: dict[str, str]):
        self.prompt_template = prompt_template

    def invoke(
        self,
        input: ChatWorkflowState,
        config: Optional[RunnableConfig] = None,  # pylint: disable=unused-argument
        **_kwargs: Any,
    ) -> PromptValue:
        messages: list[BaseMessage] = []

        # Get conversation history to be compacted
        conversation_history = input.get("conversation_history", [])
        
        # Convert messages to string representation for the template
        history_str = ""
        for msg in conversation_history:
            if isinstance(msg, HumanMessage):
                history_str += f"Human: {msg.content}\n\n"
            elif isinstance(msg, AIMessage):
                history_str += f"Assistant: {msg.content}\n\n"
            elif isinstance(msg, SystemMessage):
                history_str += f"System: {msg.content}\n\n"
            elif isinstance(msg, ToolMessage):
                history_str += f"Tool: {msg.content}\n\n"

        # Add system message with the compactor instructions and conversation history
        if "system" in self.prompt_template:
            system_content = jinja2_formatter(
                self.prompt_template["system"],
                conversation_history=history_str
            )
            messages.append(SystemMessage(content=system_content))

        return ChatPromptValue(messages=messages)


class HistoryCompactor(Prompt[ChatWorkflowState, BaseMessage]):
    _agent_name: str
    _compacting_from: str
    _workflow_id: str

    def __init__(self, model_factory, config, *args, **kwargs):
        # Extract our custom parameters from kwargs
        self._agent_name = kwargs.pop("agent_name", "history_compactor")
        self._compacting_from = kwargs.pop("compacting_from", "unknown")
        self._workflow_id = kwargs.pop("workflow_id", "unknown")
        self._logger = structlog.stdlib.get_logger("history_compactor")
        super().__init__(model_factory, config, *args, **kwargs)

    @classmethod
    def _build_prompt_template(cls, config: PromptConfig) -> Runnable:
        return HistoryCompactorPromptTemplate(config.prompt_template)

    async def run(self, input: ChatWorkflowState) -> Dict[str, Any]:
        try:
            self._logger.info("Starting history compaction process")

            # Step 1: Take the conversation history from the input
            history: List[BaseMessage] = input["conversation_history"].get(self._compacting_from, [])
            self._logger.info(f"Retrieved {len(history)} messages from conversation history")

            if not history:
                self._logger.info("No history found, returning empty history")
                return {
                    "conversation_history": {self._compacting_from: []},
                    "status": WorkflowStatusEnum.INPUT_REQUIRED,
                }

            # Step 2: Parse out the system messages at the beginning of the history
            system_messages = [msg for msg in history if isinstance(msg, SystemMessage)]
            non_system_messages = [msg for msg in history if not isinstance(msg, SystemMessage)]
            self._logger.info(f"Found {len(system_messages)} system messages and {len(non_system_messages)} non-system messages")

            # Step 3: Extract up to 3 most recent messages if they exist, otherwise extract whatever is available
            recent_count = min(3, len(non_system_messages))
            recent_messages = non_system_messages[-recent_count:] if recent_count > 0 else []
            self._logger.info(f"Extracted {len(recent_messages)} recent messages (up to 3)")

            # Step 4: Compact any remaining messages (only if there are messages to compact)
            messages_to_compact = non_system_messages[:-recent_count] if recent_count < len(non_system_messages) else []
            self._logger.info(f"Found {len(messages_to_compact)} messages to compact")

            if not messages_to_compact:
                self._logger.info("No messages to compact (fewer than 3 total messages), returning original history")
                return {
                    "conversation_history": {self._compacting_from: history},
                    "status": WorkflowStatusEnum.INPUT_REQUIRED,
                }

            # Create a temporary state with only the messages to be compacted for the prompt
            compact_input = input.copy()
            compact_input["conversation_history"] = messages_to_compact
            self._logger.info("Invoking agent to summarize conversation history")

            # Call the prompt to get the compacted history
            agent_response = await self.ainvoke(
                input=compact_input
            )
            compacted_content = StrOutputParser().invoke(agent_response) or ""
            self._logger.info(f"Agent summarization completed, generated {len(compacted_content)} characters")

            # Create a new message with the compacted content and add identifier
            compacted_content_with_id = f"COMPACTED_HISTORY: {compacted_content}"
            compacted_message = HumanMessage(content=compacted_content_with_id)
            self._logger.info("Created compacted message with identifier")

            # Step 5: Reform the conversation history with system_messages + summarized_message + recent_messages
            final_history = system_messages + [compacted_message] + recent_messages
            self._logger.info(f"Reassembled final history with {len(final_history)} messages total")

            return {
                "conversation_history": {self._compacting_from: final_history},
                "status": WorkflowStatusEnum.INPUT_REQUIRED,
            }

        except Exception as error:
            self._logger.warning(f"Error compacting history: {error}")

            error_message = HumanMessage(
                content=f"There was an error compacting the conversation history: {error}"
            )

            return {
                "conversation_history": {self._compacting_from: [error_message]},
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
