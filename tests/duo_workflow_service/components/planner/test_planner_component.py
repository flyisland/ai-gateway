from unittest.mock import AsyncMock, Mock, call, patch

import pytest
from langchain_core.runnables import Runnable
from langgraph.constants import END
from langgraph.graph import StateGraph

from duo_workflow_service.components.planner.component import PlannerComponent, Routes
from duo_workflow_service.entities import WorkflowState, WorkflowStatusEnum


@pytest.fixture
def mock_tool_registry():
    registry = Mock()
    registry.approval_required.return_value = False
    return registry


@pytest.fixture
def base_state():
    return {
        "status": WorkflowStatusEnum.PLANNING,
        "conversation_history": {"planner": []},
    }


def set_up_graph(
    node_return_values, component: PlannerComponent
) -> tuple[Runnable, AsyncMock, AsyncMock, AsyncMock]:
    graph = StateGraph(WorkflowState)
    graph.set_entry_point("first_node")
    mock_entry_node = AsyncMock(side_effect=node_return_values)
    graph.add_node("first_node", mock_entry_node)

    mock_termination_node = AsyncMock(side_effect=node_return_values)
    graph.add_node("termination", mock_termination_node)
    graph.add_edge("termination", END)

    mock_continuation_node = AsyncMock(side_effect=node_return_values)
    graph.add_node("continuation", mock_continuation_node)
    graph.add_edge("continuation", END)
    entry_point = component.attach(
        graph=graph,
        exit_node="termination",
        next_node="continuation",
    )

    graph.add_conditional_edges(
        "first_node",
        lambda s: (
            "termination"
            if s["status"] == WorkflowStatusEnum.CANCELLED
            else entry_point
        ),
    )
    return (
        graph.compile(),
        mock_entry_node,
        mock_continuation_node,
        mock_termination_node,
    )


class TestPlannerComponent:
    @pytest.fixture
    def mock_dependencies(self):
        return {
            "workflow_id": "test-workflow-123",
            "workflow_type": "test-workflow-type",
            "goal": "Test goal",
            "planner_toolset": {"tool1": Mock(), "tool2": Mock()},
            "executor_toolset": {"exec_tool1": Mock(description="Executor tool 1")},
            "tools_registry": Mock(),
            "model_config": "",
            "project": {
                "id": 123,
                "name": "test-project",
                "http_url_to_repo": "https://gitlab.com/test/repo",
            },
            "http_client": Mock(),
        }

    @pytest.fixture
    def planner_component(self, mock_dependencies):
        return PlannerComponent(**mock_dependencies)

    def test_init(self, mock_dependencies):
        """Test PlannerComponent initialization."""
        component = PlannerComponent(**mock_dependencies)

        assert component.workflow_id == "test-workflow-123"
        assert component.workflow_type == "test-workflow-type"
        assert component.goal == "Test goal"
        assert component.planner_toolset == mock_dependencies["planner_toolset"]
        assert component.executor_toolset == mock_dependencies["executor_toolset"]
        assert component.tools_registry == mock_dependencies["tools_registry"]
        assert component.model_config == mock_dependencies["model_config"]
        assert component.project == mock_dependencies["project"]
        assert component.http_client == mock_dependencies["http_client"]

    @patch("duo_workflow_service.components.planner.component.create_chat_model")
    @patch("duo_workflow_service.components.planner.component.Agent")
    @patch("duo_workflow_service.components.planner.component.ToolsExecutor")
    @patch("duo_workflow_service.components.planner.component.PlanSupervisorAgent")
    def test_attach_creates_nodes_and_edges(
        self,
        mock_supervisor,
        mock_executor,
        mock_agent,
        mock_create_model,
        planner_component,
    ):
        """Test that attach method creates all necessary nodes and edges."""
        # Setup mocks
        mock_graph = Mock(spec=StateGraph)
        mock_model = Mock()
        mock_create_model.return_value = mock_model

        mock_tool = Mock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test tool description"
        planner_component.tools_registry.get.return_value = mock_tool

        # Execute
        entry_node = planner_component.attach(mock_graph, "exit_node", "next_node")

        # Verify nodes are added
        expected_calls = [
            call("planning", mock_agent.return_value.run),
            call("update_plan", mock_executor.return_value.run),
            call("planning_supervisor", mock_supervisor.return_value.run),
        ]
        mock_graph.add_node.assert_has_calls(expected_calls)

        # Verify edges are added
        mock_graph.add_conditional_edges.assert_called_once()
        mock_graph.add_edge.assert_has_calls(
            [call("update_plan", "planning"), call("planning_supervisor", "planning")]
        )

        # Verify return value
        assert entry_node == "planning"

    @patch("duo_workflow_service.components.planner.component.create_chat_model")
    @patch("duo_workflow_service.components.planner.component.Agent")
    def test_attach_creates_agent_with_correct_parameters(
        self, mock_agent, mock_create_model, planner_component
    ):
        """Test that Agent is created with correct parameters."""
        mock_graph = Mock(spec=StateGraph)
        mock_model = Mock()
        mock_create_model.return_value = mock_model

        mock_tool = Mock()
        mock_tool.name = "test_tool"
        planner_component.tools_registry.get.return_value = mock_tool

        planner_component.attach(mock_graph, "exit_node", "next_node")

        # Verify Agent was called with correct parameters
        mock_agent.assert_called_once()
        call_args = mock_agent.call_args

        assert call_args[1]["name"] == "planner"
        assert call_args[1]["workflow_id"] == "test-workflow-123"
        assert call_args[1]["model"] == mock_model
        assert call_args[1]["toolset"] == planner_component.planner_toolset
        assert call_args[1]["workflow_type"] == "test-workflow-type"

    def test_attach_conditional_edges_routing(self, planner_component):
        """Test that conditional edges are set up with correct routing."""
        mock_graph = Mock(spec=StateGraph)
        mock_tool = Mock()
        mock_tool.name = "test_tool"
        planner_component.tools_registry.get.return_value = mock_tool

        with patch(
            "duo_workflow_service.components.planner.component.create_chat_model"
        ), patch("duo_workflow_service.components.planner.component.Agent"), patch(
            "duo_workflow_service.components.planner.component.ToolsExecutor"
        ), patch(
            "duo_workflow_service.components.planner.component.PlanSupervisorAgent"
        ):
            planner_component.attach(mock_graph, "exit_node", "next_node")

            # Verify conditional edges routing
            call_args = mock_graph.add_conditional_edges.call_args
            routing_dict = call_args[0][2]

            assert routing_dict[Routes.CALL_TOOL] == "update_plan"
            assert routing_dict[Routes.SUPERVISOR] == "planning_supervisor"
            assert routing_dict[Routes.HANDOVER] == "next_node"
            assert routing_dict[Routes.STOP] == "exit_node"
