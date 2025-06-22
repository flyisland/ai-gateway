"""
SAST False Positive Detection Workflow.

This module implements a workflow for analyzing Static Application Security Testing (SAST)
findings to determine whether they represent legitimate security vulnerabilities or false positives.

The workflow uses an AI agent to:
1. Parse SAST finding data from JSON input
2. Analyze the code context around reported vulnerabilities
3. Examine security controls and mitigations
4. Evaluate exploitability and risk
5. Generate a detailed analysis report

The agent has access to tools for reading source code files, finding related files,
and creating analysis result files.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from duo_workflow_service.agents import Agent, HandoverAgent, ToolsExecutor
from duo_workflow_service.components import ToolsRegistry
from duo_workflow_service.entities import (
    MAX_CONTEXT_TOKENS,
    MessageTypeEnum,
    Plan,
    ToolStatus,
    UiChatLog,
    WorkflowState,
    WorkflowStatusEnum,
)
from duo_workflow_service.internal_events.event_enum import CategoryEnum
from duo_workflow_service.llm_factory import create_chat_model
from duo_workflow_service.token_counter.approximate_token_counter import (
    ApproximateTokenCounter,
)
from duo_workflow_service.tracking import log_exception
from duo_workflow_service.workflows.abstract_workflow import (
    MAX_TOKENS_TO_SAMPLE,
    RECURSION_LIMIT,
    AbstractWorkflow,
)
from duo_workflow_service.workflows.detect_sast_fp.prompts import (
    SAST_ANALYZER_FILE_USER_MESSAGE,
    SAST_ANALYZER_SYSTEM_MESSAGE,
    SAST_ANALYZER_USER_GUIDELINES,
)

AGENT_NAME = "sast_analyzer_agent"

# Tool names used by the SAST analyzer
READ_FILE_TOOL = "read_file"
CREATE_FILE_TOOL = "create_file_with_contents"
FIND_FILES_TOOL = "find_files"

# Analysis tools list
ANALYSIS_TOOLS = [READ_FILE_TOOL, CREATE_FILE_TOOL, FIND_FILES_TOOL]

# ROUTERS
class Routes(StrEnum):
    """Workflow routing decisions."""
    CONTINUE = "continue"
    END = "end"
    AGENT = "agent"


def _router(state: WorkflowState) -> str:
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


def _tools_execution_requested(state: WorkflowState) -> str:
    """Check if the agent has requested tool execution."""
    if state["status"] == WorkflowStatusEnum.CANCELLED:
        return Routes.END

    agent_messages = state["conversation_history"].get(AGENT_NAME, [])
    if agent_messages and getattr(agent_messages[-1], "tool_calls", []):
        return Routes.CONTINUE

    return Routes.END


def _extract_basic_finding_info(goal: str) -> tuple[str, str, str]:
    """Extract basic finding information from the goal for logging purposes."""
    try:
        finding_data = json.loads(goal)
        title = finding_data.get("title", "Unknown")
        file_path = finding_data.get("finding", {}).get("location", {}).get("file", "Unknown")
        line_number = finding_data.get("finding", {}).get("location", {}).get("start_line", "Unknown")
        return title, file_path, line_number
    except (json.JSONDecodeError, KeyError):
        return "Unknown", "Unknown", "Unknown"


def _parse_sast_finding_data(goal: str) -> dict[str, Any]:
    """Parse SAST finding data from the goal JSON string."""
    if not goal:
        raise RuntimeError("No goal provided")
        
    finding_data = json.loads(goal)
    
    # Extract key information with safe defaults
    title = finding_data.get("title", "")
    file_path = finding_data.get("finding", {}).get("location", {}).get("file", "")
    line_number = finding_data.get("finding", {}).get("location", {}).get("start_line", "")
    severity = finding_data.get("severity", "")
    description = finding_data.get("finding", {}).get("description", "")
    raw_metadata = finding_data.get("finding", {}).get("raw_metadata", "")
    
    # Parse raw metadata if available
    metadata = {}
    if raw_metadata:
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            pass
    
    return {
        "title": title,
        "file_path": file_path,
        "line_number": line_number,
        "severity": severity,
        "description": description,
        "metadata": metadata,
        "raw_finding": finding_data
    }


def _create_ui_log(
    content: str, 
    status: ToolStatus = ToolStatus.SUCCESS
) -> UiChatLog:
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


def _prepare_agent_messages(goal: str) -> tuple[list, list[UiChatLog]]:
    """Prepare agent messages and logs from the SAST finding goal."""
    finding_info = _parse_sast_finding_data(goal)
    
    logs: list[UiChatLog] = []
    
    # Prepare messages for the agent
    human_prompt = SAST_ANALYZER_FILE_USER_MESSAGE.format(
        finding_data=json.dumps(finding_info, indent=2),
    )
    messages = [
        SystemMessage(content=SAST_ANALYZER_SYSTEM_MESSAGE),
        HumanMessage(content=SAST_ANALYZER_USER_GUIDELINES),
        HumanMessage(content=human_prompt),
    ]
    
    # Check token limit
    if ApproximateTokenCounter(AGENT_NAME).count_tokens(messages) > MAX_CONTEXT_TOKENS:
        messages = []
        logs.append(_create_ui_log(
            "SAST finding data too large, skipping analysis.",
            status=ToolStatus.FAILURE
        ))
    else:
        title = finding_info["title"]
        file_path = finding_info["file_path"]
        line_number = finding_info["line_number"]
        logs.append(_create_ui_log(
            f"Loaded SAST finding: {title} in {file_path}:{line_number}"
        ))
    
    return messages, logs


class Workflow(AbstractWorkflow):
    """SAST False Positive Detection Workflow.
    
    This workflow analyzes SAST findings to determine if they are legitimate
    security vulnerabilities or false positives. It uses an AI agent to examine
    the code context and provide detailed analysis.
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
        graph = StateGraph(WorkflowState)
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
        """Setup the complete workflow graph with all nodes and edges."""
        analyzer_components = self._setup_analyzer_nodes(tools_registry)

        self.log.info("Starting %s workflow graph compilation", self._workflow_type)
        graph.set_entry_point("parse_sast_finding")
        
        # Parse SAST finding from goal JSON using a custom node
        def parse_sast_finding_with_goal(state: WorkflowState) -> WorkflowState:
            messages, logs = _prepare_agent_messages(goal)
            return WorkflowState(
                status=WorkflowStatusEnum.EXECUTION,
                ui_chat_log=state.get("ui_chat_log", []) + logs,
                conversation_history={AGENT_NAME: messages},
                plan=Plan(steps=[]),
                handover=[],
                last_human_input=None,
                files_changed=[],
            )
        
        # Add all nodes to the graph
        graph.add_node("parse_sast_finding", parse_sast_finding_with_goal)
        graph.add_node(analyzer_components["start_node"], analyzer_components["agent"].run)
        graph.add_node("execution_tools", analyzer_components["tools_executor"].run)
        graph.add_node(
            "complete",
            HandoverAgent(
                new_status=WorkflowStatusEnum.COMPLETED, 
                handover_from=AGENT_NAME
            ).run,
        )

        # Add edges to connect the workflow
        graph.add_edge("parse_sast_finding", analyzer_components["start_node"])
        graph.add_conditional_edges(
            analyzer_components["start_node"],
            _tools_execution_requested,
            {
                Routes.CONTINUE: "execution_tools",
                Routes.END: "complete",
            },
        )
        graph.add_conditional_edges(
            "execution_tools",
            _router,
            {
                Routes.AGENT: analyzer_components["start_node"],
                Routes.END: "complete",
            },
        )
        graph.add_edge("complete", END)
        
        return graph

    def get_workflow_state(self, goal: str) -> WorkflowState:
        """Create the initial workflow state with the starting log message."""
        title, file_path, line_number = _extract_basic_finding_info(goal)
            
        initial_ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.TOOL,
            message_sub_type=None,
            content=f"Starting SAST false positive detection workflow for: {title} in {file_path}:{line_number}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.SUCCESS,
            correlation_id=None,
            tool_info=None,
            context_elements=None,
        )

        return WorkflowState(
            status=WorkflowStatusEnum.NOT_STARTED,
            ui_chat_log=[initial_ui_chat_log],
            conversation_history={},
            plan=Plan(steps=[]),
            handover=[],
            last_human_input=None,
            files_changed=[],
        )
