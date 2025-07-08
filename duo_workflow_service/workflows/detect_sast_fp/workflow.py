"""
SAST False Positive Detection Workflow.

This module implements a workflow for analyzing Static Application Security Testing (SAST)
findings to determine whether they represent legitimate security vulnerabilities or false positives.

The workflow uses an AI agent to:
1. Parse vulnerability ID from input
2. Fetch vulnerability details using get_vulnerability tool
3. Analyze the code context around reported vulnerabilities
4. Examine security controls and mitigations
5. Evaluate exploitability and risk
6. Generate a detailed analysis report

The agent has access to tools for fetching vulnerability details, reading source code files,
finding related files, and creating analysis result files.
"""

from datetime import datetime, timezone
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import BaseCheckpointSaver
from duo_workflow_service.workflows.abstract_workflow import AbstractWorkflow
from duo_workflow_service.components import ToolsRegistry
from duo_workflow_service.entities import WorkflowStatusEnum, UiChatLog, MessageTypeEnum, ToolStatus

from duo_workflow_service.components.detect_sast_fp_simple import start_fp_detect_component, end_fp_detect_component, attach as detect_sast_fp_attach

class Workflow(AbstractWorkflow):
    """SAST False Positive Detection Workflow.

    This workflow analyzes SAST findings to determine if they are legitimate
    security vulnerabilities or false positives. It uses an AI agent to examine
    the code context and provide detailed analysis.

    The workflow takes a vulnerability ID as input and fetches the vulnerability
    details using the get_vulnerability tool before proceeding with analysis.
    """

    async def _handle_workflow_failure(
        self, error: Exception, compiled_graph, graph_config
    ):
        """Handle workflow failures by logging the exception."""
        pass

    def _recursion_limit(self):
        """Return the maximum recursion limit for this workflow."""
        return 100 # Default recursion limit, as the original RECURSION_LIMIT was removed

    def _compile(self, goal: str, tools_registry: ToolsRegistry, checkpointer: BaseCheckpointSaver):
        graph = StateGraph(dict)
        graph.add_node("start_detect_fp", self._start_detect_fp)
        # Attach the component between start_detect_fp and end_detect_fp_component
        detect_sast_fp_attach(graph, "component_entry", "component_exit")
        graph.add_node("end_detect_fp", self._end_detect_fp)
        graph.set_entry_point("start_detect_fp")
        graph.add_edge("start_detect_fp", "component_entry")
        graph.add_edge("component_exit", "end_detect_fp")
        graph.add_edge("end_detect_fp", END)
        return graph.compile(checkpointer=checkpointer)

    async def _start_detect_fp(self, state):
        log_entry = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content="Entered start_detect_fp node",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )
        state = dict(state)
        state.setdefault("ui_chat_log", []).append(log_entry)
        return state

    async def _end_detect_fp(self, state):
        log_entry = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content="Entered end_detect_fp node",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )
        state = dict(state)
        state.setdefault("ui_chat_log", []).append(log_entry)
        return state

    def _setup_workflow_graph(
        self,
        graph: StateGraph,
        tools_registry: ToolsRegistry,
        goal: str,
    ):
        # This method is no longer used as the workflow graph is simplified
        # and the agent logic is moved directly into the graph nodes.
        # Keeping it for now as it might be re-introduced or refactored later.
        pass

    def get_workflow_state(self, goal: str):
        """Create the initial workflow state with the starting log message."""
        initial_log = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content=f"Starting detect_sast_fp workflow with goal: {goal}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )
        return {
            "status": WorkflowStatusEnum.NOT_STARTED,
            "goal": goal,
            "ui_chat_log": [initial_log],
        }
