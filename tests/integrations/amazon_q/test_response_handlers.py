"""
Test cases for the response handlers module.
Tests the processing of various event types and response handling functionality.
"""

from typing import Dict

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from ai_gateway.integrations.amazon_q.response_handlers import (
    ResponseHandler,
    StreamEvent,
    StreamResponse,
)


@pytest.fixture
def response_handler() -> ResponseHandler:
    """Fixture to create a ResponseHandler instance for tests."""
    return ResponseHandler()


class TestResponseHandler:
    """Test suite for ResponseHandler class."""

    # Test Data Setup
    VALID_ASSISTANT_EVENT = {
        "assistantResponseEvent": {"content": "Hello, I can help you with that."}
    }

    VALID_FOLLOWUP_EVENT = {
        "followupPrompt": {"content": "Would you like to know more about AWS services?"}
    }

    VALID_WEBLINKS_EVENT = {
        "supplementaryWebLinks": {"content": "Here are some helpful resources..."}
    }

    VALID_REFERENCES_EVENT = {"references": {"content": "Source: AWS Documentation"}}

    VALID_METADATA_EVENT = {
        "messageMetadataEvent": {"content": "System metadata information"}
    }

    INVALID_EVENT = {"invalidEventType": {"content": "Invalid content"}}

    # Test Process Stream Event
    def test_process_stream_event_with_invalid_input(self, response_handler):
        """Test handling of invalid input types."""
        result = response_handler.process_stream_event(None)
        assert isinstance(result, StreamResponse)
        assert result.error is not None
        assert "Invalid event format" in result.error

    def test_process_stream_event_with_empty_dict(self, response_handler):
        """Test handling of empty dictionary input."""
        result = response_handler.process_stream_event({})
        assert isinstance(result, StreamResponse)
        assert result.content == ""

    # Test Assistant Response Events
    def test_process_assistant_response_valid(self, response_handler):
        """Test processing of valid assistant response events."""
        result = response_handler.process_stream_event(self.VALID_ASSISTANT_EVENT)
        assert result.content == "Hello, I can help you with that."
        assert result.error is None

    def test_process_assistant_response_invalid(self, response_handler):
        """Test processing of invalid assistant response events."""
        invalid_event = {"assistantResponseEvent": {}}
        result = response_handler.process_stream_event(invalid_event)
        assert result.content == ""

    # Test Followup Prompt Events
    def test_process_followup_prompt_valid(self, response_handler):
        """Test processing of valid followup prompt events."""
        result = response_handler.process_stream_event(self.VALID_FOLLOWUP_EVENT)
        assert result.content == "Would you like to know more about AWS services?"
        assert result.error is None

    def test_process_followup_prompt_invalid(self, response_handler):
        """Test processing of invalid followup prompt events."""
        invalid_event = {"followupPrompt": {}}
        result = response_handler.process_stream_event(invalid_event)
        assert result.content == ""

    # Test Web Links Events
    def test_process_web_links_valid(self, response_handler):
        """Test processing of valid web links events."""
        result = response_handler.process_stream_event(self.VALID_WEBLINKS_EVENT)
        assert result.content == "Here are some helpful resources..."
        assert result.error is None

    def test_process_web_links_invalid(self, response_handler):
        """Test processing of invalid web links events."""
        invalid_event = {"supplementaryWebLinks": {}}
        result = response_handler.process_stream_event(invalid_event)
        assert result.content == ""

    # Test References Events
    def test_process_references_valid(self, response_handler):
        """Test processing of valid references events."""
        result = response_handler.process_stream_event(self.VALID_REFERENCES_EVENT)
        assert result.content == "Source: AWS Documentation"
        assert result.error is None

    def test_process_references_invalid(self, response_handler):
        """Test processing of invalid references events."""
        invalid_event = {"references": {}}
        result = response_handler.process_stream_event(invalid_event)
        assert result.content == ""

    # Test Metadata Events
    def test_process_metadata_event(self, response_handler):
        """Test processing of metadata events."""
        result = response_handler.process_stream_event(self.VALID_METADATA_EVENT)
        assert result.content == ""
        assert result.error is None

    # Test Default Event Processing
    def test_process_default_event(self, response_handler):
        """Test processing of unknown event types."""
        result = response_handler.process_stream_event(self.INVALID_EVENT)
        assert isinstance(result, StreamResponse)
        assert result.content == ""

    # Test Chunk Creation
    def test_create_error_chunk(self, response_handler):
        """Test creation of error chunks."""
        error_message = "Test error message"
        chunk = response_handler.create_error_chunk(error_message)
        assert isinstance(chunk, ChatGenerationChunk)
        assert isinstance(chunk.message, AIMessageChunk)
        assert chunk.message.content == f"Error: {error_message}"

    def test_create_content_chunk(self, response_handler):
        """Test creation of content chunks."""
        content = "Test content"
        chunk = response_handler.create_content_chunk(content)
        assert isinstance(chunk, ChatGenerationChunk)
        assert isinstance(chunk.message, AIMessageChunk)
        assert chunk.message.content == content

    # Test Error Handling
    def test_error_handling_with_malformed_event(self, response_handler):
        """Test handling of malformed events."""
        malformed_event = {"assistantResponseEvent": None}
        result = response_handler.process_stream_event(malformed_event)
        assert isinstance(result, StreamResponse)
        assert result.error is not None

    # Test Edge Cases
    @pytest.mark.parametrize(
        "event_input",
        [
            None,
            "",
            [],
            42,
            True,
        ],
    )
    def test_invalid_input_types(self, response_handler, event_input):
        """Test handling of various invalid input types."""
        result = response_handler.process_stream_event(event_input)
        assert isinstance(result, StreamResponse)
        assert result.error is not None
        assert "Invalid event format" in result.error

    def test_empty_content_handling(self, response_handler):
        """Test handling of events with empty content."""
        event = {"assistantResponseEvent": {"content": ""}}
        result = response_handler.process_stream_event(event)
        assert isinstance(result, StreamResponse)
        assert result.content == ""
        assert result.error is None


# Integration Tests
class TestResponseHandlerIntegration:
    """Integration tests for ResponseHandler class."""

    def test_full_conversation_flow(self, response_handler):
        """Test a complete conversation flow with multiple event types."""
        events = [
            {"messageMetadataEvent": {"content": "Conversation started"}},
            {"assistantResponseEvent": {"content": "Hello! How can I help?"}},
            {"followupPrompt": {"content": "Would you like to learn more?"}},
            {"supplementaryWebLinks": {"content": "Additional resources..."}},
            {"references": {"content": "Documentation references"}},
        ]

        responses = [response_handler.process_stream_event(event) for event in events]

        assert all(isinstance(response, StreamResponse) for response in responses)
        assert responses[0].content == ""  # metadata event
        assert responses[1].content == "Hello! How can I help?"
        assert responses[2].content == "Would you like to learn more?"
        assert responses[3].content == "Additional resources..."
        assert responses[4].content == "Documentation references"
