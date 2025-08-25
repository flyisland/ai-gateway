from typing import Any, Dict, Optional, List

import structlog
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
)
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.prompt_values import ChatPromptValue, PromptValue
from langchain_core.runnables import Runnable, RunnableConfig

from ai_gateway.prompts import Prompt, jinja2_formatter
from ai_gateway.prompts.config.base import PromptConfig
from duo_workflow_service.entities.state import ChatWorkflowState

log = structlog.stdlib.get_logger("history_compactor")


class HistoryCompactorPromptTemplate(Runnable[ChatWorkflowState, PromptValue]):
    def __init__(self, agent_name: str, prompt_template: dict[str, str]):
        self.prompt_template = prompt_template
        self.agent_name = agent_name

    def invoke(
        self,
        input: ChatWorkflowState,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> PromptValue:
        # Get conversation history from kwargs (passed from compact_messages)
        conversation_history = kwargs.get("conversation_history", "")

        # Build system message with the conversation history to compact
        system_content = jinja2_formatter(
            self.prompt_template["system"],
            conversation_history=conversation_history
        )

        # Add a user message to request compression (required by Anthropic API)
        user_content = "Please provide a concise summary of the above conversation history."

        messages = [SystemMessage(content=system_content), HumanMessage(content=user_content)]
        return ChatPromptValue(messages=messages)


class HistoryCompactor(Prompt[ChatWorkflowState, BaseMessage]):
    compacting_from: Optional[Any] = None

    def __init__(self, model_factory, config, model_metadata=None, **kwargs):
        compacting_from = kwargs.pop('compacting_from', None)
        super().__init__(model_factory, config, model_metadata, **kwargs)
        self.compacting_from = compacting_from

    @classmethod
    def _build_prompt_template(cls, config: PromptConfig) -> Runnable:
        return HistoryCompactorPromptTemplate(config.name, config.prompt_template)

    def _find_last_human_message_index(self, messages: List[BaseMessage]) -> int:
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                return i
        return -1

    def _split_messages_safely(self, messages: List[BaseMessage]) -> tuple[List[BaseMessage], List[BaseMessage]]:
        # avoid compacting system messages if there are any

        # Find the last human message as a starting point
        last_human_index = self._find_last_human_message_index(messages)

        if last_human_index <= 0:
            # No human messages found or it's the first message - keep all as recent
            log.info("No human messages found or first message is human, keeping all messages as recent")
            return [], messages

        # Look backwards from the human message to find incomplete tool sequences
        safe_split_index = last_human_index

        for i in range(last_human_index - 1, -1, -1):
            if isinstance(messages[i], AIMessage) and hasattr(messages[i], 'tool_calls') and messages[i].tool_calls:
                # This AI message has tool calls - check if all are resolved
                tool_ids = {tc.get('id') for tc in messages[i].tool_calls if tc.get('id')}

                if not tool_ids:  # No valid tool IDs
                    continue

                # Look for corresponding tool responses after this message
                found_responses = set()
                for j in range(i + 1, len(messages)):
                    if isinstance(messages[j], ToolMessage) and hasattr(messages[j], 'tool_call_id'):
                        found_responses.add(messages[j].tool_call_id)

                # If not all tool calls have responses, include this sequence in recent messages
                if not tool_ids.issubset(found_responses):
                    log.info(f"Found incomplete tool sequence at index {i}, including in recent messages")
                    safe_split_index = i
                    break

        messages_to_compact = messages[:safe_split_index]
        recent_messages = messages[safe_split_index:]

        log.info(f"Safe split at index {safe_split_index}: {len(messages_to_compact)} to compact, {len(recent_messages)} recent")

        return messages_to_compact, recent_messages

    def _format_messages_for_compacting(self, messages: List[BaseMessage]) -> str:
        return "\n\n".join(message.pretty_repr() for message in messages)

    async def compact_messages(self, messages: List[BaseMessage], input: ChatWorkflowState) -> str:
        if not messages:
            return ""

        # Format messages for compacting
        conversation_history = self._format_messages_for_compacting(messages)

        # Get the compacted summary from the AI model
        response = await self.ainvoke(
            input=input,
            conversation_history=conversation_history
        )

        # Extract the text content from the response
        return StrOutputParser().invoke(response) if response else ""

    async def run(self, input: ChatWorkflowState) -> Dict[str, Any]:
        if not self.compacting_from:
            log.error("No agent specified for compacting")
            return input

        agent_name = self.compacting_from.name

        if agent_name not in input["conversation_history"]:
            log.warning(f"No conversation history found for agent: {agent_name}")
            return input

        messages = input["conversation_history"][agent_name]

        log.info(f"=== ORIGINAL MESSAGES ({len(messages)} total) ===")
        for i, msg in enumerate(messages):
            msg_type = type(msg).__name__
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_ids = [tc.get('id', 'no-id') for tc in msg.tool_calls]
                log.info(f"  {i}: {msg_type} (tool_calls: {tool_ids}) (content: {msg.content})")
            elif isinstance(msg, ToolMessage) and hasattr(msg, 'tool_call_id'):
                log.info(f"  {i}: {msg_type} (tool_call_id: {msg.tool_call_id}) (content: {msg.content})")
            else:
                log.info(f"  {i}: {msg_type} (content: {msg.content})")

        messages_to_compact, recent_messages = self._split_messages_safely(messages)

        if not messages_to_compact:
            return input

        try:
            new_messages = []

            compacted_summary = await self.compact_messages(messages_to_compact, input)
            if compacted_summary:
                new_messages.append(
                    AIMessage(content=f"[COMPACTED HISTORY]\n{compacted_summary}")
                )

            new_messages.extend(recent_messages)

            log.info(f"=== FINAL MESSAGES ({len(new_messages)} total) ===")
            for i, msg in enumerate(new_messages):
                msg_type = type(msg).__name__
                if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                    tool_ids = [tc.get('id', 'no-id') for tc in msg.tool_calls]
                    log.info(f"  {i}: {msg_type} (tool_calls: {tool_ids})(content: {msg.content})")
                elif isinstance(msg, ToolMessage) and hasattr(msg, 'tool_call_id'):
                    log.info(f"  {i}: {msg_type} (tool_call_id: {msg.tool_call_id})(content: {msg.content})")
                else:
                    log.info(f"  {i}: {msg_type}(content: {msg.content})")

            return {
                "conversation_history": {agent_name: new_messages},
            }

        except Exception as error:
            log.error(f"Error compacting history for agent '{agent_name}': {error}")
            # Return original input if compacting fails
            return input

