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
    _compacting_from: str

    @inject
    def __init__(
        self,
        agent_name: str,
        compacting_from: str,
        workflow_id: str,
        internal_event_client: InternalEventsClient = Provide[
            ContainerApplication.internal_event.client
        ],
    ) -> None:
        self._prompt = self.history_compactor_prompt()
        self._agent_name = agent_name
        self._compacting_from = compacting_from
        self._workflow_id = workflow_id
        self._internal_event_client = internal_event_client
        self._logger = structlog.stdlib.get_logger("history_compactor")

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
            compact_input["conversation_history"] = {self._compacting_from: messages_to_compact}
            self._logger.info("Invoking agent to summarize conversation history")

            # Call the prompt to get the compacted history
            agent_response = await self._prompt.ainvoke(
                input=compact_input, agent_name=self._agent_name
            )
            compacted_content = StrOutputParser().invoke(agent_response) or ""
            self._logger.info(f"Agent summarization completed, generated {len(compacted_content)} characters")

            # Create a new message with the compacted content
            compacted_message = HumanMessage(content=compacted_content)
            self._logger.info("Created compacted message")

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
