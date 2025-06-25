"""
Router functions for SAST False Positive Detection Workflow.

This module contains the routing logic that determines the flow
of the SAST false positive detection workflow.
"""

from duo_workflow_service.entities import DetectSastFpWorkflowState, WorkflowStatusEnum
from duo_workflow_service.workflows.detect_sast_fp.constants import (
    AGENT_NAME,
    CREATE_FILE_TOOL,
    FIND_FILES_TOOL,
    READ_FILE_TOOL,
    Routes,
)


def router(state: DetectSastFpWorkflowState) -> str:
    """Route workflow based on agent's tool calls and workflow status."""
    if state["status"] == WorkflowStatusEnum.CANCELLED:
        return Routes.END

    agent_messages = state["conversation_history"].get(AGENT_NAME, [])
    if not agent_messages or len(agent_messages) < 2:
        return Routes.END

    tool_calls = getattr(agent_messages[-2], "tool_calls", [])
    if not tool_calls:
        return Routes.END

    tool_name = tool_calls[0].get("name")

    # If the agent created the analysis result file, workflow is complete
    if tool_name == CREATE_FILE_TOOL:
        return Routes.END

    # If the agent is reading files or finding files, continue analysis
    if tool_name in [READ_FILE_TOOL, FIND_FILES_TOOL]:
        return Routes.AGENT

    return Routes.END


def tools_execution_requested(state: DetectSastFpWorkflowState) -> str:
    """Check if the agent has requested tool execution."""
    if state["status"] == WorkflowStatusEnum.CANCELLED:
        return Routes.END

    agent_messages = state["conversation_history"].get(AGENT_NAME, [])
    if agent_messages and getattr(agent_messages[-1], "tool_calls", []):
        return Routes.CONTINUE

    return Routes.END 