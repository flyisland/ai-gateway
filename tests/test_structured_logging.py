from contextlib import ExitStack
from types import SimpleNamespace
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pytest
import structlog
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette_context.middleware import RawContextMiddleware
from structlog.testing import capture_logs

from ai_gateway.api.middleware import AccessLogMiddleware
from ai_gateway.model_metadata import ModelMetadata
from ai_gateway.structured_logging import prevent_logging_if_disabled, sanitize_logs


class TestSanitizeLogs:
    @pytest.fixture(name="inputs_with_model_metadata", scope="class")
    def inputs_with_model_metadata_fixture(self):
        inputs = MagicMock(
            model_metadata=ModelMetadata(
                name="mistral",
                provider="openai",
                api_key="secret-key-456",
                endpoint="https://example.com",
            ),
            other_fied="other_value",
        )

        return inputs

    def test_sanitize_api_key(self):
        # Test when api_key is present
        event_dict = {"api_key": "secret-key-123"}
        result = sanitize_logs(None, None, event_dict)
        assert result["api_key"] == "**********"

    def test_sanitize_missing_api_key(self):
        # Test when api_key is not present
        event_dict = {"other_field": "value"}
        result = sanitize_logs(None, None, event_dict)
        assert result["api_key"] is None

    def test_sanitize_inputs_with_model_metadata(self, inputs_with_model_metadata):
        event_dict = {"inputs": inputs_with_model_metadata}

        result = sanitize_logs(None, None, event_dict)

        assert result["inputs"].model_metadata.api_key == "**********"
        assert str(result["inputs"].model_metadata.endpoint) == "https://example.com/"
        assert result["inputs"].other_fied == "other_value"

    def test_sanitize_inputs_without_model_metadata(self):
        # Test when inputs exist but without model_metadata
        inputs = SimpleNamespace(other_field="test")
        event_dict = {"inputs": inputs}

        result = sanitize_logs(None, None, event_dict)
        assert result["inputs"].other_field == "test"

    def test_sanitize_no_inputs(self):
        # Test when no inputs field exists
        event_dict = {"some_field": "value"}
        result = sanitize_logs(None, None, event_dict)
        assert "inputs" not in result
        assert result["some_field"] == "value"


class TestPreventLoggingIfDisabled:
    class Case(NamedTuple):
        enable_request_logging: bool
        custom_models_enabled: bool
        enabled_instance_verbose_ai_logs: bool
        feature_flag_enabled: bool

    def _setup_logging_patches(self, case):
        """Helper method to set up common patches for logging tests."""
        return [
            patch(
                "ai_gateway.structured_logging.ENABLE_REQUEST_LOGGING",
                case.enable_request_logging,
            ),
            patch(
                "ai_gateway.structured_logging.CUSTOM_MODELS_ENABLED",
                case.custom_models_enabled,
            ),
            patch(
                "ai_gateway.structured_logging.is_feature_enabled",
                return_value=case.feature_flag_enabled,
            ),
            patch(
                "ai_gateway.structured_logging.enabled_instance_verbose_ai_logs",
                return_value=case.enabled_instance_verbose_ai_logs,
            ),
        ]

    CASES_WHERE_LOGS_SHOULD_NOT_BE_DROPPED = [
        # request logging enabled at AIGW level
        Case(
            enable_request_logging=True,
            custom_models_enabled=False,
            enabled_instance_verbose_ai_logs=False,
            feature_flag_enabled=False,
        ),
        # request logging disabled, custom models enabled, enabled_instance_verbose_ai_logs enabled
        Case(
            enable_request_logging=False,
            custom_models_enabled=True,
            enabled_instance_verbose_ai_logs=True,
            feature_flag_enabled=False,
        ),
        # request logging disabled, custom models disabled, feature flag enabled
        Case(
            enable_request_logging=False,
            custom_models_enabled=False,
            enabled_instance_verbose_ai_logs=False,
            feature_flag_enabled=True,
        ),
    ]

    @pytest.mark.parametrize("case", CASES_WHERE_LOGS_SHOULD_NOT_BE_DROPPED)
    def test_events_are_not_dropped(self, case):
        with ExitStack() as stack:
            for logging_patch in self._setup_logging_patches(case):
                stack.enter_context(logging_patch)
            event_dict = {"key": "value"}
            result = prevent_logging_if_disabled(None, None, event_dict)
            assert result == event_dict

    CASES_WHERE_LOGS_SHOULD_BE_DROPPED = [
        # request logging disabled, custom models disabled, enabled_instance_verbose_ai_logs enabled
        Case(
            enable_request_logging=False,
            custom_models_enabled=False,
            enabled_instance_verbose_ai_logs=True,
            feature_flag_enabled=False,
        ),
        # request logging disabled, custom models enabled, feature flag enabled
        Case(
            enable_request_logging=False,
            custom_models_enabled=True,
            enabled_instance_verbose_ai_logs=False,
            feature_flag_enabled=True,
        ),
    ]

    @pytest.mark.parametrize("case", CASES_WHERE_LOGS_SHOULD_BE_DROPPED)
    def test_logging_disabled(self, case):
        with ExitStack() as stack:
            for logging_patch in self._setup_logging_patches(case):
                stack.enter_context(logging_patch)
            with pytest.raises(structlog.DropEvent):
                prevent_logging_if_disabled(None, None, {"key": "value"})


