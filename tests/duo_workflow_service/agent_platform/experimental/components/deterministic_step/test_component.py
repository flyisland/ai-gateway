"""Test suite for DeterministicStepComponent class."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain.tools import BaseTool
from pydantic import ValidationError

from duo_workflow_service.agent_platform.experimental.components.deterministic_step.component import (
    DeterministicStepComponent,
)
from duo_workflow_service.agent_platform.experimental.components.deterministic_step.ui_log import (
    UILogWriterDeterministicStep,
)
from duo_workflow_service.agent_platform.experimental.state import IOKey
from duo_workflow_service.agent_platform.experimental.ui_log import UIHistory
from duo_workflow_service.tools.toolset import Toolset
from lib.internal_events import InternalEventsClient
from lib.internal_events.event_enum import CategoryEnum


@pytest.fixture(name="mock_tool")
def mock_tool_fixture():
    """Fixture for mock tool."""
    tool = Mock(spec=BaseTool)
    tool.name = "test_tool"
    tool._arun = AsyncMock(return_value="tool_result")
    return tool


@pytest.fixture(name="mock_toolset")
def mock_toolset_fixture(mock_tool):
    """Fixture for mock toolset."""
    toolset = Mock(spec=Toolset)
    toolset.__getitem__ = Mock(return_value=mock_tool)
    toolset.__contains__ = Mock(return_value=True)
    return toolset


@pytest.fixture(name="component_name")
def component_name_fixture():
    """Fixture for component name."""
    return "test_component"


@pytest.fixture(name="flow_id")
def flow_id_fixture():
    """Fixture for flow ID."""
    return "test_flow_123"


@pytest.fixture(name="flow_type")
def flow_type_fixture():
    """Fixture for flow type."""
    return CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT


@pytest.fixture(name="inputs")
def inputs_fixture():
    """Fixture for component inputs."""
    return [
        IOKey(target="context", subkeys=["user_input"]),
        IOKey(target="context", subkeys=["task_description"]),
    ]


@pytest.fixture(name="deterministic_component")
def deterministic_component_fixture(component_name, flow_id, flow_type, mock_toolset):
    """Fixture for DeterministicStepComponent instance."""
    return DeterministicStepComponent(
        name=component_name,
        flow_id=flow_id,
        flow_type=flow_type,
        inputs=["context:user_input", "context:task_description"],
        tool_name="test_tool",
        toolset=mock_toolset,
    )


@pytest.fixture(name="mock_state_graph")
def mock_state_graph_fixture():
    """Fixture for mock StateGraph."""
    return Mock()


@pytest.fixture(name="mock_router")
def mock_router_fixture():
    """Fixture for mock router."""
    return Mock()


@pytest.fixture(name="base_flow_state")
def base_flow_state_fixture():
    """Fixture for base flow state."""
    return {
        "status": "in_progress",
        "conversation_history": {},
        "ui_chat_log": [],
        "context": {"input_param": "test_value"},
    }


@pytest.fixture(name="tool_name")
def tool_name_fixture():
    """Fixture for tool name."""
    return "example_tool"


@pytest.fixture(name="ui_log_events")
def ui_log_events_fixture():
    """Fixture for UI log events."""
    return []


@pytest.fixture(name="ui_role_as")
def ui_role_as_fixture():
    """Fixture for UI role."""
    return "tool"


@pytest.fixture(name="mock_internal_event_client")
def mock_internal_event_client_fixture():
    """Fixture for mock internal event client."""
    return Mock(spec=InternalEventsClient)


@pytest.fixture(name="deterministic_step_component")
def deterministic_step_component_fixture(
    component_name,
    flow_id,
    flow_type,
    tool_name,
    ui_log_events,
    ui_role_as,
    mock_toolset,
    mock_internal_event_client,
):
    """Fixture for DeterministicStepComponent instance."""
    return DeterministicStepComponent(
        name=component_name,
        flow_id=flow_id,
        flow_type=flow_type,
        inputs=["context:user_input", "context:task_description"],
        tool_name=tool_name,
        toolset=mock_toolset,
        internal_event_client=mock_internal_event_client,
        ui_log_events=ui_log_events,
        ui_role_as=ui_role_as,
    )


@pytest.fixture(name="mock_deterministic_step_node_cls")
def mock_deterministic_step_node_cls_fixture(component_name):
    """Fixture for mocked DeterministicStepNode class."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.deterministic_step.component.DeterministicStepNode"
    ) as mock_cls:
        mock_node = Mock()
        mock_node.name = f"{component_name}#deterministic_step"
        mock_cls.return_value = mock_node

        yield mock_cls


class TestDeterministicStepComponentInitialization:
    """Test suite for DeterministicStepComponent initialization."""

    @pytest.mark.parametrize(
        "input_output",
        [
            "context:user_input",
            "conversation_history:agent_component",
        ],
    )
    def test_allowed_targets_through_validation(
        self,
        component_name,
        flow_id,
        flow_type,
        mock_toolset,
        input_output,
    ):
        """Test that component validates input targets correctly."""
        # This should succeed without raising an exception
        DeterministicStepComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=[input_output],
            toolset=mock_toolset,
            tool_name="test_tool",
        )

    @pytest.mark.parametrize(
        "input_output",
        [
            "status",
            "ui_chat_log",
        ],
    )
    def test_not_allowed_targets_through_validation(
        self,
        component_name,
        flow_id,
        flow_type,
        mock_toolset,
        input_output,
    ):
        """Test that component validates input targets correctly."""
        # This should succeed without raising an exception
        with pytest.raises(ValidationError, match="doesn't support the input target"):
            DeterministicStepComponent(
                name=component_name,
                flow_id=flow_id,
                flow_type=flow_type,
                inputs=[input_output],
                toolset=mock_toolset,
                tool_name="test_tool",
            )


