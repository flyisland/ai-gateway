import json
from unittest.mock import Mock

import pytest

from duo_workflow_service.tracking.sentry_error_tracking import (
    filter_checkpoint_errors,
    remove_private_info_fields,
    sentry_filtering_before_send,
)


@pytest.fixture
def test_event():
    return {"event_id": "test-event-id", "message": "JSON decode error"}


@pytest.fixture
def test_json_error():
    return json.JSONDecodeError("Expecting value", "invalid json", 0)


def create_mock_traceback(method_name, filename, tb_next=None):
    mock_frame = Mock()
    mock_frame.f_code.co_name = method_name
    mock_frame.f_code.co_filename = filename
    mock_traceback = Mock()
    mock_traceback.tb_frame = mock_frame
    mock_traceback.tb_next = tb_next
    return mock_traceback


def test_remove_private_info_fields_removes_server_name():
    """Test that server_name is removed from events."""
    event = {
        "event_id": "test-event-id",
        "server_name": "sensitive-server-name",
        "message": "Some error message",
    }
    result = remove_private_info_fields(event)
    assert result["server_name"] is None
    assert result["event_id"] == "test-event-id"
    assert result["message"] == "Some error message"


def test_remove_private_info_fields_no_server_name():
    """Test that events without server_name are handled correctly."""
    event = {"event_id": "test-event-id", "message": "Some error message"}
    result = remove_private_info_fields(event)
    assert result == event
    assert "server_name" not in result


def test_sentry_filtering_before_send_calls_remove_private_info():
    """Test that sentry_filtering_before_send calls remove_private_info_fields."""
    event = {
        "event_id": "test-event-id",
        "server_name": "sensitive-server-name",
        "message": "Some error message",
    }
    hint = {}
    result = sentry_filtering_before_send(event, hint)
    assert result["server_name"] is None
    assert result["event_id"] == "test-event-id"
    assert result["message"] == "Some error message"


@pytest.mark.parametrize(
    "path,method_name,should_filter",
    [
        ("/api/v4/ai/duo_workflows/workflows/123/checkpoints", "_parse_response", True),
        (
            "/api/v4/ai/duo_workflows/workflows/456/checkpoints?per_page=1",
            "_parse_response",
            True,
        ),
        (
            "/api/v4/ai/duo_workflows/workflows/789/checkpoint_writes_batch",
            "_parse_response",
            False,
        ),
        ("/api/v4/ai/duo_workflows/workflows/999/executions", "_parse_response", False),
        ("/api/v4/projects/123/issues", "_parse_response", False),
        ("/api/v4/users", "_parse_response", False),
        (
            "/api/v4/ai/duo_workflows/workflows/123/checkpoints",
            "some_other_method",
            False,
        ),
    ],
)
def test_filter_checkpoint_errors(path, method_name, should_filter):
    """Parametrized test for different path combinations and traceback scenarios."""
    event = {
        "event_id": "test-event-id",
        "message": "JSON decode error",
        "extra": {"path": path},
    }
    json_error = json.JSONDecodeError("Expecting value", "invalid json", 0)

    # Create traceback with the specified method name
    traceback = create_mock_traceback(
        method_name=method_name,
        filename="/path/to/some/file.py",
        tb_next=None,
    )

    hint = {"exc_info": (json.JSONDecodeError, json_error, traceback)}
    result = filter_checkpoint_errors(event, hint)
    if should_filter:
        assert result is None, f"Expected filtering for path={path}"
    else:
        assert result == event, f"Expected no filtering for path={path}"


def test_filter_checkpoint_errors_without_exc_info():
    """Test that events without exc_info in hint are not filtered."""
    event = {"event_id": "test-event-id", "message": "Some error"}
    hint = {"some_other_key": "some_value"}
    result = filter_checkpoint_errors(event, hint)
    assert result == event
