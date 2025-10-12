import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from duo_workflow_service.components.contradiction_detection.component import (
    ContradictionDetectionComponent,
)
from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    ToolInfo,
    ToolStatus,
    UiChatLog,
    WorkflowState,
)
from lib.internal_events.event_enum import CategoryEnum


class TestLegacyContradictionDetectionComponent:
    """Test suite for legacy ContradictionDetectionComponent."""

    @pytest.fixture
    def mock_workflow_state_with_contradictions(self):
        """Create a mock workflow state with tool responses containing contradictions."""
        tool_response_with_contradiction = json.dumps(
            {
                "title": "Task Completed Successfully",
                "description": "The task failed with multiple errors",
                "status": "completed",
            }
        )

        # Mock ToolMessage-like object
        class MockToolResponse:
            def __init__(self, content):
                self.content = content

        tool_log = {
            "message_type": MessageTypeEnum.TOOL,
            "message_sub_type": "test_tool",
            "content": "Using test_tool",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": ToolStatus.SUCCESS,
            "correlation_id": None,
            "tool_info": ToolInfo(
                name="test_tool",
                args={"test": "arg"},
                tool_response=MockToolResponse(tool_response_with_contradiction),
            ),
            "additional_context": None,
        }

        return {
            "conversation_history": {"agent": []},
            "ui_chat_log": [tool_log],
            "status": "running",
        }

    @pytest.fixture
    def mock_workflow_state_no_contradictions(self):
        """Create a mock workflow state with consistent tool responses."""
        tool_response_consistent = json.dumps(
            {
                "title": "Task Completed Successfully",
                "description": "The task was completed without any issues",
                "status": "completed",
            }
        )

        class MockToolResponse:
            def __init__(self, content):
                self.content = content

        tool_log = {
            "message_type": MessageTypeEnum.TOOL,
            "message_sub_type": "test_tool",
            "content": "Using test_tool",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": ToolStatus.SUCCESS,
            "correlation_id": None,
            "tool_info": ToolInfo(
                name="test_tool",
                args={"test": "arg"},
                tool_response=MockToolResponse(tool_response_consistent),
            ),
            "additional_context": None,
        }

        return {
            "conversation_history": {"agent": []},
            "ui_chat_log": [tool_log],
            "status": "running",
        }

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "true"})
    def test_feature_enabled_detects_contradictions(
        self, mock_workflow_state_with_contradictions
    ):
        """Test that contradictions are detected when feature is enabled."""
        # We can't easily create a full component instance due to dependency injection
        # So we'll test the core logic methods directly

        # Test the environment variable check
        from duo_workflow_service.components.contradiction_detection.component import (
            ContradictionDetectionComponent,
        )

        # Create a minimal mock component to test the methods
        component = object.__new__(ContradictionDetectionComponent)
        component._logger = type(
            "MockLogger",
            (),
            {
                "warning": lambda *args, **kwargs: None,
                "debug": lambda *args, **kwargs: None,
            },
        )()

        # Test the feature flag check
        assert component._is_feature_enabled() is True

        # Test JSON extraction
        test_content = '{"title": "Success", "description": "Failed"}'
        extracted = component._extract_json_from_content(test_content)
        assert extracted == {"title": "Success", "description": "Failed"}

        # Test contradiction detection
        contradictions = component._detect_contradictions_in_data(
            {
                "title": "Task completed successfully",
                "description": "Task failed with errors",
            },
            "test_tool",
        )
        assert len(contradictions) > 0
        assert contradictions[0]["contradiction_type"] == "sentiment_contradiction"

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "false"})
    def test_feature_disabled_skips_analysis(self):
        """Test that analysis is skipped when feature is disabled."""
        component = object.__new__(ContradictionDetectionComponent)
        component._logger = type(
            "MockLogger", (), {"debug": lambda *args, **kwargs: None}
        )()

        assert component._is_feature_enabled() is False

    @patch.dict(os.environ, {}, clear=True)
    def test_feature_default_disabled(self):
        """Test that feature is disabled by default."""
        component = object.__new__(ContradictionDetectionComponent)
        component._logger = type(
            "MockLogger", (), {"debug": lambda *args, **kwargs: None}
        )()

        assert component._is_feature_enabled() is False

    def test_extract_json_from_various_formats(self):
        """Test JSON extraction from different content formats."""
        component = object.__new__(ContradictionDetectionComponent)

        # Direct JSON string
        json_string = '{"title": "Test", "description": "Test description"}'
        result = component._extract_json_from_content(json_string)
        assert result == {"title": "Test", "description": "Test description"}

        # JSON within text
        text_with_json = (
            'Some text {"title": "Test", "description": "Test description"} more text'
        )
        result = component._extract_json_from_content(text_with_json)
        assert result == {"title": "Test", "description": "Test description"}

        # Direct dict
        dict_content = {"title": "Test", "description": "Test description"}
        result = component._extract_json_from_content(dict_content)
        assert result == {"title": "Test", "description": "Test description"}

        # List with dict
        list_content = [{"title": "Test", "description": "Test description"}]
        result = component._extract_json_from_content(list_content)
        assert result == {"title": "Test", "description": "Test description"}

        # Invalid content
        result = component._extract_json_from_content("not json")
        assert result is None

    def test_contradiction_analysis(self):
        """Test the core contradiction analysis logic."""
        component = object.__new__(ContradictionDetectionComponent)

        # Test sentiment contradiction
        contradiction = component._analyze_contradiction(
            "Task completed successfully", "The task failed with errors"
        )
        assert contradiction is not None
        assert contradiction["type"] == "sentiment_contradiction"

        # Test no contradiction
        no_contradiction = component._analyze_contradiction(
            "Task Completed Successfully", "The task was completed without issues"
        )
        assert no_contradiction is None

        # Test action contradiction
        action_contradiction = component._analyze_contradiction(
            "Create New File", "Delete the existing file"
        )
        assert action_contradiction is not None
        assert action_contradiction["type"] == "action_contradiction"

        # Test numerical contradiction
        numerical_contradiction = component._analyze_contradiction(
            "0 Items Found", "Found 5 matching results"
        )
        assert numerical_contradiction is not None
        assert numerical_contradiction["type"] == "numerical_contradiction"

    def test_is_tool_response_detection(self):
        """Test detection of tool response log entries."""
        component = object.__new__(ContradictionDetectionComponent)

        # Mock tool response log
        class MockToolResponse:
            content = "test response"

        tool_info = ToolInfo(
            name="test_tool",
            args={},
            tool_response=MockToolResponse(),
        )

        tool_log = {
            "message_type": MessageTypeEnum.TOOL,
            "message_sub_type": "test_tool",
            "content": "Using test_tool",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": ToolStatus.SUCCESS,
            "correlation_id": None,
            "tool_info": tool_info,
            "additional_context": None,
        }

        # Debug the hasattr check
        print(f"Tool info: {tool_info}")
        print(f"Has tool_response attr: {hasattr(tool_info, 'tool_response')}")
        print(f"Tool response: {getattr(tool_info, 'tool_response', None)}")

        assert component._is_tool_response(tool_log) is True

        # Non-tool log
        non_tool_log = {
            "message_type": MessageTypeEnum.AGENT,
            "message_sub_type": None,
            "content": "Agent message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": ToolStatus.SUCCESS,
            "correlation_id": None,
            "tool_info": None,
            "additional_context": None,
        }

        assert component._is_tool_response(non_tool_log) is False