class TestAccessLogEventContext:
    """Test event context integration with access logging."""

    @pytest.fixture(name="test_app")
    def test_app_fixture(self):
        """Create a test app with AccessLogMiddleware for testing."""

        def success_endpoint(request):  # pylint: disable=unused-argument
            return JSONResponse({"message": "success"})

        app = Starlette(
            middleware=[
                Middleware(RawContextMiddleware),
                Middleware(AccessLogMiddleware, skip_endpoints=[]),
            ],
            routes=[
                Route("/success", endpoint=success_endpoint, methods=["GET"]),
            ],
        )
        return TestClient(app)

    @patch("ai_gateway.api.middleware.base.current_event_context")
    def test_event_context_attributes_logged_when_available(
        self, mock_current_event_context, test_app
    ):
        """Test that event context attributes are included in access logs when available."""
        # Import here to avoid import-outside-toplevel warning
        from lib.internal_events.context import (  # pylint: disable=import-outside-toplevel
            EventContext,
        )

        # Setup event context with test data
        test_event_context = EventContext(
            instance_id="test-instance-123",
            host_name="gitlab.example.com",
            realm="saas",
            is_gitlab_team_member=True,
            global_user_id="user-456",
            correlation_id="corr-789",
        )
        mock_current_event_context.get.return_value = test_event_context

        with capture_logs() as cap_logs:
            response = test_app.get("/success")
            assert response.status_code == 200

        # Verify event context fields were included
        assert cap_logs[0]["event_context_instance_id"] == "test-instance-123"
        assert cap_logs[0]["event_context_host_name"] == "gitlab.example.com"
        assert cap_logs[0]["event_context_realm"] == "saas"
        assert cap_logs[0]["is_gitlab_team_member"] == "True"
        assert cap_logs[0]["event_context_global_user_id"] == "user-456"
        assert cap_logs[0]["event_context_correlation_id"] == "corr-789"

        # Verify standard fields are still present
        assert "url" in cap_logs[0]
        assert "status_code" in cap_logs[0]
        assert "method" in cap_logs[0]
        assert "duration_s" in cap_logs[0]

    @patch("ai_gateway.api.middleware.base.current_event_context")
    def test_event_context_attributes_not_logged_when_unavailable(
        self, mock_current_event_context, test_app
    ):
        """Test that access logging handles missing event context gracefully."""
        # Setup event context to return None
        mock_current_event_context.get.return_value = None

        with capture_logs() as cap_logs:
            response = test_app.get("/success")
            assert response.status_code == 200

        # Verify event context fields are not present
        assert "event_context_instance_id" not in cap_logs[0]
        assert "event_context_host_name" not in cap_logs[0]
        assert "event_context_realm" not in cap_logs[0]
        assert "is_gitlab_team_member" not in cap_logs[0]
        assert "event_context_global_user_id" not in cap_logs[0]
        assert "event_context_correlation_id" not in cap_logs[0]

        # Verify standard fields are still present
        assert "url" in cap_logs[0]
        assert "status_code" in cap_logs[0]
        assert "method" in cap_logs[0]
        assert "duration_s" in cap_logs[0]

    @patch("ai_gateway.api.middleware.base.current_event_context")
    def test_event_context_attributes_with_partial_data(
        self, mock_current_event_context, test_app
    ):
        """Test that access logging handles partial event context data properly."""
        # Import here to avoid import-outside-toplevel warning
        from lib.internal_events.context import (  # pylint: disable=import-outside-toplevel
            EventContext,
        )

        # Setup event context with some None values
        test_event_context = EventContext(
            instance_id="test-instance-123",
            host_name=None,  # This should not be present in the output
            realm="saas",
            is_gitlab_team_member=None,  # This should not be present in the output
            global_user_id="user-456",
            correlation_id=None,  # This should not be present in the output
        )
        mock_current_event_context.get.return_value = test_event_context

        with capture_logs() as cap_logs:
            response = test_app.get("/success")
            assert response.status_code == 200

        # Verify only non-None event context fields are present
        assert cap_logs[0]["event_context_instance_id"] == "test-instance-123"
        assert (
            "event_context_host_name" not in cap_logs[0]
        )  # None values are not included
        assert cap_logs[0]["event_context_realm"] == "saas"
        assert (
            "is_gitlab_team_member" not in cap_logs[0]
        )  # None values are not included
        assert cap_logs[0]["event_context_global_user_id"] == "user-456"
        assert (
            "event_context_correlation_id" not in cap_logs[0]
        )  # None values are not included
