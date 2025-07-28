from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from dependency_injector.wiring import Provide, inject
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.output_parsers.string import StrOutputParser

from ai_gateway.container import ContainerApplication
from ai_gateway.prompts import Prompt
from duo_workflow_service.entities.state import (
    ChatWorkflowState,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
    WorkflowStatusEnum,
)
from lib.internal_events import InternalEventsClient

log = structlog.stdlib.get_logger("history_compactor")


class HistoryCompactor:
    _prompt: Prompt[ChatWorkflowState, BaseMessage]
    _agent_name: str

    @inject
    def __init__(
        self,
        agent_name: str,
        workflow_id: str,
        internal_event_client: InternalEventsClient = Provide[
            ContainerApplication.internal_event.client
        ],
    ) -> None:
        self._prompt = self.history_compactor_prompt()
        self._agent_name = agent_name
        self._workflow_id = workflow_id
        self._internal_event_client = internal_event_client
        self._logger = structlog.stdlib.get_logger("history_compactor")

    async def run(self, input: ChatWorkflowState) -> Dict[str, Any]:
        try:
            # Get the conversation history for this agent
            history: List[BaseMessage] = input["conversation_history"].get(self._agent_name, [])
            
            if not history:
                return {
                    "conversation_history": {self._agent_name: []},
                    "status": WorkflowStatusEnum.INPUT_REQUIRED,
                }
            
            # Check if we've recently compacted (look for our compacted message marker)
            has_recent_compaction = any(
                isinstance(msg, HumanMessage) and 
                msg.content and 
                ("<analysis>" in msg.content or "Generated with [Claude Code]" in msg.content)
                for msg in history[-5:]  # Check last 5 messages
            )
            
            if has_recent_compaction:
                log.info("Recent compaction detected - skipping to avoid loop")
                return {
                    "conversation_history": {self._agent_name: history},
                    "status": WorkflowStatusEnum.INPUT_REQUIRED,
                }
            
            # Separate system messages (keep at the beginning)
            system_messages = [msg for msg in history if isinstance(msg, SystemMessage)]
            non_system_messages = [msg for msg in history if not isinstance(msg, SystemMessage)]
            
            # If we have very few messages, don't compact
            if len(non_system_messages) <= 8:
                return {
                    "conversation_history": {self._agent_name: history},
                    "status": WorkflowStatusEnum.INPUT_REQUIRED,
                }
            
            # Extract recent messages (5-6 messages, ensuring tool use/result pairs stay together)
            recent_messages = self._extract_recent_messages_with_tool_pairs(non_system_messages)
            
            # Get middle messages to be compacted (everything except system and recent)
            messages_to_compact = non_system_messages[:-len(recent_messages)] if recent_messages else non_system_messages
            
            if not messages_to_compact:
                # Nothing to compact
                return {
                    "conversation_history": {self._agent_name: history},
                    "status": WorkflowStatusEnum.INPUT_REQUIRED,
                }
            
            # Create a temporary state with only the messages to be compacted for the prompt
            compact_input = input.copy()
            compact_input["conversation_history"] = {self._agent_name: messages_to_compact}
            
            # Call the prompt to get the compacted history
            agent_response = await self._prompt.ainvoke(
                input=compact_input, agent_name=self._agent_name
            )
            compacted_content = StrOutputParser().invoke(agent_response) or ""

            # Create a new message with the compacted content
            compacted_message = HumanMessage(content=compacted_content)

            from duo_workflow_service.token_counter.approximate_token_counter import (
                ApproximateTokenCounter,
            )
            token_counter = ApproximateTokenCounter(self._agent_name)
            total_tokens = token_counter.count_tokens(compacted_message)

            log.info("PARK" * 50)
            log.info(compacted_message)
            log.info(f"Post compact token count {total_tokens}")

            # Reassemble: system messages + compacted message + recent messages
            final_history = system_messages + [compacted_message] + recent_messages

            return {
                "conversation_history": {self._agent_name: final_history},
                "status": WorkflowStatusEnum.INPUT_REQUIRED,
            }

        except Exception as error:
            self._logger.warning(f"Error compacting history: {error}")

            error_message = HumanMessage(
                content=f"There was an error compacting the conversation history: {error}"
            )

            return {
                "conversation_history": {self._agent_name: [error_message]},
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

    def _extract_recent_messages_with_tool_pairs(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Extract the 5-6 most recent messages, ensuring tool use and tool result messages 
        are kept together as pairs.
        """
        if not messages:
            return []
        
        # Simple approach: take the last 6 messages but ensure tool pairs stay together
        target_count = 6
        
        if len(messages) <= target_count:
            return messages
        
        # Start with the last target_count messages
        candidate_messages = messages[-target_count:]
        
        # Check if the first message in our candidate set breaks a tool pair
        first_msg = candidate_messages[0]
        
        # If the first message is a ToolMessage, we need to include its corresponding AIMessage
        if isinstance(first_msg, ToolMessage):
            tool_call_id = getattr(first_msg, "tool_call_id", None)
            if tool_call_id:
                # Look backwards in the full message list to find the AIMessage with this tool_call_id
                start_index = len(messages) - target_count
                ai_msg_index = self._find_ai_message_with_tool_call(messages, tool_call_id, start_index - 1)
                if ai_msg_index is not None:
                    # Include messages from the AIMessage onwards
                    return messages[ai_msg_index:]
        
        # Check if we have any AIMessages with tool_calls that don't have all their ToolMessages
        for i, msg in enumerate(candidate_messages):
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_call_ids = [tc.get("id") for tc in msg.tool_calls if tc.get("id")]
                if tool_call_ids:
                    # Check if all tool_call_ids have corresponding ToolMessages in the remaining messages
                    remaining_messages = candidate_messages[i+1:]
                    found_tool_ids = set()
                    for remaining_msg in remaining_messages:
                        if isinstance(remaining_msg, ToolMessage):
                            tool_call_id = getattr(remaining_msg, "tool_call_id", None)
                            if tool_call_id in tool_call_ids:
                                found_tool_ids.add(tool_call_id)
                    
                    # If not all tool calls have results, we need to extend to include them
                    missing_tool_ids = set(tool_call_ids) - found_tool_ids
                    if missing_tool_ids:
                        # Look for the missing tool results after our candidate messages
                        extended_end = len(messages) - target_count + len(candidate_messages)
                        for j in range(extended_end, len(messages)):
                            if isinstance(messages[j], ToolMessage):
                                tool_call_id = getattr(messages[j], "tool_call_id", None)
                                if tool_call_id in missing_tool_ids:
                                    # Extend to include this message
                                    candidate_messages = messages[len(messages) - target_count:j+1]
                                    missing_tool_ids.discard(tool_call_id)
                                    if not missing_tool_ids:
                                        break
        
        return candidate_messages
    
    def _find_ai_message_with_tool_call(self, messages: List[BaseMessage], tool_call_id: str, max_index: int) -> int | None:
        """Find the AIMessage that contains the given tool_call_id, searching backwards from max_index."""
        for i in range(max_index, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    if tool_call.get("id") == tool_call_id:
                        return i
        return None
    
    def _find_last_tool_message(self, messages: List[BaseMessage], tool_call_ids: List[str], start_index: int) -> int | None:
        """Find the last ToolMessage that corresponds to any of the given tool_call_ids."""
        last_index = None
        for i in range(start_index + 1, len(messages)):
            msg = messages[i]
            if isinstance(msg, ToolMessage):
                tool_call_id = getattr(msg, "tool_call_id", None)
                if tool_call_id in tool_call_ids:
                    last_index = i
        return last_index

    def history_compactor_prompt(self):
        return """
        You are operating as an agentic coding assistant built by GitLab. You are expected to be precise, safe, and helpful.

        <role>
        Context Extraction and Technical Summarization Assistant
        </role>

        <primary_objective>
        Your task is to extract and summarize the most relevant, high-quality information from the conversation history below to preserve essential context for ongoing development. Your output will *replace* the current conversation history, so it must retain all critical information while freeing up space.
        </primary_objective>

        <objective_information>
        You are approaching the model's token limit. Your goal is to summarize older parts of the conversation, while preserving the most recent interactions in full. Additionally, you must include full file diffs, code changes, and function definitions whenever they appear, especially in the most recent messages. Avoid duplicating information.

        To aid in this, you will be provided with:
        - The user's original request
        - The full conversation history

        You must distill this into a compact, chronologically accurate summary that preserves key context, code, and intentions.
        </objective_information>

        <required_technique>
        Follow this strategy exactly:

        1. Summarize older sections, combining duplicated requests, responses, and analysis.
        2. Include full file diffs and code edits, using real file paths and code block formatting.
        3. Capture all explicit user requests, including tactical and strategic goals.
        4. Include reasoning, design decisions, and any learned context about the codebase.
        5. Do not invent or omit details. Do not summarize code—copy it fully if referenced.
        6. Include the most recent next steps, in the user's words if possible.

        </required_technique>

        <output_structure>
        Your output must include:

        1. `<analysis>`: Internal thought process ensuring you've followed the above rules.
        2. `<summary>`: Structured summary with the following fields:

            a. Primary Request and Intent:
            [User's explicit goals and motivations]

            b. Key Technical Concepts:
            - [Relevant tools, APIs, patterns, models]

            c. Files and Code Sections:
            - [Full path to relevant file]
                - [Why this file is important]
                - [Summary of edits or insights]
                - [Full code snippet or diff if referenced or modified]

            d. Problem Solving:
            [Resolved bugs, edge cases, challenges]

            e. Pending Tasks:
            - [Tasks still outstanding or awaiting clarification]

            f. Current Work:
            [Precise detail of last action taken or being discussed]
            [Include full message(s) and code if recent]

            g. Optional Next Step:
            [Only if it directly follows from current task and user request]
            - "Direct quote from user for confirmation"
        </output_structure>

        <conversation_history>
        {{conversation_history}}
        </conversation_history>

        Now, carefully read the full conversation history, then apply the summarization strategy outlined above. Respond only with the <analysis> and <summary> sections, formatted as instructed.

        """
