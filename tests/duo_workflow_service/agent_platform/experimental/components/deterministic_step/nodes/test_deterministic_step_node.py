from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.tools import BaseTool
from pydantic_core import ValidationError

from duo_workflow_service.agent_platform.experimental.components.agent.ui_log import (
    UILogEventsAgent,
)
from duo_workflow_service.agent_platform.experimental.components.deterministic_step.nodes.deterministic_step_node import (
    DeterministicStepNode,
)
from duo_workflow_service.agent_platform.experimental.state import FlowStateKeys, IOKey
from duo_workflow_service.security.prompt_security import SecurityException
from lib.internal_events.event_enum import CategoryEnum, EventEnum


@pytest.fixture(name="mock_prompt_security")
def mock_prompt_security_fixture():
    """Fixture for mocking PromptSecurity."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.deterministic_step.nodes.deterministic_step_node.PromptSecurity"
    ) as mock_security:
        mock_security.apply_security_to_tool_response.return_value = (
            "Sanitized response"
        )
        yield mock_security


@pytest.fixture(name="mock_logger")
def mock_logger_fixture():
    """Fixture for mocking structlog logger."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.deterministic_step.nodes.deterministic_step_node.structlog"
    ) as mock_structlog:
        mock_logger = Mock()
        mock_structlog.stdlib.get_logger.return_value = mock_logger
        yield mock_logger


@pytest.fixture(name="mock_tool_monitoring")
def mock_tool_monitoring_fixture():
    """Fixture for mocking duo_workflow_metrics for tool operations."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.deterministic_step.nodes.deterministic_step_node.duo_workflow_metrics"
    ) as mock_metrics:
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_context_manager)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_metrics.time_tool_call.return_value = mock_context_manager
        yield mock_metrics


@pytest.fixture(name="mock_get_vars_from_state")
def mock_get_vars_from_state_fixture():
    """Fixture for mocking get_vars_from_state."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.deterministic_step.nodes.deterministic_step_node.get_vars_from_state"
    ) as mock_get_vars:
        mock_get_vars.return_value = {"param": "value"}
        yield mock_get_vars


@pytest.fixture(name="mock_tool")
def mock_tool_fixture():
    """Fixture for mock tool."""
    mock_tool = Mock(spec=BaseTool)
    mock_tool.name = "test_tool"
    mock_tool.arun = AsyncMock(return_value="Tool execution result")
    mock_tool.args_schema = None
    return mock_tool


@pytest.fixture(name="mock_toolset")
def mock_toolset_fixture(mock_tool):
    """Fixture for mock toolset."""
    mock_toolset = Mock()
    mock_toolset.__contains__ = Mock(return_value=True)
    mock_toolset.__getitem__ = Mock(return_value=mock_tool)
    return mock_toolset


@pytest.fixture(name="component_name")
def component_name_fixture():
    """Fixture for component name."""
    return "test_component"


@pytest.fixture(name="flow_id")
def flow_id_fixture():
    """Fixture for flow ID."""
    return "test_flow_id"


@pytest.fixture(name="flow_type")
def flow_type_fixture():
    """Fixture for flow type."""
    return CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT


@pytest.fixture(name="inputs")
def inputs_fixture():
    """Fixture for inputs."""
    return [
        IOKey(target="context", subkeys=["input1"]),
        IOKey(target="context", subkeys=["input2"]),
    ]


@pytest.fixture(name="mock_internal_event_client")
def mock_internal_event_client_fixture():
    """Fixture for mock internal event client."""
    mock_client = Mock()
    mock_client.track_event = Mock()
    return mock_client


@pytest.fixture(name="ui_history")
def ui_history_fixture():
    """Fixture for UI history."""
    mock_ui_history = Mock()
    mock_ui_history.log = Mock()
    mock_ui_history.log.success = Mock()
    mock_ui_history.log.error = Mock()
    mock_ui_history.pop_state_updates = Mock(return_value={})
    return mock_ui_history


@pytest.fixture(name="flow_state")
def flow_state_fixture():
    """Fixture for flow state."""
    return {
        FlowStateKeys.CONTEXT: {
            "input1": "value1",
            "input2": "value2",
        }
    }


