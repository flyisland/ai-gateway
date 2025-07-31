from unittest.mock import Mock

import pytest

from duo_workflow_service.agent_platform.experimental.components.human_input.ui_log import (
    UILogEventsHumanInput,
    UILogWriterHumanInput,
)
from duo_workflow_service.entities import MessageTypeEnum
from lib.internal_events import InternalEventsClient


class TestUILogWriterHumanInput:
    """Test suite for UILogWriterHumanInput class."""

    @pytest.fixture
    def mock_internal_event_client(self):
        """Mock internal event client."""
        return Mock(spec=InternalEventsClient)

    @pytest.fixture
    def mock_log_callback(self):
        """Mock log callback function."""
        return Mock()

    @pytest.fixture
    def ui_log_writer(self, mock_log_callback):  # pylint: disable=unused-argument
        """Create UILogWriterHumanInput instance for testing."""
        return UILogWriterHumanInput(
            log_callback=mock_log_callback,
        )

    def test_events_type_property(self, ui_log_writer):
        """Test that events_type property returns correct type."""
        assert ui_log_writer.events_type == UILogEventsHumanInput

    def test_log_success_all_parameters(self, ui_log_writer):
        """Test success log creation with all parameters."""
        content = "Please provide detailed feedback:"
        correlation_id = "test-correlation-456"
        additional_context = {"step": "user_input", "component": "human_input"}

        result = ui_log_writer._log_success(
            content=content,
            correlation_id=correlation_id,
            additional_context=additional_context,
        )

        assert result["content"] == content
        assert result["correlation_id"] == correlation_id
        assert result["additional_context"] == additional_context
        assert result["message_type"] == MessageTypeEnum.AGENT
