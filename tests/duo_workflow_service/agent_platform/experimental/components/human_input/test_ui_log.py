from unittest.mock import Mock

import pytest

from duo_workflow_service.agent_platform.experimental.components.human_input.ui_log import (
    UILogEventsHumanInput,
    UILogWriterHumanInput,
)
from duo_workflow_service.agent_platform.experimental.ui_log import UIHistory
from duo_workflow_service.entities import MessageTypeEnum, ToolStatus, UiChatLog


class TestUILogEventsHumanInput:
    def test_event_naming_convention(self):
        """Test that all events follow the 'on_' naming convention."""
        for event in UILogEventsHumanInput:
            assert event.value.startswith("on_"), f"Event {event.name} should start with 'on_'"
            assert event.name == event.value.upper(), f"Event key {event.name} should be uppercase of value {event.value}"

    def test_required_events_exist(self):
        """Test that required events are defined."""
        assert UILogEventsHumanInput.ON_USER_INPUT_PROMPT == "on_user_input_prompt"
        assert UILogEventsHumanInput.ON_USER_INPUT_RECEIVED == "on_user_input_received"


class TestUILogWriterHumanInput:
    @pytest.fixture
    def log_callback(self):
        return Mock()

    @pytest.fixture
    def writer(self, log_callback):
        return UILogWriterHumanInput(log_callback)

    def test_events_type_property(self, writer):
        """Test that events_type returns correct type."""
        assert writer.events_type == UILogEventsHumanInput

    def test_log_success(self, writer):
        """Test _log_success creates correct UiChatLog."""
        message = "Please provide your input"
        correlation_id = "test_corr_id"
        additional_context = ["context1", "context2"]

        log = writer._log_success(
            message,
            correlation_id=correlation_id,
            additional_context=additional_context,
        )

        assert isinstance(log, UiChatLog)
        assert log.message_type == MessageTypeEnum.REQUEST
        assert log.content == message
        assert log.status == ToolStatus.SUCCESS
        assert log.correlation_id == correlation_id
        assert log.additional_context == additional_context
        assert log.tool_info is None
        assert log.message_sub_type is None
        assert log.timestamp is not None

    def test_log_error(self, writer):
        """Test _log_error creates correct UiChatLog."""
        message = "Error occurred"
        correlation_id = "error_corr_id"

        log = writer._log_error(message, correlation_id=correlation_id)

        assert isinstance(log, UiChatLog)
        assert log.message_type == MessageTypeEnum.REQUEST
        assert log.content == message
        assert log.status == ToolStatus.FAILURE
        assert log.correlation_id == correlation_id
        assert log.tool_info is None
        assert log.message_sub_type is None

    def test_log_warning(self, writer):
        """Test _log_warning creates correct UiChatLog."""
        message = "Warning message"

        log = writer._log_warning(message)

        assert isinstance(log, UiChatLog)
        assert log.message_type == MessageTypeEnum.REQUEST
        assert log.content == message
        assert log.status == ToolStatus.SUCCESS
        assert log.tool_info is None
        assert log.message_sub_type is None

    def test_success_method_via_log(self, writer, log_callback):
        """Test success method through log interface."""
        message = "Test message"
        event = UILogEventsHumanInput.ON_USER_INPUT_PROMPT

        writer.success(message, event=event)

        # Verify callback was called
        log_callback.assert_called_once()
        call_args = log_callback.call_args[0][0]  # Get the _UILogEntry
        
        assert call_args.event == event
        assert call_args.record.content == message
        assert call_args.record.status == ToolStatus.SUCCESS

    def test_error_method_via_log(self, writer, log_callback):
        """Test error method through log interface."""
        message = "Error message"
        event = UILogEventsHumanInput.ON_USER_INPUT_RECEIVED

        writer.error(message, event=event)

        log_callback.assert_called_once()
        call_args = log_callback.call_args[0][0]
        
        assert call_args.event == event
        assert call_args.record.content == message
        assert call_args.record.status == ToolStatus.FAILURE

    def test_warning_method_via_log(self, writer, log_callback):
        """Test warning method through log interface."""
        message = "Warning message"
        event = UILogEventsHumanInput.ON_USER_INPUT_PROMPT

        writer.warning(message, event=event)

        log_callback.assert_called_once()
        call_args = log_callback.call_args[0][0]
        
        assert call_args.event == event
        assert call_args.record.content == message
        assert call_args.record.status == ToolStatus.SUCCESS

    def test_invalid_event_type_raises_error(self, writer):
        """Test that invalid event type raises TypeError."""
        with pytest.raises(TypeError, match="Expected 'event' to be an instance of UILogEventsHumanInput"):
            writer.success("message", event="invalid_event")

    def test_missing_event_raises_error(self, writer):
        """Test that missing event raises ValueError."""
        with pytest.raises(ValueError, match="Missing required keyword argument: 'event'"):
            writer.success("message")


class TestUIHistoryIntegration:
    def test_ui_history_with_human_input_events(self):
        """Test UIHistory integration with HumanInputComponent events."""
        events = [
            UILogEventsHumanInput.ON_USER_INPUT_PROMPT,
            UILogEventsHumanInput.ON_USER_INPUT_RECEIVED,
        ]
        
        ui_history = UIHistory(
            writer_class=UILogWriterHumanInput,
            events=events,
        )

        # Test that writer is properly initialized
        assert isinstance(ui_history.log, UILogWriterHumanInput)
        assert ui_history.log.events_type == UILogEventsHumanInput

        # Test logging an event
        ui_history.log.success(
            "Test prompt",
            event=UILogEventsHumanInput.ON_USER_INPUT_PROMPT,
        )

        # Get state updates
        state_updates = ui_history.pop_state_updates()
        
        assert "ui_chat_log" in state_updates
        ui_logs = state_updates["ui_chat_log"]
        assert len(ui_logs) == 1
        assert ui_logs[0].content == "Test prompt"

    def test_ui_history_filters_events(self):
        """Test that UIHistory only logs configured events."""
        # Only configure ON_USER_INPUT_PROMPT
        events = [UILogEventsHumanInput.ON_USER_INPUT_PROMPT]
        
        ui_history = UIHistory(
            writer_class=UILogWriterHumanInput,
            events=events,
        )

        # Log both events
        ui_history.log.success(
            "Prompt message",
            event=UILogEventsHumanInput.ON_USER_INPUT_PROMPT,
        )
        ui_history.log.success(
            "Received message",
            event=UILogEventsHumanInput.ON_USER_INPUT_RECEIVED,
        )

        # Only the configured event should be in state updates
        state_updates = ui_history.pop_state_updates()
        ui_logs = state_updates["ui_chat_log"]
        
        assert len(ui_logs) == 1
        assert ui_logs[0].content == "Prompt message"

    def test_ui_history_clear_after_pop(self):
        """Test that UIHistory clears logs after pop_state_updates."""
        events = [UILogEventsHumanInput.ON_USER_INPUT_PROMPT]
        
        ui_history = UIHistory(
            writer_class=UILogWriterHumanInput,
            events=events,
        )

        ui_history.log.success(
            "Test message",
            event=UILogEventsHumanInput.ON_USER_INPUT_PROMPT,
        )

        # First pop should return the log
        state_updates1 = ui_history.pop_state_updates()
        assert len(state_updates1["ui_chat_log"]) == 1

        # Second pop should return empty logs
        state_updates2 = ui_history.pop_state_updates()
        assert len(state_updates2["ui_chat_log"]) == 0