@pytest.fixture(name="deterministic_step_node")
def deterministic_step_node_fixture(
    component_name,
    inputs,
    mock_toolset,
    flow_id,
    flow_type,
    mock_internal_event_client,
    ui_history,
    mock_tool_monitoring,
    mock_prompt_security,
    mock_logger,
    mock_get_vars_from_state,
):
    """Fixture for DeterministicStepNode instance."""
    return DeterministicStepNode(
        name="test_node",
        tool_name="test_tool",
        component_name=component_name,
        inputs=inputs,
        toolset=mock_toolset,
        flow_id=flow_id,
        flow_type=flow_type,
        internal_event_client=mock_internal_event_client,
        ui_history=ui_history,
    )


class TestDeterministicStepNode:
    """Test suite for DeterministicStepNode class focusing on the run method."""

    @pytest.mark.asyncio
    async def test_run_success(
        self,
        deterministic_step_node,
        flow_state,
        component_name,
        mock_tool,
        mock_get_vars_from_state,
        mock_tool_monitoring,
        mock_prompt_security,
        ui_history,
        inputs,
    ):
        """Test successful run with tool execution."""
        result = await deterministic_step_node.run(flow_state)

        # Verify get_vars_from_state was called
        mock_get_vars_from_state.assert_called_once_with(inputs, flow_state)

        # Verify result structure
        assert FlowStateKeys.CONTEXT in result
        assert component_name in result[FlowStateKeys.CONTEXT]
        assert (
            result[FlowStateKeys.CONTEXT][component_name]["tool_result"]
            == "Sanitized response"
        )

        # Verify tool execution was called
        mock_tool.arun.assert_called_once_with({"param": "value"})

        # Verify security sanitization was called
        mock_prompt_security.apply_security_to_tool_response.assert_called_once_with(
            response="Tool execution result", tool_name="test_tool"
        )

        # Verify ui_history.log.success was called
        ui_history.log.success.assert_called_once()
        call_args = ui_history.log.success.call_args
        assert call_args[1]["tool"] == mock_tool
        assert call_args[1]["tool_call_args"] == {"param": "value"}
        assert call_args[1]["tool_response"] == "Sanitized response"
        assert call_args[1]["event"] == UILogEventsAgent.ON_TOOL_EXECUTION_SUCCESS

        # Verify ui_history.pop_state_updates was called
        ui_history.pop_state_updates.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_tool_not_found(
        self,
        deterministic_step_node,
        flow_state,
        component_name,
        mock_toolset,
        ui_history,
        mock_get_vars_from_state,
    ):
        """Test run when tool is not found in toolset."""
        # Configure toolset to not contain the tool
        mock_toolset.__contains__ = Mock(return_value=False)

        result = await deterministic_step_node.run(flow_state)

        # Verify result structure with error
        assert FlowStateKeys.CONTEXT in result
        assert component_name in result[FlowStateKeys.CONTEXT]
        assert result[FlowStateKeys.CONTEXT][component_name]["tool_result"] is None
        assert (
            "Tool test_tool not found"
            in result[FlowStateKeys.CONTEXT][component_name]["error"]
        )

        # Verify ui_history.log.error was called
        ui_history.log.error.assert_called_once()
        call_args = ui_history.log.error.call_args
        assert "Tool test_tool not found" in call_args[1]["error"]
        assert call_args[1]["event"] == UILogEventsAgent.ON_TOOL_EXECUTION_FAILED

    @pytest.mark.asyncio
    async def test_run_type_error_handling(
        self,
        deterministic_step_node,
        flow_state,
        component_name,
        mock_tool,
        mock_internal_event_client,
        ui_history,
        mock_tool_monitoring,
        flow_type,
        mock_get_vars_from_state,
    ):
        """Test run handles TypeError during tool execution."""
        # Configure tool to raise TypeError
        type_error = TypeError("Invalid argument type")
        mock_tool.arun = AsyncMock(side_effect=type_error)
        mock_tool.args_schema = Mock()
        mock_tool.args_schema.model_json_schema.return_value = {
            "type": "object",
            "properties": {},
        }

        result = await deterministic_step_node.run(flow_state)

        # Verify error message in result
        assert FlowStateKeys.CONTEXT in result
        assert component_name in result[FlowStateKeys.CONTEXT]
        assert result[FlowStateKeys.CONTEXT][component_name]["tool_result"] is None
        error_msg = result[FlowStateKeys.CONTEXT][component_name]["error"]
        assert "Tool test_tool execution failed due to wrong arguments" in error_msg
        assert "The schema is:" in error_msg

        # Verify internal event tracking for failure
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Verify ui_history.log.error was called
        ui_history.log.error.assert_called_once()

        # Verify tool error metric was called
        mock_tool_monitoring.count_agent_platform_tool_failure.assert_called_once_with(
            flow_type=flow_type.value,
            tool_name="test_tool",
            failure_reason="TypeError",
        )

    @pytest.mark.asyncio
    async def test_run_validation_error_handling(
        self,
        deterministic_step_node,
        flow_state,
        component_name,
        mock_tool,
        mock_internal_event_client,
        ui_history,
        mock_tool_monitoring,
        flow_type,
        mock_get_vars_from_state,
    ):
        """Test run handles ValidationError during tool execution."""
        # Configure tool to raise ValidationError
        validation_error = ValidationError.from_exception_data(
            "ValidationError",
            [{"type": "missing", "loc": ["field"], "msg": "Field required"}],
        )
        mock_tool.arun = AsyncMock(side_effect=validation_error)

        result = await deterministic_step_node.run(flow_state)

        # Verify error message in result
        assert FlowStateKeys.CONTEXT in result
        assert component_name in result[FlowStateKeys.CONTEXT]
        assert result[FlowStateKeys.CONTEXT][component_name]["tool_result"] is None
        error_msg = result[FlowStateKeys.CONTEXT][component_name]["error"]
        assert "raised validation error" in error_msg

        # Verify internal event tracking for failure
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Verify tool error metric was called
        mock_tool_monitoring.count_agent_platform_tool_failure.assert_called_once_with(
            flow_type=flow_type.value,
            tool_name="test_tool",
            failure_reason="ValidationError",
        )

    @pytest.mark.asyncio
    async def test_run_key_error_handling(
        self,
        deterministic_step_node,
        flow_state,
        component_name,
        mock_toolset,
        mock_internal_event_client,
        ui_history,
        mock_tool_monitoring,
        flow_type,
        mock_get_vars_from_state,
    ):
        """Test run handles KeyError during tool execution."""
        # Configure toolset to raise KeyError
        key_error = KeyError("missing_key")
        mock_toolset.__getitem__ = Mock(side_effect=key_error)

        result = await deterministic_step_node.run(flow_state)

        # Verify error message in result
        assert FlowStateKeys.CONTEXT in result
        assert component_name in result[FlowStateKeys.CONTEXT]
        assert result[FlowStateKeys.CONTEXT][component_name]["tool_result"] is None
        error_msg = result[FlowStateKeys.CONTEXT][component_name]["error"]
        assert "Tool test_tool raised key error" in error_msg

        # Verify internal event tracking for failure
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Verify tool error metric was called
        mock_tool_monitoring.count_agent_platform_tool_failure.assert_called_once_with(
            flow_type=flow_type.value,
            tool_name="test_tool",
            failure_reason="KeyError",
        )

    @pytest.mark.asyncio
    async def test_run_generic_exception_handling(
        self,
        deterministic_step_node,
        flow_state,
        component_name,
        mock_tool,
        mock_internal_event_client,
        ui_history,
        mock_tool_monitoring,
        flow_type,
        mock_get_vars_from_state,
    ):
        """Test run handles generic exceptions during tool execution."""
        # Configure tool to raise generic exception
        generic_error = Exception("Generic error")
        mock_tool.arun = AsyncMock(side_effect=generic_error)

        result = await deterministic_step_node.run(flow_state)

        # Verify error message in result
        assert FlowStateKeys.CONTEXT in result
        assert component_name in result[FlowStateKeys.CONTEXT]
        assert result[FlowStateKeys.CONTEXT][component_name]["tool_result"] is None
        error_msg = result[FlowStateKeys.CONTEXT][component_name]["error"]
        assert "Tool runtime exception due to Generic error" in error_msg

        # Verify internal event tracking for failure
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Verify tool error metric was called
        mock_tool_monitoring.count_agent_platform_tool_failure.assert_called_once_with(
            flow_type=flow_type.value,
            tool_name="test_tool",
            failure_reason="Exception",
        )