class TestDeterministicStepComponentEntryHook:
    """Test suite for DeterministicStepComponent entry hook."""

    def test_entry_hook_returns_correct_node_name(
        self, deterministic_component, component_name
    ):
        """Test that __entry_hook__ returns the correct node name."""
        expected_entry_node = f"{component_name}#deterministic_step"
        assert deterministic_component.__entry_hook__() == expected_entry_node


class TestDeterministicStepComponentAttachNodes:
    """Test suite for DeterministicStepComponent attach method."""

    def test_attach_creates_node_with_correct_parameters(
        self,
        mock_deterministic_step_node_cls,
        deterministic_step_component,
        mock_state_graph,
        mock_router,
        component_name,
        flow_id,
        flow_type,
        inputs,
        tool_name,
        mock_toolset,
        ui_log_events,
    ):
        """Test that node is created with correct parameters."""
        deterministic_step_component.attach(mock_state_graph, mock_router)

        # Verify DeterministicStepNode creation
        mock_deterministic_step_node_cls.assert_called_once()
        node_call_kwargs = mock_deterministic_step_node_cls.call_args[1]

        assert node_call_kwargs["name"] == f"{component_name}#deterministic_step"
        assert node_call_kwargs["tool_name"] == tool_name
        assert node_call_kwargs["component_name"] == component_name
        assert node_call_kwargs["inputs"] == inputs
        assert node_call_kwargs["toolset"] == mock_toolset
        assert node_call_kwargs["flow_id"] == flow_id
        assert node_call_kwargs["flow_type"] == flow_type
        assert (
            node_call_kwargs["internal_event_client"]
            == deterministic_step_component.internal_event_client
        )

        # Verify UI logging
        assert "ui_history" in node_call_kwargs
        assert isinstance(node_call_kwargs["ui_history"], UIHistory)
        assert node_call_kwargs["ui_history"].events == ui_log_events

    def test_attach_uses_correct_ui_log_writer(
        self,
        mock_deterministic_step_node_cls,
        deterministic_step_component,
        mock_state_graph,
        mock_router,
    ):
        """Test that the correct UI log writer class is used."""
        deterministic_step_component.attach(mock_state_graph, mock_router)

        # Get the ui_history argument
        node_call_kwargs = mock_deterministic_step_node_cls.call_args[1]
        ui_history = node_call_kwargs["ui_history"]

        assert ui_history.writer_class == UILogWriterDeterministicStep


class TestDeterministicStepComponentAttachEdges:
    """Test suite for DeterministicStepComponent graph structure."""

    def test_attach_creates_graph_structure(
        self,
        deterministic_step_component,
        mock_state_graph,
        mock_router,
        component_name,
        mock_deterministic_step_node_cls,
    ):
        """Test that attach method creates proper graph structure."""
        deterministic_step_component.attach(mock_state_graph, mock_router)

        expected_node_name = f"{component_name}#deterministic_step"

        # Verify node was added
        mock_state_graph.add_node.assert_called_once_with(
            expected_node_name, mock_deterministic_step_node_cls.return_value.run
        )

        # Verify conditional edge was added
        mock_state_graph.add_conditional_edges.assert_called_once_with(
            expected_node_name, mock_router.route
        )

    def test_attach_no_internal_routing(
        self,
        deterministic_step_component,
        mock_state_graph,
        mock_router,
    ):
        """Test that component has no internal routing logic."""
        deterministic_step_component.attach(mock_state_graph, mock_router)

        # Should not have any regular edges (only conditional edges to router)
        mock_state_graph.add_edge.assert_not_called()

        # Should have exactly one conditional edge (to the router)
        assert mock_state_graph.add_conditional_edges.call_count == 1


class TestDeterministicStepComponentIntegration:
    """Test suite for DeterministicStepComponent integration aspects."""

    def test_component_requires_tool_name(
        self,
        component_name,
        flow_id,
        flow_type,
        mock_toolset,
        mock_internal_event_client,
    ):
        """Test that component requires tool_name parameter."""
        with pytest.raises(ValidationError):
            DeterministicStepComponent(
                name=component_name,
                flow_id=flow_id,
                flow_type=flow_type,
                inputs=["context:user_input"],
                # tool_name is missing
                toolset=mock_toolset,
                internal_event_client=mock_internal_event_client,
            )

    def test_component_requires_toolset(
        self,
        component_name,
        flow_id,
        flow_type,
        tool_name,
        mock_internal_event_client,
    ):
        """Test that component requires toolset parameter."""
        with pytest.raises(ValidationError):
            DeterministicStepComponent(
                name=component_name,
                flow_id=flow_id,
                flow_type=flow_type,
                inputs=["context:user_input"],
                tool_name=tool_name,
                # toolset is missing
                internal_event_client=mock_internal_event_client,
            )

    def test_component_with_empty_ui_log_events(
        self,
        component_name,
        flow_id,
        flow_type,
        tool_name,
        mock_toolset,
        mock_internal_event_client,
    ):
        """Test that component can be created with empty ui_log_events."""
        component = DeterministicStepComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=["context:user_input"],
            tool_name=tool_name,
            toolset=mock_toolset,
            internal_event_client=mock_internal_event_client,
            # ui_log_events not provided, should use default empty list
        )
        assert component.ui_log_events == []
