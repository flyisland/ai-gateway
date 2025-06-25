"""
Workflow nodes for SAST False Positive Detection Workflow.

This module contains the individual node functions that make up
the SAST false positive detection workflow graph.
"""

import json

from duo_workflow_service.entities import DetectSastFpWorkflowState, ToolStatus
from duo_workflow_service.workflows.detect_sast_fp.constants import (
    AGENT_NAME,
    GET_VULNERABILITY_TOOL,
)
from duo_workflow_service.workflows.detect_sast_fp.utils import (
    create_ui_log,
    prepare_agent_messages_from_details,
)


def fetch_vulnerability_details_node(tools_registry, vulnerability_id):
    """Node that deterministically fetches vulnerability details using the get_vulnerability tool."""

    async def fetch_vulnerability_details(
        state: DetectSastFpWorkflowState,
    ) -> DetectSastFpWorkflowState:
        try:
            get_vuln_tool = tools_registry.get(GET_VULNERABILITY_TOOL)
            if not get_vuln_tool:
                raise RuntimeError(
                    f"Tool {GET_VULNERABILITY_TOOL} not found in tools registry"
                )

            # Call the tool asynchronously with tool_input as a dictionary
            result = await get_vuln_tool.arun({"vulnerability_id": vulnerability_id})

            try:
                vuln_data = json.loads(result)
            except json.JSONDecodeError as e:
                vuln_data = {"error": f"Failed to parse vulnerability details: {e}"}

            # Store in state
            state = dict(state)
            state["vulnerability"] = vuln_data.get("vulnerability") or vuln_data

            # Add UI log
            if "error" in vuln_data:
                ui_log = create_ui_log(
                    f"Error fetching vulnerability details: {vuln_data['error']}",
                    status=ToolStatus.FAILURE,
                )
            else:
                ui_log = create_ui_log(
                    f"Successfully fetched vulnerability details for ID: {vulnerability_id}",
                    status=ToolStatus.SUCCESS,
                )

            state["ui_chat_log"] = state.get("ui_chat_log", []) + [ui_log]
            return state

        except Exception as e:
            # Ensure workflow continues even if there's an error
            state = dict(state)
            state["vulnerability"] = {
                "error": f"Exception during fetch: {str(e)}"
            }
            error_log = create_ui_log(
                f"Exception while fetching vulnerability details: {str(e)}",
                status=ToolStatus.FAILURE,
            )
            state["ui_chat_log"] = state.get("ui_chat_log", []) + [error_log]
            return state

    return fetch_vulnerability_details


async def prepare_agent_messages_node(
    state: DetectSastFpWorkflowState,
) -> DetectSastFpWorkflowState:
    """Node that prepares agent messages from vulnerability details."""
    vuln_details = state.get("vulnerability", {})

    # Add a log to indicate we're preparing agent messages
    state = dict(state)
    state["ui_chat_log"] = state.get("ui_chat_log", []) + [
        create_ui_log("Preparing agent messages with vulnerability details")
    ]

    try:
        messages, logs = prepare_agent_messages_from_details(vuln_details)
        state["conversation_history"] = {AGENT_NAME: messages}
        state["ui_chat_log"] = state.get("ui_chat_log", []) + logs

        # Add a log to indicate agent is about to start
        state["ui_chat_log"].append(
            create_ui_log("Agent messages prepared, starting analysis")
        )

    except Exception as e:
        # Handle any errors in message preparation
        error_log = create_ui_log(
            f"Error preparing agent messages: {str(e)}",
            status=ToolStatus.FAILURE,
        )
        state["ui_chat_log"].append(error_log)
        # Still set empty conversation history so workflow can continue
        state["conversation_history"] = {AGENT_NAME: []}

    return state 