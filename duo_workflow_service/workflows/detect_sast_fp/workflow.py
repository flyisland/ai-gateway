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
from enum import StrEnum
from typing import Any
import json
import asyncio

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
    DetectSastFpWorkflowState,
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
GET_VULNERABILITY_TOOL = "get_vulnerability"
READ_FILE_TOOL = "read_file"
CREATE_FILE_TOOL = "create_file_with_contents"
FIND_FILES_TOOL = "find_files"

# Analysis tools list (agent tools - excludes get_vulnerability since it's called deterministically)
ANALYSIS_TOOLS = [READ_FILE_TOOL, CREATE_FILE_TOOL, FIND_FILES_TOOL]


# ROUTERS
class Routes(StrEnum):
    """Workflow routing decisions."""

    CONTINUE = "continue"
    END = "end"
    AGENT = "agent"


def _router(state: DetectSastFpWorkflowState) -> str:
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


def _tools_execution_requested(state: DetectSastFpWorkflowState) -> str:
    """Check if the agent has requested tool execution."""
    if state["status"] == WorkflowStatusEnum.CANCELLED:
        return Routes.END

    agent_messages = state["conversation_history"].get(AGENT_NAME, [])
    if agent_messages and getattr(agent_messages[-1], "tool_calls", []):
        return Routes.CONTINUE

    return Routes.END


def _extract_vulnerability_id(goal: str) -> str:
    """Extract vulnerability ID from the goal for logging purposes."""
    try:
        # The goal should be a simple vulnerability ID string
        vulnerability_id = goal.strip()
        if not vulnerability_id:
            raise ValueError("Empty vulnerability ID")
        return vulnerability_id
    except Exception:
        return "Unknown"


def _create_ui_log(content: str, status: ToolStatus = ToolStatus.SUCCESS) -> UiChatLog:
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


def _fetch_vulnerability_details_node(tools_registry, vulnerability_id):
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
                ui_log = _create_ui_log(
                    f"Error fetching vulnerability details: {vuln_data['error']}",
                    status=ToolStatus.FAILURE,
                )
            else:
                ui_log = _create_ui_log(
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
            error_log = _create_ui_log(
                f"Exception while fetching vulnerability details: {str(e)}",
                status=ToolStatus.FAILURE,
            )
            state["ui_chat_log"] = state.get("ui_chat_log", []) + [error_log]
            return state

    return fetch_vulnerability_details


def _prepare_agent_messages_from_details(
    vuln_details: dict,
) -> tuple[list, list[UiChatLog]]:
    """Prepare agent messages and logs for vulnerability analysis using details."""
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
            _create_ui_log(
                "Vulnerability details too large, skipping analysis.",
                status=ToolStatus.FAILURE,
            )
        )
    else:
        title = vuln_details.get("title", "Unknown")
        file_path = vuln_details.get("location", {}).get("file", "Unknown")
        line_number = vuln_details.get("location", {}).get("startLine", "Unknown")
        logs.append(
            _create_ui_log(
                f"Loaded vulnerability: {title} in {file_path}:{line_number}"
            )
        )
    return messages, logs


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
        graph.set_entry_point("parse_vulnerability_id")

        def parse_vulnerability_id_with_goal(
            state: DetectSastFpWorkflowState,
        ) -> DetectSastFpWorkflowState:
            vulnerability_id = _extract_vulnerability_id(goal)
            # Only log the start, don't prepare agent messages yet
            logs = [_create_ui_log(f"Loaded vulnerability ID: {vulnerability_id}")]
            return DetectSastFpWorkflowState(
                status=WorkflowStatusEnum.EXECUTION,
                ui_chat_log=state.get("ui_chat_log", []) + logs,
                conversation_history={},
                vulnerability_id=vulnerability_id,
                vulnerability={},
                plan=Plan(steps=[]),
                files_changed=[],
            )

        # Deterministic node to fetch vulnerability details
        fetch_vuln_details_node = _fetch_vulnerability_details_node(
            tools_registry, _extract_vulnerability_id(goal)
        )

        async def prepare_agent_messages_node(
            state: DetectSastFpWorkflowState,
        ) -> DetectSastFpWorkflowState:
            vuln_details = state.get("vulnerability", {})

            # Add a log to indicate we're preparing agent messages
            state = dict(state)
            state["ui_chat_log"] = state.get("ui_chat_log", []) + [
                _create_ui_log("Preparing agent messages with vulnerability details")
            ]

            try:
                messages, logs = _prepare_agent_messages_from_details(vuln_details)
                state["conversation_history"] = {AGENT_NAME: messages}
                state["ui_chat_log"] = state.get("ui_chat_log", []) + logs

                # Add a log to indicate agent is about to start
                state["ui_chat_log"].append(
                    _create_ui_log("Agent messages prepared, starting analysis")
                )

            except Exception as e:
                # Handle any errors in message preparation
                error_log = _create_ui_log(
                    f"Error preparing agent messages: {str(e)}",
                    status=ToolStatus.FAILURE,
                )
                state["ui_chat_log"].append(error_log)
                # Still set empty conversation history so workflow can continue
                state["conversation_history"] = {AGENT_NAME: []}

            return state

        # Add all nodes to the graph
        graph.add_node("parse_vulnerability_id", parse_vulnerability_id_with_goal)
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
        graph.add_edge("parse_vulnerability_id", "fetch_vulnerability_details")
        graph.add_edge("fetch_vulnerability_details", "prepare_agent_messages")
        graph.add_edge("prepare_agent_messages", analyzer_components["start_node"])
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

    def get_workflow_state(self, goal: str) -> DetectSastFpWorkflowState:
        """Create the initial workflow state with the starting log message."""
        vulnerability_id = _extract_vulnerability_id(goal)

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
