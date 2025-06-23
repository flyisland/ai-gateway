"""
SAST Analyzer Component.

This component encapsulates the SAST analysis functionality, including
the agent setup, tool execution, and workflow routing logic.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph

from duo_workflow_service.agents import Agent, HandoverAgent, ToolsExecutor
from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.entities import (
    MessageTypeEnum,
    Plan,
    ToolStatus,
    UiChatLog,
    WorkflowState,
    WorkflowStatusEnum,
)
from duo_workflow_service.gitlab.http_client import GitlabHttpClient
from duo_workflow_service.internal_events.event_enum import CategoryEnum
from .prompts import (
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


class Routes(StrEnum):
    """Workflow routing decisions."""
    CONTINUE = "continue"
    END = "end"
    AGENT = "agent"


class SastAnalyzerComponent:
    """Component for SAST false positive detection analysis."""

    def __init__(
        self,
        goal: str,
        model: BaseChatModel,
        workflow_id: str,
        tools_registry: ToolsRegistry,
        http_client: GitlabHttpClient,
        workflow_type: CategoryEnum,
    ):
        self._goal = goal
        self._model = model
        self._workflow_id = workflow_id
        self._http_client = http_client
        self._tools_registry = tools_registry
        self._workflow_type = workflow_type

    def attach(
        self,
        graph: StateGraph,
        entry_node: str,
        exit_node: str,
    ) -> str:
        """Attach the SAST analyzer component to the workflow graph.
        
        Args:
            graph: The workflow graph to attach to
            entry_node: The node to start from
            exit_node: The node to end at
            
        Returns:
            The entry node name for the component
        """
        # Setup the SAST analyzer agent and tools
        agents_toolset = self._tools_registry.toolset(ANALYSIS_TOOLS)
        analyzer_agent = Agent(
            goal="N/A",
            system_prompt="N/A",
            name=AGENT_NAME,
            model=self._model,
            toolset=agents_toolset,
            http_client=self._http_client,
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        )

        tools_executor = ToolsExecutor(
            tools_agent_name=AGENT_NAME,
            toolset=agents_toolset,
            workflow_id=self._workflow_id,
            workflow_type=self._workflow_type,
        )

        # Add nodes to the graph
        graph.add_node("sast_analyzer", analyzer_agent.run)
        graph.add_node("sast_tools", tools_executor.run)
        graph.add_node(
            "sast_complete",
            HandoverAgent(
                new_status=WorkflowStatusEnum.COMPLETED,
                handover_from=AGENT_NAME,
            ).run,
        )

        # Add edges to connect the component
        graph.add_edge(entry_node, "sast_analyzer")
        graph.add_conditional_edges(
            "sast_analyzer",
            self._tools_execution_requested,
            {
                Routes.CONTINUE: "sast_tools",
                Routes.END: "sast_complete",
            },
        )
        graph.add_conditional_edges(
            "sast_tools",
            self._router,
            {
                Routes.AGENT: "sast_analyzer",
                Routes.END: "sast_complete",
            },
        )
        graph.add_edge("sast_complete", exit_node)

        return "sast_analyzer"

    def _router(self, state: WorkflowState) -> str:
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

    def _tools_execution_requested(self, state: WorkflowState) -> str:
        """Check if the agent has requested tool execution."""
        if state["status"] == WorkflowStatusEnum.CANCELLED:
            return Routes.END

        agent_messages = state["conversation_history"].get(AGENT_NAME, [])
        if agent_messages and getattr(agent_messages[-1], "tool_calls", []):
            return Routes.CONTINUE

        return Routes.END

    def prepare_initial_state(self) -> WorkflowState:
        """Prepare the initial workflow state with SAST finding data."""
        import json
        
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
            from duo_workflow_service.token_counter.approximate_token_counter import (
                ApproximateTokenCounter,
            )
            from duo_workflow_service.entities import MAX_CONTEXT_TOKENS
            from langchain_core.messages import HumanMessage, SystemMessage
            
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

        # Extract basic finding info for initial log
        title, file_path, line_number = _extract_basic_finding_info(self._goal)
            
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

        # Prepare agent messages and logs
        messages, logs = _prepare_agent_messages(self._goal)

        return WorkflowState(
            status=WorkflowStatusEnum.EXECUTION,
            ui_chat_log=[initial_ui_chat_log] + logs,
            conversation_history={AGENT_NAME: messages},
            plan=Plan(steps=[]),
            handover=[],
            last_human_input=None,
            files_changed=[],
        ) 