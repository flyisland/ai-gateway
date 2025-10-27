from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic_core import ValidationError

from duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node import (
    ToolNode,
)
from duo_workflow_service.agent_platform.experimental.components.agent.ui_log import (
    UILogEventsAgent,
)
from duo_workflow_service.agent_platform.experimental.state import FlowStateKeys, IOKey
from duo_workflow_service.security.prompt_security import SecurityException
from lib.internal_events.event_enum import CategoryEnum, EventEnum


@pytest.fixture(name="mock_prompt_security")
def mock_prompt_security_fixture():
    """Fixture for mocking PromptSecurity."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.PromptSecurity"
    ) as mock_security:
        mock_security.apply_security_to_tool_response.return_value = (
            "Sanitized response"
        )
        yield mock_security


@pytest.fixture(name="mock_logger")
def mock_logger_fixture():
    """Fixture for mocking structlog logger."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.structlog"
    ) as mock_structlog:
        mock_logger = Mock()
        mock_structlog.stdlib.get_logger.return_value = mock_logger
        yield mock_logger


@pytest.fixture(name="mock_tool_monitoring")
def mock_tool_monitoring_fixture():
    """Fixture for mocking duo_workflow_metrics for tool operations."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.duo_workflow_metrics"
    ) as mock_metrics:
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_context_manager)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_metrics.time_tool_call.return_value = mock_context_manager
        yield mock_metrics


@pytest.fixture(name="tool_node")
def tool_node_fixture(
    component_name,
    mock_toolset,
    flow_id,
    flow_type,
    ui_history,
    mock_internal_event_client,
    mock_tool_monitoring,
    mock_prompt_security,
    mock_logger,
):
    """Fixture for ToolNode instance."""
    return ToolNode(
        name="test_tool_node",
        component_name=component_name,
        toolset=mock_toolset,
        tool_arguments_binding=[],
        flow_id=flow_id,
        flow_type=flow_type,
        internal_event_client=mock_internal_event_client,
        ui_history=ui_history,
    )


class TestToolNode:
    """Test suite for ToolNode class focusing on the run method."""

    @pytest.mark.asyncio
    async def test_run_success_single_tool_call(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_tool,
        mock_tool_call,
        mock_tool_monitoring,
        mock_prompt_security,
        ui_history,
    ):
        """Test successful run with single tool call."""
        result = await tool_node.run(flow_state_with_tool_calls)

        # Verify result structure
        assert FlowStateKeys.CONVERSATION_HISTORY in result
        assert component_name in result[FlowStateKeys.CONVERSATION_HISTORY]

        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 1
        assert isinstance(tool_messages[0], ToolMessage)
        assert tool_messages[0].tool_call_id == mock_tool_call["id"]

        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert tool_messages[0].content == expected_response

        # Verify tool execution was called
        mock_tool.arun.assert_called_once_with(mock_tool_call["args"])

        # Verify security sanitization was called
        mock_prompt_security.apply_security_to_tool_response.assert_called_once_with(
            response="Tool execution result", tool_name=mock_tool.name
        )

        # Verify ui_history.log.success was called with the correct parameters
        ui_history.log.success.assert_called_once_with(
            tool=mock_tool,
            tool_call_args=mock_tool_call["args"],
            event=UILogEventsAgent.ON_TOOL_EXECUTION_SUCCESS,
        )

        # Verify ui_history.pop_state_updates was called
        ui_history.pop_state_updates.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_success_multiple_tool_calls(
        self,
        tool_node,
        base_flow_state,
        component_name,
        mock_ai_message_with_multiple_tool_calls,
        mock_toolset,
        mock_tool_monitoring,
        mock_prompt_security,
    ):
        """Test successful run with multiple tool calls."""
        # Set up toolset to return different tools
        mock_tool_1 = Mock(spec=BaseTool)
        mock_tool_1.name = "tool_1"
        mock_tool_1.arun = AsyncMock(return_value="Result 1")

        mock_tool_2 = Mock(spec=BaseTool)
        mock_tool_2.name = "tool_2"
        mock_tool_2.arun = AsyncMock(return_value="Result 2")

        def mock_getitem(key):
            if key == "tool_1":
                return mock_tool_1
            elif key == "tool_2":
                return mock_tool_2

        mock_toolset.__getitem__ = Mock(side_effect=mock_getitem)

        # Set up flow state
        state = base_flow_state.copy()
        state["conversation_history"] = {
            component_name: [mock_ai_message_with_multiple_tool_calls]
        }

        result = await tool_node.run(state)

        # Verify result structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 2

        # Verify both tools were called
        mock_tool_1.arun.assert_called_once_with({"param1": "value1"})
        mock_tool_2.arun.assert_called_once_with({"param2": "value2"})

    @pytest.mark.asyncio
    async def test_run_tool_not_found(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_toolset,
        mock_prompt_security,
        mock_tool_call,
    ):
        """Test run when tool is not found in toolset."""
        # Configure toolset to not contain the tool
        mock_toolset.__contains__ = Mock(return_value=False)

        result = await tool_node.run(flow_state_with_tool_calls)

        # Verify error response was created and sanitized
        security_call_args = (
            mock_prompt_security.apply_security_to_tool_response.call_args
        )
        assert "Tool test_tool not found" in security_call_args[1]["response"]

        # Verify response structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 1
        assert isinstance(tool_messages[0], ToolMessage)

        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert tool_messages[0].content == expected_response

    @pytest.mark.asyncio
    async def test_run_type_error_handling(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_tool,
        mock_tool_call,
        mock_prompt_security,
        mock_internal_event_client,
        ui_history,
        mock_tool_monitoring,
        flow_type,
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

        result = await tool_node.run(flow_state_with_tool_calls)

        # Verify error message in result
        security_call_args = (
            mock_prompt_security.apply_security_to_tool_response.call_args
        )
        assert security_call_args[1]["tool_name"] == mock_tool.name
        assert (
            "Tool test_tool execution failed due to wrong arguments"
            in security_call_args[1]["response"]
        )
        assert "The schema is:" in security_call_args[1]["response"]

        # Verify response structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 1
        assert isinstance(tool_messages[0], ToolMessage)

        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert tool_messages[0].content == expected_response

        # Verify internal event tracking for failure
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Verify ui_history.log.error was called with the correct parameters
        ui_history.log.error.assert_called_once_with(
            tool=mock_tool,
            tool_call_args=mock_tool_call["args"],
            event=UILogEventsAgent.ON_TOOL_EXECUTION_FAILED,
        )

        # Verify ui_history.pop_state_updates was called
        ui_history.pop_state_updates.assert_called_once()

        # Verify tool error metric was called
        mock_tool_monitoring.count_agent_platform_tool_failure.assert_called_once_with(
            flow_type=flow_type.value,
            tool_name=mock_tool.name,
            failure_reason=type(type_error).__name__,
        )

    @pytest.mark.asyncio
    async def test_run_validation_error_handling(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_tool,
        mock_tool_call,
        mock_prompt_security,
        mock_internal_event_client,
        ui_history,
        mock_tool_monitoring,
        flow_type,
    ):
        """Test run handles ValidationError during tool execution."""
        # Configure tool to raise ValidationError
        validation_error = ValidationError.from_exception_data(
            "ValidationError",
            [{"type": "missing", "loc": ["field"], "msg": "Field required"}],
        )
        mock_tool.arun = AsyncMock(side_effect=validation_error)

        result = await tool_node.run(flow_state_with_tool_calls)

        # Verify error message in result
        security_call_args = (
            mock_prompt_security.apply_security_to_tool_response.call_args
        )
        assert security_call_args[1]["tool_name"] == mock_tool.name
        assert (
            "Tool test_tool raised validation error"
            in security_call_args[1]["response"]
        )

        # Verify response structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 1
        assert isinstance(tool_messages[0], ToolMessage)

        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert tool_messages[0].content == expected_response

        # Verify internal event tracking for failure
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Verify ui_history.log.error was called with the correct parameters
        ui_history.log.error.assert_called_once_with(
            tool=mock_tool,
            tool_call_args=mock_tool_call["args"],
            event=UILogEventsAgent.ON_TOOL_EXECUTION_FAILED,
        )

        # Verify ui_history.pop_state_updates was called
        ui_history.pop_state_updates.assert_called_once()

        # Verify tool error metric was called
        mock_tool_monitoring.count_agent_platform_tool_failure.assert_called_once_with(
            flow_type=flow_type.value,
            tool_name=mock_tool.name,
            failure_reason=type(validation_error).__name__,
        )

    @pytest.mark.asyncio
    async def test_run_generic_exception_handling(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_tool,
        mock_tool_call,
        mock_prompt_security,
        mock_internal_event_client,
        ui_history,
        mock_tool_monitoring,
        flow_type,
    ):
        """Test run handles generic exceptions during tool execution."""
        # Configure tool to raise generic exception
        generic_error = Exception("Generic error")
        mock_tool.arun = AsyncMock(side_effect=generic_error)

        result = await tool_node.run(flow_state_with_tool_calls)

        # Verify error message in result
        security_call_args = (
            mock_prompt_security.apply_security_to_tool_response.call_args
        )
        assert security_call_args[1]["tool_name"] == mock_tool.name
        assert (
            "Tool runtime exception due to Generic error"
            in security_call_args[1]["response"]
        )

        # Verify response structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 1
        assert isinstance(tool_messages[0], ToolMessage)

        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert tool_messages[0].content == expected_response

        # Verify internal event tracking for failure
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_FAILURE.value

        # Verify ui_history.log.error was called with the correct parameters
        ui_history.log.error.assert_called_once_with(
            tool=mock_tool,
            tool_call_args=mock_tool_call["args"],
            event=UILogEventsAgent.ON_TOOL_EXECUTION_FAILED,
        )

        # Verify ui_history.pop_state_updates was called
        ui_history.pop_state_updates.assert_called_once()

        # Verify tool error metric was called
        mock_tool_monitoring.count_agent_platform_tool_failure.assert_called_once_with(
            flow_type=flow_type.value,
            tool_name=mock_tool.name,
            failure_reason=type(generic_error).__name__,
        )

    @pytest.mark.asyncio
    async def test_run_no_tool_calls(
        self,
        tool_node,
        base_flow_state,
        component_name,
        mock_ai_message_no_tool_calls,
    ):
        """Test run with message that has no tool calls."""
        state = base_flow_state.copy()
        state["conversation_history"] = {
            component_name: [mock_ai_message_no_tool_calls]
        }

        result = await tool_node.run(state)

        # Verify result structure with empty tool messages
        assert FlowStateKeys.CONVERSATION_HISTORY in result
        assert component_name in result[FlowStateKeys.CONVERSATION_HISTORY]

        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 0

    @pytest.mark.asyncio
    async def test_run_tool_call_without_args(
        self,
        tool_node,
        base_flow_state,
        component_name,
        mock_tool,
        mock_toolset,
        mock_tool_monitoring,
        mock_prompt_security,
    ):
        """Test run with tool call that has no args."""
        # Create tool call without args
        tool_call_no_args = {
            "name": "test_tool",
            "id": "test_tool_call_id",
        }

        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [tool_call_no_args]

        state = base_flow_state.copy()
        state["conversation_history"] = {component_name: [mock_message]}

        result = await tool_node.run(state)

        # Verify tool was called with empty args
        mock_tool.arun.assert_called_once_with({})

        # Verify result structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 1
        assert isinstance(tool_messages[0], ToolMessage)


class TestToolNodeSecurity:
    """Test suite for ToolNode security functionality."""

    @pytest.mark.asyncio
    async def test_run_security_exception_handling(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_tool,
        mock_logger,
    ):
        """Test run handles SecurityException during response sanitization."""
        # Configure PromptSecurity to raise SecurityException
        security_error = SecurityException("Security validation failed")

        with patch(
            "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.PromptSecurity"
        ) as mock_security:
            mock_security.apply_security_to_tool_response.side_effect = security_error

            with pytest.raises(SecurityException):
                await tool_node.run(flow_state_with_tool_calls)

            # Verify error was logged
            mock_logger.error.assert_called_once()
            assert (
                "Security validation failed for tool test_tool"
                in mock_logger.error.call_args[0][0]
            )

    @pytest.mark.asyncio
    async def test_run_security_sanitization_success(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_tool,
        mock_tool_call,
    ):
        """Test run with successful security sanitization."""
        with patch(
            "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.PromptSecurity"
        ) as mock_security:
            mock_security.apply_security_to_tool_response.return_value = (
                "Sanitized safe response"
            )

            result = await tool_node.run(flow_state_with_tool_calls)

            # Verify sanitization was called
            mock_security.apply_security_to_tool_response.assert_called_once_with(
                response="Tool execution result", tool_name=mock_tool.name
            )

            # Verify response structure
            tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]

            expected_response = (
                "<tool-response>\nSanitized safe response\n</tool-response>"
            )
            assert tool_messages[0].content == expected_response


class TestToolNodeMonitoring:
    """Test suite for ToolNode monitoring functionality."""

    @pytest.mark.asyncio
    async def test_run_monitoring_success(
        self,
        tool_node,
        flow_state_with_tool_calls,
        mock_tool,
        mock_tool_monitoring,
    ):
        """Test run method monitoring for successful tool execution."""
        await tool_node.run(flow_state_with_tool_calls)

        # Verify monitoring was called
        mock_tool_monitoring.time_tool_call.assert_called_once_with(
            tool_name=mock_tool.name,
            flow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT.value,
        )

    @pytest.mark.asyncio
    async def test_run_monitoring_with_error(
        self,
        tool_node,
        flow_state_with_tool_calls,
        mock_tool,
        mock_tool_monitoring,
    ):
        """Test run method monitoring when tool execution fails."""
        # Configure tool to raise exception
        mock_tool.arun = AsyncMock(side_effect=Exception("Tool error"))

        await tool_node.run(flow_state_with_tool_calls)

        # Verify monitoring was still called despite error
        mock_tool_monitoring.time_tool_call.assert_called_once_with(
            tool_name=mock_tool.name,
            flow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT.value,
        )


class TestToolNodeEventTracking:
    """Test suite for ToolNode internal event tracking."""

    @pytest.mark.asyncio
    async def test_run_tracks_success_event(
        self,
        tool_node,
        flow_state_with_tool_calls,
        mock_tool,
        mock_internal_event_client,
        flow_id,
    ):
        """Test run method tracks success event."""
        await tool_node.run(flow_state_with_tool_calls)

        # Verify internal event tracking for success
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args
        assert call_args[1]["event_name"] == EventEnum.WORKFLOW_TOOL_SUCCESS.value
        assert call_args[1]["category"] == CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT

    @pytest.mark.asyncio
    async def test_run_tracks_failure_event_with_extra_data(
        self,
        tool_node,
        flow_state_with_tool_calls,
        mock_tool,
        mock_internal_event_client,
    ):
        """Test run method tracks failure event with extra error data."""
        # Configure tool to raise exception
        error_message = "Specific tool error"
        mock_tool.arun = AsyncMock(side_effect=Exception(error_message))

        await tool_node.run(flow_state_with_tool_calls)

        # Verify internal event tracking includes error details
        mock_internal_event_client.track_event.assert_called_once()
        call_args = mock_internal_event_client.track_event.call_args

        # Check that additional_properties contains error information
        additional_props = call_args[1]["additional_properties"]
        assert hasattr(additional_props, "property")
        assert additional_props.property == mock_tool.name


class TestToolNodeArgumentBinding:
    """Test suite for ToolNode tool_arguments_binding security feature."""

    @pytest.fixture(name="tool_node_with_binding")
    def tool_node_with_binding_fixture(
        self,
        component_name,
        mock_toolset,
        flow_id,
        flow_type,
        ui_history,
        mock_internal_event_client,
        mock_tool_monitoring,
        mock_prompt_security,
        mock_logger,
    ):
        """Fixture for ToolNode instance with argument binding."""
        binding = [
            IOKey(target="context", subkeys=["project_id"]),
            IOKey(target="context", subkeys=["branch_name"], alias="ref"),
        ]
        return ToolNode(
            name="test_tool_node",
            component_name=component_name,
            toolset=mock_toolset,
            tool_arguments_binding=binding,
            flow_id=flow_id,
            flow_type=flow_type,
            internal_event_client=mock_internal_event_client,
            ui_history=ui_history,
        )

    @pytest.fixture(name="flow_state_with_bound_values")
    def flow_state_with_bound_values_fixture(self, base_flow_state, component_name):
        """Fixture for flow state with bound values and tool calls."""
        state = base_flow_state.copy()
        state["context"] = {
            "project_id": 42,
            "branch_name": "main",
            "other_value": "test",
        }

        # Create tool call that attempts to override bound values
        mock_tool_call = {
            "name": "test_tool",
            "args": {
                "project_id": 999,  # Agent tries to access different project
                "ref": "evil-branch",  # Agent tries to access different branch
                "other_param": "value",
            },
            "id": "test_tool_call_id",
        }

        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_tool_call]

        state["conversation_history"] = {component_name: [mock_message]}
        return state

    @pytest.mark.asyncio
    async def test_argument_binding_overrides_agent_values(
        self,
        tool_node_with_binding,
        flow_state_with_bound_values,
        component_name,
        mock_tool,
    ):
        """Test that argument bindings override agent-provided values."""
        # Mock PromptSecurity to allow us to verify the complete response structure
        with patch(
            "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.PromptSecurity"
        ) as mock_security:
            # Return different values for response and instructions sanitization
            mock_security.apply_security_to_tool_response.side_effect = [
                "Sanitized tool result",
                "Sanitized security instructions",
            ]

            result = await tool_node_with_binding.run(flow_state_with_bound_values)

        # Verify tool was called with bound values, not agent values
        call_args = mock_tool.arun.call_args[0][0]
        assert call_args["project_id"] == 42  # Bound value, not 999
        assert call_args["ref"] == "main"  # Bound value via alias, not "evil-branch"
        assert call_args["other_param"] == "value"  # Non-bound param unchanged

        # Verify result contains security instructions with proper structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 1
        response_content = tool_messages[0].content

        expected_response = (
            "<tool-response>\n"
            "Sanitized tool result\n"
            "</tool-response>\n"
            "<instructions>\n"
            "Sanitized security instructions\n"
            "</instructions>"
        )
        assert response_content == expected_response

    @pytest.mark.asyncio
    async def test_argument_binding_no_override_when_values_match(
        self,
        tool_node_with_binding,
        base_flow_state,
        component_name,
        mock_tool,
        mock_prompt_security,
        mock_logger,
    ):
        """Test that no override occurs when agent values match bound values."""
        state = base_flow_state.copy()
        state["context"] = {
            "project_id": 42,
            "branch_name": "main",
        }

        # Create tool call with matching values
        mock_tool_call = {
            "name": "test_tool",
            "args": {
                "project_id": 42,  # Matches bound value
                "ref": "main",  # Matches bound value via alias
            },
            "id": "test_tool_call_id",
        }

        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_tool_call]
        state["conversation_history"] = {component_name: [mock_message]}

        result = await tool_node_with_binding.run(state)

        # Verify tool was called with correct values
        call_args = mock_tool.arun.call_args[0][0]
        assert call_args["project_id"] == 42
        assert call_args["ref"] == "main"

        # Verify no security instructions in response (no override occurred)
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        response_content = tool_messages[0].content

        # Response should only have tool-response wrapper, no instructions
        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert response_content == expected_response
        assert "<instructions>" not in response_content
        assert "SECURITY NOTICE" not in response_content

    @pytest.mark.asyncio
    async def test_argument_binding_missing_parameter_in_tool_call(
        self,
        tool_node_with_binding,
        base_flow_state,
        component_name,
        mock_tool,
        mock_prompt_security,
    ):
        """Test that binding is skipped when parameter is not in tool call."""
        state = base_flow_state.copy()
        state["context"] = {
            "project_id": 42,
            "branch_name": "main",
        }

        # Create tool call without bound parameters
        mock_tool_call = {
            "name": "test_tool",
            "args": {
                "other_param": "value",  # No project_id or ref
            },
            "id": "test_tool_call_id",
        }

        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_tool_call]
        state["conversation_history"] = {component_name: [mock_message]}

        result = await tool_node_with_binding.run(state)

        # Verify tool was called with original args (no binding applied)
        call_args = mock_tool.arun.call_args[0][0]
        assert "project_id" not in call_args
        assert "ref" not in call_args
        assert call_args["other_param"] == "value"

        # Verify no security instructions (no override occurred)
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        response_content = tool_messages[0].content

        # Response should only have tool-response wrapper, no instructions
        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert response_content == expected_response
        assert "<instructions>" not in response_content

    @pytest.mark.asyncio
    async def test_argument_binding_fails_on_missing_state_value(
        self,
        tool_node_with_binding,
        base_flow_state,
        component_name,
        mock_logger,
    ):
        """Test that binding raises RuntimeError when bound value is missing from state."""
        state = base_flow_state.copy()
        state["context"] = {}  # Missing project_id and branch_name

        mock_tool_call = {
            "name": "test_tool",
            "args": {"project_id": 999},
            "id": "test_tool_call_id",
        }

        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_tool_call]
        state["conversation_history"] = {component_name: [mock_message]}

        # Should raise RuntimeError for security enforcement
        with pytest.raises(RuntimeError) as exc_info:
            await tool_node_with_binding.run(state)

        assert "Security enforcement failed" in str(exc_info.value)
        assert "Cannot extract bound value" in str(exc_info.value)

        # Verify security error was logged
        mock_logger.error.assert_called()
        error_log = mock_logger.error.call_args[0][0]
        assert "SECURITY" in error_log
        assert "Failed to extract bound value" in error_log

    @pytest.mark.asyncio
    async def test_argument_binding_with_empty_binding_list(
        self,
        tool_node,
        flow_state_with_tool_calls,
        component_name,
        mock_tool,
    ):
        """Test that empty binding list doesn't affect normal execution."""
        result = await tool_node.run(flow_state_with_tool_calls)

        # Verify tool was called with original args
        mock_tool.arun.assert_called_once()

        # Verify no security instructions
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        response_content = tool_messages[0].content

        # Response should only have tool-response wrapper, no instructions
        expected_response = "<tool-response>\nSanitized response\n</tool-response>"
        assert response_content == expected_response
        assert "<instructions>" not in response_content

    @pytest.mark.asyncio
    async def test_argument_binding_logs_override(
        self,
        tool_node_with_binding,
        flow_state_with_bound_values,
        mock_logger,
    ):
        """Test that argument override is logged."""
        await tool_node_with_binding.run(flow_state_with_bound_values)

        # Verify override was logged
        mock_logger.info.assert_called()
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]

        # Check that override log messages exist
        override_logs = [log for log in log_calls if "tool_arguments_binding" in log]
        assert len(override_logs) > 0

        # Verify log contains parameter details
        assert any("project_id" in log for log in override_logs)

    @pytest.mark.asyncio
    async def test_argument_binding_security_instructions_sanitized(
        self,
        tool_node_with_binding,
        flow_state_with_bound_values,
        component_name,
        mock_tool,
    ):
        """Test that security instructions are also sanitized."""
        with patch(
            "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.PromptSecurity"
        ) as mock_security:
            # First call for tool response, second call for security instructions
            mock_security.apply_security_to_tool_response.side_effect = [
                "Sanitized response",
                "Sanitized instructions",
            ]

            result = await tool_node_with_binding.run(flow_state_with_bound_values)

            # Verify security sanitization was called twice
            assert mock_security.apply_security_to_tool_response.call_count == 2

            # First call: tool response
            first_call = mock_security.apply_security_to_tool_response.call_args_list[0]
            assert first_call[1]["tool_name"] == mock_tool.name

            # Second call: security instructions
            second_call = mock_security.apply_security_to_tool_response.call_args_list[
                1
            ]
            assert "security_instructions" in second_call[1]["tool_name"]
            assert "SECURITY NOTICE" in second_call[1]["response"]

    @pytest.mark.asyncio
    async def test_argument_binding_security_instruction_sanitization_failure(
        self,
        tool_node_with_binding,
        flow_state_with_bound_values,
        component_name,
        mock_logger,
    ):
        """Test that SecurityException is raised if instruction sanitization fails."""
        with patch(
            "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.PromptSecurity"
        ) as mock_security:
            # First call succeeds, second call (instructions) fails
            security_error = SecurityException("Instruction sanitization failed")
            mock_security.apply_security_to_tool_response.side_effect = [
                "Sanitized response",
                security_error,
            ]

            with pytest.raises(SecurityException) as exc_info:
                await tool_node_with_binding.run(flow_state_with_bound_values)

            assert "Instruction sanitization failed" in str(exc_info.value)

            # Verify error was logged
            mock_logger.error.assert_called()
            error_log = mock_logger.error.call_args[0][0]
            assert "SECURITY" in error_log
            assert "Instruction sanitization failed" in error_log

    @pytest.mark.asyncio
    async def test_argument_binding_format_value_for_display(
        self,
        tool_node_with_binding,
        base_flow_state,
        component_name,
        mock_tool,
    ):
        """Test that various value types are formatted correctly in security instructions."""
        state = base_flow_state.copy()
        state["context"] = {
            "project_id": {"nested": "dict"},  # Complex type
            "branch_name": "a" * 150,  # Long string
        }

        mock_tool_call = {
            "name": "test_tool",
            "args": {
                "project_id": 999,
                "ref": "short",
            },
            "id": "test_tool_call_id",
        }

        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_tool_call]
        state["conversation_history"] = {component_name: [mock_message]}

        # Mock PromptSecurity to pass through so we can see the actual formatted values
        with patch(
            "duo_workflow_service.agent_platform.experimental.components.agent.nodes.tool_node.PromptSecurity"
        ) as mock_security:
            # Pass through the actual content so we can verify formatting
            mock_security.apply_security_to_tool_response.side_effect = (
                lambda response, tool_name: response
            )

            result = await tool_node_with_binding.run(state)

        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        response_content = tool_messages[0].content

        # Verify complete response structure
        assert response_content.startswith("<tool-response>\n")
        assert "</tool-response>\n<instructions>\n" in response_content
        assert response_content.endswith("</instructions>")

        # Verify security notice is present
        assert "SECURITY NOTICE" in response_content

        # Verify complex dict values are JSON stringified in the instructions
        assert (
            '{"nested": "dict"}' in response_content or '"nested"' in response_content
        )

        # Verify long strings are truncated to 100 chars (97 + "...")
        assert "..." in response_content  # Truncation indicator
        # The long string should be truncated
        assert "aaa...'" in response_content or 'aaa..."' in response_content

    @pytest.mark.asyncio
    async def test_argument_binding_multiple_tools_in_sequence(
        self,
        tool_node_with_binding,
        base_flow_state,
        component_name,
        mock_toolset,
        mock_prompt_security,
    ):
        """Test that bindings apply correctly to multiple tool calls."""
        state = base_flow_state.copy()
        state["context"] = {
            "project_id": 42,
            "branch_name": "main",
        }

        # Create multiple tools
        mock_tool_1 = Mock(spec=BaseTool)
        mock_tool_1.name = "tool_1"
        mock_tool_1.arun = AsyncMock(return_value="Result 1")

        mock_tool_2 = Mock(spec=BaseTool)
        mock_tool_2.name = "tool_2"
        mock_tool_2.arun = AsyncMock(return_value="Result 2")

        def mock_getitem(key):
            if key == "tool_1":
                return mock_tool_1
            elif key == "tool_2":
                return mock_tool_2

        mock_toolset.__getitem__ = Mock(side_effect=mock_getitem)

        # Both tools attempt to use different project_id
        mock_tool_calls = [
            {
                "name": "tool_1",
                "args": {"project_id": 111},
                "id": "call_1",
            },
            {
                "name": "tool_2",
                "args": {"project_id": 222},
                "id": "call_2",
            },
        ]

        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = mock_tool_calls
        state["conversation_history"] = {component_name: [mock_message]}

        result = await tool_node_with_binding.run(state)

        # Verify both tools were called with bound value
        assert mock_tool_1.arun.call_args[0][0]["project_id"] == 42
        assert mock_tool_2.arun.call_args[0][0]["project_id"] == 42

        # Verify both responses contain security instructions with proper structure
        tool_messages = result[FlowStateKeys.CONVERSATION_HISTORY][component_name]
        assert len(tool_messages) == 2

        for msg in tool_messages:
            # Each response should have both tool-response and instructions sections
            assert msg.content.startswith("<tool-response>\n")
            assert "</tool-response>" in msg.content
            assert "<instructions>" in msg.content
            assert msg.content.endswith("</instructions>")