class TestDeterministicStepNodeMonitoring:
    """Test suite for DeterministicStepNode monitoring functionality."""

    @pytest.mark.asyncio
    async def test_monitoring_success(
        self,
        deterministic_step_node,
        flow_state,
        mock_tool,
        mock_tool_monitoring,
        flow_type,
        mock_get_vars_from_state,
    ):
        """Test monitoring for successful tool execution."""
        await deterministic_step_node.run(flow_state)

        # Verify monitoring was called
        mock_tool_monitoring.time_tool_call.assert_called_once_with(
            tool_name="test_tool",
            flow_type=flow_type.value,
        )

    @pytest.mark.asyncio
    async def test_monitoring_with_error(
        self,
        deterministic_step_node,
        flow_state,
        mock_tool,
        mock_tool_monitoring,
        flow_type,
        mock_get_vars_from_state,
    ):
        """Test monitoring when tool execution fails."""
        # Configure tool to raise exception
        mock_tool.arun = AsyncMock(side_effect=Exception("Tool error"))

        await deterministic_step_node.run(flow_state)

        # Verify monitoring was still called despite error
        mock_tool_monitoring.time_tool_call.assert_called_once_with(
            tool_name="test_tool",
            flow_type=flow_type.value,
        )


class TestDeterministicStepNodeEventTracking:
    """Test suite for DeterministicStepNode internal event tracking."""

    @pytest.mark.asyncio
    async def test_tracks_success_event(
        self,
        deterministic_step_node,
        flow_state,
        mock_tool,
        mock_internal_event_client,
        flow_id,
        flow_type,
        mock_get_vars_from_state,
    ):
        """Test tracking success event."""
        await deterministic_step_node.run(flow_state)

        # Verify internal event tracking for success
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_SUCCESS.value
        assert call_args[1]["category"] == flow_type.value

        # Verify additional properties
        additional_props = call_args[1]["additional_properties"]
        assert hasattr(additional_props, "property")
        assert additional_props.property == "test_tool"
        assert hasattr(additional_props, "value")
        assert additional_props.value == flow_id

    @pytest.mark.asyncio
    async def test_tracks_failure_event_with_extra_data(
        self,
        deterministic_step_node,
        flow_state,
        mock_tool,
        mock_internal_event_client,
        mock_get_vars_from_state,
    ):
        """Test tracking failure event with extra error data."""
        # Configure tool to raise exception
        error_message = "Specific tool error"
        mock_tool.arun = AsyncMock(side_effect=Exception(error_message))

        await deterministic_step_node.run(flow_state)

        # Verify internal event tracking includes error details
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Check that additional_properties contains error information
        additional_props = call_args[1]["additional_properties"]
        assert hasattr(additional_props, "property")
        assert additional_props.property == "test_tool"
        assert hasattr(additional_props, "extra")
        assert additional_props.extra["error"] == error_message
        assert additional_props.extra["error_type"] == "Exception"


