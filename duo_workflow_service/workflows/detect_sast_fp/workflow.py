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

from typing import Any

from langgraph.checkpoint.memory import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from duo_workflow_service.components import SastAnalyzerComponent
from duo_workflow_service.entities import WorkflowState
from duo_workflow_service.llm_factory import create_chat_model
from duo_workflow_service.tracking import log_exception
from duo_workflow_service.workflows.abstract_workflow import (
    MAX_TOKENS_TO_SAMPLE,
    RECURSION_LIMIT,
    AbstractWorkflow,
)


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
        tools_registry,
        checkpointer: BaseCheckpointSaver,
    ):
        """Compile the workflow graph."""
        graph = StateGraph(WorkflowState)
        graph = self._setup_workflow_graph(graph, tools_registry, goal)
        return graph.compile(checkpointer=checkpointer)

    def _setup_workflow_graph(
        self,
        graph: StateGraph,
        tools_registry,
        goal: str,
    ):
        """Setup the complete workflow graph using the SAST analyzer component."""
        self.log.info("Starting %s workflow graph compilation", self._workflow_type)
        
        # Create the SAST analyzer component
        sast_analyzer_component = SastAnalyzerComponent(
            goal=goal,
            model=create_chat_model(
                max_tokens=MAX_TOKENS_TO_SAMPLE,
                config=self._model_config,
            ),
            workflow_id=self._workflow_id,
            tools_registry=tools_registry,
            http_client=self._http_client,
            workflow_type=self._workflow_type,
        )

        # Setup the workflow graph
        graph.set_entry_point("start")
        
        # Add a start node that prepares the component state
        def start_node(state: WorkflowState) -> WorkflowState:
            """Start node that prepares the component state."""
            # Prepare the component state
            component_state = sast_analyzer_component.prepare_initial_state()
            
            # Merge the component state with the existing state
            return WorkflowState(
                status=component_state["status"],
                ui_chat_log=state.get("ui_chat_log", []) + component_state["ui_chat_log"],
                conversation_history=component_state["conversation_history"],
                plan=component_state["plan"],
                handover=component_state["handover"],
                last_human_input=component_state["last_human_input"],
                files_changed=component_state["files_changed"],
            )
        
        graph.add_node("start", start_node)
        
        # Attach the SAST analyzer component
        # The component returns the entry node name, but we don't need to use it
        # since we're connecting directly from "start" to the component
        sast_analyzer_component.attach(
            graph=graph,
            entry_node="start",
            exit_node=END,
        )
        
        return graph

    def get_workflow_state(self, goal: str) -> WorkflowState:
        """Create the initial workflow state."""
        import json
        from datetime import datetime, timezone
        from duo_workflow_service.entities import (
            MessageTypeEnum,
            Plan,
            ToolStatus,
            UiChatLog,
            WorkflowStatusEnum,
        )
        
        # Extract basic finding info for initial log
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
