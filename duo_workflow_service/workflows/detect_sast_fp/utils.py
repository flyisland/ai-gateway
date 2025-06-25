"""
Utility functions for SAST False Positive Detection Workflow.

This module contains utility functions used throughout the SAST workflow
for data processing, logging, and state management.
"""

from datetime import datetime, timezone
import json

from duo_workflow_service.entities import (
    MAX_CONTEXT_TOKENS,
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
)
from duo_workflow_service.token_counter.approximate_token_counter import (
    ApproximateTokenCounter,
)
from duo_workflow_service.workflows.detect_sast_fp.constants import AGENT_NAME


def extract_vulnerability_id(goal: str) -> str:
    """Extract vulnerability ID from the goal for logging purposes."""
    try:
        # The goal should be a simple vulnerability ID string
        vulnerability_id = goal.strip()
        if not vulnerability_id:
            raise ValueError("Empty vulnerability ID")
        return vulnerability_id
    except Exception:
        return "Unknown"


def create_ui_log(content: str, status: ToolStatus = ToolStatus.SUCCESS) -> UiChatLog:
    """Create a UI chat log entry with current timestamp."""
    return UiChatLog(
        message_type=MessageTypeEnum.TOOL,
        message_sub_type=None,
        content=content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=status,
        correlation_id=None,
        tool_info=None,
        context_elements=None,
    )


def prepare_agent_messages_from_details(
    vuln_details: dict,
) -> tuple[list, list[UiChatLog]]:
    """Prepare agent messages and logs for vulnerability analysis using details."""
    from duo_workflow_service.workflows.detect_sast_fp.prompts import (
        SAST_ANALYZER_FILE_USER_MESSAGE,
        SAST_ANALYZER_SYSTEM_MESSAGE,
        SAST_ANALYZER_USER_GUIDELINES,
    )
    from langchain_core.messages import HumanMessage, SystemMessage

    logs: list[UiChatLog] = []
    # Prepare messages for the agent
    human_prompt = SAST_ANALYZER_FILE_USER_MESSAGE.format(
        finding_data=json.dumps(vuln_details, indent=2),
    )
    messages = [
        SystemMessage(content=SAST_ANALYZER_SYSTEM_MESSAGE),
        HumanMessage(content=SAST_ANALYZER_USER_GUIDELINES),
        HumanMessage(content=human_prompt),
    ]
    # Check token limit
    if ApproximateTokenCounter(AGENT_NAME).count_tokens(messages) > MAX_CONTEXT_TOKENS:
        messages = []
        logs.append(
            create_ui_log(
                "Vulnerability details too large, skipping analysis.",
                status=ToolStatus.FAILURE,
            )
        )
    else:
        title = vuln_details.get("title", "Unknown")
        file_path = vuln_details.get("location", {}).get("file", "Unknown")
        line_number = vuln_details.get("location", {}).get("startLine", "Unknown")
        logs.append(
            create_ui_log(
                f"Loaded vulnerability: {title} in {file_path}:{line_number}"
            )
        )
    return messages, logs 