class TestDeterministicStepNodeEdgeCases:
    """Test suite for edge cases in DeterministicStepNode."""

    @pytest.mark.asyncio
    async def test_run_with_empty_tool_args(
        self,
        deterministic_step_node,
        flow_state,
        mock_tool,
        mock_get_vars_from_state,
    ):
        """Test run with empty tool arguments."""
        mock_get_vars_from_state.return_value = {}

        result = await deterministic_step_node.run(flow_state)

        # Verify tool was called with empty args
        mock_tool.arun.assert_called_once_with({})

    @pytest.mark.asyncio
    async def test_run_with_tool_without_schema(
        self,
        deterministic_step_node,
        flow_state,
        mock_tool,
        mock_get_vars_from_state,
    ):
        """Test TypeError formatting when tool has no args_schema."""
        # Configure tool with no schema
        mock_tool.args_schema = None
        mock_tool.arun = AsyncMock(side_effect=TypeError("No args"))

        result = await deterministic_step_node.run(flow_state)

        # Verify error message mentions no arguments
        error_msg = result[FlowStateKeys.CONTEXT]["test_component"]["error"]
        assert "The tool does not accept any argument" in error_msg

    @pytest.mark.asyncio
    async def test_ui_history_state_updates(
        self,
        deterministic_step_node,
        flow_state,
        ui_history,
        mock_get_vars_from_state,
    ):
        """Test that UI history state updates are properly merged."""
        # Configure ui_history to return state updates
        ui_state_updates = {
            "ui_messages": ["message1", "message2"],
            "ui_state": {"key": "value"},
        }
        ui_history.pop_state_updates.return_value = ui_state_updates

        result = await deterministic_step_node.run(flow_state)

        # Verify UI state updates are included in result
        assert "ui_messages" in result
        assert result["ui_messages"] == ["message1", "message2"]
        assert "ui_state" in result
        assert result["ui_state"] == {"key": "value"}
        assert FlowStateKeys.CONTEXT in result
