from unittest.mock import patch

import pytest

from duo_workflow_service.tracking.sentry_error_tracking import (
    catch_asyncio_warnings,
    remove_private_info_fields,
)


@pytest.mark.parametrize(
    "event,expected_changes",
    [
        # Test server_name removal
        (
            {
                "server_name": "sensitive-server-name",
                "message": "Test error message",
                "other_field": "keep this",
            },
            {"server_name": None},
        ),
        # Test event without server_name
        ({"message": "Test error message", "other_field": "keep this"}, {}),
        # Test preserving other fields
        (
            {
                "server_name": "server123",
                "user": {"id": "user123"},
                "extra": {"key": "value"},
                "tags": {"env": "test"},
            },
            {"server_name": None},
        ),
    ],
)
def test_remove_private_info_fields(event, expected_changes):
    """Test that private information is removed correctly."""
    original_event = event.copy()
    result = remove_private_info_fields(event)

    # Check expected changes
    for key, expected_value in expected_changes.items():
        assert result[key] == expected_value

    # Check that other fields are preserved
    for key, value in original_event.items():
        if key not in expected_changes:
            assert result[key] == value


@pytest.mark.parametrize(
    (
        "event",
        "expected_result",
        "expected_workflow_id",
        "should_call_metrics",
    ),
    [
        # Asyncio warning with workflow ID
        (
            {
                "logger": "asyncio",
                "logentry": {"message": "Task was destroyed but it is pending!"},
                "breadcrumbs": {
                    "values": [{"data": {"workflow_id": "test-workflow-123"}}]
                },
            },
            None,  # Filtered out
            "test-workflow-123",
            True,
        ),
        # Asyncio warning without workflow ID
        (
            {
                "logger": "asyncio",
                "logentry": {"message": "Task was destroyed but it is pending!"},
                "breadcrumbs": {"values": []},
            },
            None,  # Filtered out
            "unknown",
            True,
        ),
        # Non-asyncio event
        (
            {
                "logger": "other_logger",
                "logentry": {"message": "Some other error message"},
            },
            "unchanged",  # Pass through
            None,
            False,
        ),
        # Asyncio event without task warning
        (
            {
                "logger": "asyncio",
                "logentry": {"message": "Some other asyncio message"},
            },
            "unchanged",  # Pass through
            None,
            False,
        ),
        # Workflow ID with 'undefined' value (should use next valid one)
        (
            {
                "logger": "asyncio",
                "logentry": {"message": "Task was destroyed but it is pending!"},
                "breadcrumbs": {
                    "values": [
                        {"data": {"workflow_id": "undefined"}},
                        {"data": {"workflow_id": "real-workflow-456"}},
                    ]
                },
            },
            None,  # Filtered out
            "real-workflow-456",
            True,
        ),
        # Missing breadcrumbs
        (
            {
                "logger": "asyncio",
                "logentry": {"message": "Task was destroyed but it is pending!"},
            },
            None,  # Filtered out
            "unknown",
            True,
        ),
    ],
)
@patch("duo_workflow_service.tracking.sentry_error_tracking.duo_workflow_metrics")
def test_catch_asyncio_warnings(
    mock_metrics,
    event,
    expected_result,
    expected_workflow_id,
    should_call_metrics,
):
    """Test catching and filtering asyncio warnings with various scenarios."""
    result = catch_asyncio_warnings(event)

    if expected_result == "unchanged":
        assert result == event
    else:
        assert result == expected_result

    if should_call_metrics:
        mock_metrics.count_asyncio_warning.assert_called_once_with(
            type="pending_task_destroyed", workflow_id=expected_workflow_id
        )
    else:
        mock_metrics.count_asyncio_warning.assert_not_called()
