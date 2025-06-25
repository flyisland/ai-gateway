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

from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from duo_workflow_service.agents import Agent, HandoverAgent, ToolsExecutor
from duo_workflow_service.components import ToolsRegistry
from duo_workflow_service.entities import (
    MessageTypeEnum,
    Plan,
    ToolStatus,
    UiChatLog,
    DetectSastFpWorkflowState,
    WorkflowStatusEnum,
)
from duo_workflow_service.internal_events.event_enum import CategoryEnum
from duo_workflow_service.llm_factory import create_chat_model
from duo_workflow_service.tracking import log_exception
from duo_workflow_service.workflows.abstract_workflow import (
    MAX_TOKENS_TO_SAMPLE,
    RECURSION_LIMIT,
    AbstractWorkflow,
)
from duo_workflow_service.workflows.detect_sast_fp.constants import (
    AGENT_NAME,
    ANALYSIS_TOOLS,
    Routes,
)
from duo_workflow_service.workflows.detect_sast_fp.nodes import (
    fetch_vulnerability_details_node,
    prepare_agent_messages_node,
)
from duo_workflow_service.workflows.detect_sast_fp.routers import (
    router,
    tools_execution_requested,
)
from duo_workflow_service.workflows.detect_sast_fp.utils import (
    create_ui_log,
    extract_vulnerability_id,
)


class Workflow(AbstractWorkflow):
    """SAST False Positive Detection Workflow.

    This workflow analyzes SAST findings to determine if they are legitimate
    security vulnerabilities or false positives. It uses an AI agent to examine
    the code context and provide detailed analysis.

    The workflow takes a vulnerability ID as input and fetches the vulnerability
    details using the get_vulnerability tool before proceeding with analysis.
    """

    async def _handle_workflow_failure(
        self, error: BaseException, compiled_graph: Any, graph_config: Any
    ):
        """Handle workflow failures by logging the exception."""
        log_exception(error, extra={"workflow_id": self._workflow_id})

    def _recursion_limit(self):
        """Return the maximum recursion limit for this workflow."""
        return RECURSION_LIMIT

    def _compile(
        self,
        goal: str,
        tools_registry: ToolsRegistry,
        checkpointer: BaseCheckpointSaver,
    ):
        """Compile the workflow graph."""
        graph = StateGraph(DetectSastFpWorkflowState)
        graph = self._setup_workflow_graph(graph, tools_registry, goal)
        return graph.compile(checkpointer=checkpointer)

    def _setup_analyzer_nodes(self, tools_registry: ToolsRegistry):
        """Setup the SAST analyzer agent and tools."""
        agents_toolset = tools_registry.toolset(ANALYSIS_TOOLS)
        analyzer_agent = Agent(
            goal="N/A",
            system_prompt="N/A",
            name=AGENT_NAME,
            model=create_chat_model(
                max_tokens=MAX_TOKENS_TO_SAMPLE,
                config=self._model_config,
            ),
            toolset=agents_toolset,
            http_client=self._http_client,
            workflow_id=self._workflow_id,
            workflow_type=CategoryEnum.WORKFLOW_DETECT_SAST_FP,
        )

        return {
            "agent": analyzer_agent,
            "tools": ANALYSIS_TOOLS,
            "tools_executor": ToolsExecutor(
                tools_agent_name=AGENT_NAME,
                toolset=agents_toolset,
                workflow_id=self._workflow_id,
                workflow_type=CategoryEnum.WORKFLOW_DETECT_SAST_FP,
            ),
            "start_node": "request_analysis",
        }

    def _setup_workflow_graph(
        self,
        graph: StateGraph,
        tools_registry: ToolsRegistry,
        goal: str,
    ):
        analyzer_components = self._setup_analyzer_nodes(tools_registry)
        self.log.info("Starting %s workflow graph compilation", self._workflow_type)
        graph.set_entry_point("fetch_vulnerability_details")

        # Deterministic node to fetch vulnerability details
        fetch_vuln_details_node = fetch_vulnerability_details_node(
            tools_registry, extract_vulnerability_id(goal)
        )

        # Add all nodes to the graph
        graph.add_node("fetch_vulnerability_details", fetch_vuln_details_node)
        graph.add_node("prepare_agent_messages", prepare_agent_messages_node)
        graph.add_node(
            analyzer_components["start_node"], analyzer_components["agent"].run
        )
        graph.add_node("execution_tools", analyzer_components["tools_executor"].run)
        graph.add_node(
            "complete",
            HandoverAgent(
                new_status=WorkflowStatusEnum.COMPLETED, handover_from=AGENT_NAME
            ).run,
        )

        # Add edges to connect the workflow
        graph.add_edge("fetch_vulnerability_details", "prepare_agent_messages")
        graph.add_edge("prepare_agent_messages", analyzer_components["start_node"])
        graph.add_conditional_edges(
            analyzer_components["start_node"],
            tools_execution_requested,
            {
                Routes.CONTINUE: "execution_tools",
                Routes.END: "complete",
            },
        )
        graph.add_conditional_edges(
            "execution_tools",
            router,
            {
                Routes.AGENT: analyzer_components["start_node"],
                Routes.END: "complete",
            },
        )
        graph.add_edge("complete", END)
        return graph

    def get_workflow_state(self, goal: str) -> DetectSastFpWorkflowState:
        """Create the initial workflow state with the starting log message."""
        vulnerability_id = extract_vulnerability_id(goal)

        initial_ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content=f"Starting SAST false positive detection workflow for vulnerability ID: {vulnerability_id}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )

        return DetectSastFpWorkflowState(
            status=WorkflowStatusEnum.NOT_STARTED,
            ui_chat_log=[initial_ui_chat_log],
            conversation_history={},
            vulnerability_id=vulnerability_id,
            vulnerability={},
            plan=Plan(steps=[]),
            files_changed=[],
        )
