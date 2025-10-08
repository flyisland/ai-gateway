import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gitlab_cloud_connector import CloudConnectorUser, UserClaims

from duo_workflow_service.interceptors.authentication_interceptor import current_user
from duo_workflow_service.interceptors.model_metadata_interceptor import (
    ModelMetadataEvalBasedInterceptor,
    ModelMetadataHeaderBasedInterceptor,
    ModelMetadataInterceptor,
)


@pytest.fixture(name="mock_user")
def mock_user_fixture():
    return CloudConnectorUser(True, claims=UserClaims(gitlab_realm="test-realm"))


@pytest.fixture(name="mock_patch_file")
def mock_patch_file_fixture(tmp_path):
    """Create a temporary patch file for testing."""
    import json

    patch_data = {"provider": "gitlab", "name": "gpt_5"}
    patch_file = tmp_path / "patch_model_selection.json"
    with open(patch_file, "w") as f:
        json.dump(patch_data, f)
    return patch_file


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata_value,expected_data,test_case",
    [
        (
            json.dumps(
                {
                    "model": "claude-3-5-sonnet-20240620",
                    "version": "1.0",
                    "provider": "anthropic",
                }
            ),
            {
                "model": "claude-3-5-sonnet-20240620",
                "version": "1.0",
                "provider": "anthropic",
            },
            "sets_metadata",
        ),
        ("null", None, "null_json"),
    ],
)
async def test_header_based_interceptor_processing_scenarios(
    metadata_value, expected_data, test_case, mock_user
):
    """Test that the interceptor processes model metadata correctly for valid scenarios."""
    current_user.set(mock_user)
    interceptor = ModelMetadataHeaderBasedInterceptor()

    handler_call_details = MagicMock()
    handler_call_details.invocation_metadata = [
        ("x-gitlab-agent-platform-model-metadata", metadata_value),
        ("other-header", "other-value"),
    ]

    continuation = AsyncMock()
    continuation.return_value = "mocked_response"

    with (
        patch(
            "duo_workflow_service.interceptors.model_metadata_interceptor.create_model_metadata"
        ) as mock_create,
        patch(
            "duo_workflow_service.interceptors.model_metadata_interceptor.current_model_metadata_context"
        ) as mock_context,
    ):

        mock_model_metadata = MagicMock()
        mock_create.return_value = mock_model_metadata

        result = await interceptor.intercept_service(continuation, handler_call_details)

        mock_create.assert_called_once_with(expected_data)
        mock_context.set.assert_called_once_with(mock_model_metadata)
        continuation.assert_called_once_with(handler_call_details)
        assert result == "mocked_response"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invocation_metadata,test_case",
    [
        ([("other-header", "other-value")], "no_metadata_header"),
        (
            [
                ("x-gitlab-agent-platform-model-metadata", ""),
                ("other-header", "other-value"),
            ],
            "empty_metadata",
        ),
        (
            [
                ("x-gitlab-agent-platform-model-metadata", "invalid-json{"),
                ("other-header", "other-value"),
            ],
            "invalid_json",
        ),
    ],
)
async def test_header_based_interceptor_no_processing_scenarios(
    invocation_metadata, test_case
):
    """Test that the interceptor handles cases where no model metadata processing occurs."""
    interceptor = ModelMetadataHeaderBasedInterceptor()

    handler_call_details = MagicMock()
    handler_call_details.invocation_metadata = invocation_metadata

    continuation = AsyncMock()
    continuation.return_value = "mocked_response"

    with (
        patch(
            "duo_workflow_service.interceptors.model_metadata_interceptor.create_model_metadata"
        ) as mock_create,
        patch(
            "duo_workflow_service.interceptors.model_metadata_interceptor.current_model_metadata_context"
        ) as mock_context,
    ):

        result = await interceptor.intercept_service(continuation, handler_call_details)

        mock_create.assert_not_called()
        mock_context.set.assert_not_called()
        continuation.assert_called_once_with(handler_call_details)
        assert result == "mocked_response"


class TestModelMetadataEvalBasedInterceptor:
    @pytest.mark.asyncio
    async def test_try_enable_with_evaluation_env(self, monkeypatch, mock_patch_file):
        """Test that try_enable returns an instance when AIGW_ENVIRONMENT is 'evaluation' and patch file exists."""
        monkeypatch.setenv("AIGW_ENVIRONMENT", "evaluation")

        with patch.object(
            ModelMetadataEvalBasedInterceptor, "PATCH_LOOKUP_PATH", mock_patch_file
        ):
            interceptor = ModelMetadataEvalBasedInterceptor.try_enable()
            assert interceptor is not None
            assert isinstance(interceptor, ModelMetadataEvalBasedInterceptor)

    @pytest.mark.asyncio
    async def test_try_enable_with_non_evaluation_env(
        self, monkeypatch, mock_patch_file
    ):
        """Test that try_enable returns None when AIGW_ENVIRONMENT is not 'evaluation'."""
        monkeypatch.setenv("AIGW_ENVIRONMENT", "production")

        with patch.object(
            ModelMetadataEvalBasedInterceptor, "PATCH_LOOKUP_PATH", mock_patch_file
        ):
            interceptor = ModelMetadataEvalBasedInterceptor.try_enable()
            assert interceptor is None

    @pytest.mark.asyncio
    async def test_try_enable_without_patch_file(self, monkeypatch, tmp_path):
        """Test that try_enable returns None when patch file doesn't exist."""
        monkeypatch.setenv("AIGW_ENVIRONMENT", "evaluation")

        non_existent_file = tmp_path / "non_existent.json"
        with patch.object(
            ModelMetadataEvalBasedInterceptor, "PATCH_LOOKUP_PATH", non_existent_file
        ):
            interceptor = ModelMetadataEvalBasedInterceptor.try_enable()
            assert interceptor is None

    @pytest.mark.asyncio
    async def test_intercept_service(self, mock_patch_file, mock_user):
        """Test that intercept_service loads data from the patch file and sets model metadata."""
        current_user.set(mock_user)

        with patch.object(
            ModelMetadataEvalBasedInterceptor, "PATCH_LOOKUP_PATH", mock_patch_file
        ):
            interceptor = ModelMetadataEvalBasedInterceptor()
            handler_call_details = MagicMock()
            continuation = AsyncMock()
            continuation.return_value = "mocked_response"

            with (
                patch(
                    "duo_workflow_service.interceptors.model_metadata_interceptor.create_model_metadata"
                ) as mock_create,
                patch(
                    "duo_workflow_service.interceptors.model_metadata_interceptor.current_model_metadata_context"
                ) as mock_context,
            ):
                mock_model_metadata = MagicMock()
                mock_create.return_value = mock_model_metadata

                result = await interceptor.intercept_service(
                    continuation, handler_call_details
                )

                mock_create.assert_called_once()
                mock_context.set.assert_called_once_with(mock_model_metadata)
                continuation.assert_called_once_with(handler_call_details)
                assert result == "mocked_response"


class TestModelMetadataInterceptor:
    @pytest.mark.asyncio
    async def test_selection_in_eval_mode(self, monkeypatch, mock_patch_file):
        """Test that ModelMetadataInterceptor selects ModelMetadataEvalBasedInterceptor in eval mode."""
        monkeypatch.setenv("AIGW_ENVIRONMENT", "evaluation")

        with patch.object(
            ModelMetadataEvalBasedInterceptor, "PATCH_LOOKUP_PATH", mock_patch_file
        ):
            interceptor = ModelMetadataInterceptor()
            assert isinstance(
                interceptor.selected_interceptor, ModelMetadataEvalBasedInterceptor
            )

    @pytest.mark.asyncio
    async def test_selection_in_non_eval_mode(self, monkeypatch):
        """Test that ModelMetadataInterceptor selects ModelMetadataHeaderBasedInterceptor in non-eval mode."""
        monkeypatch.setenv("AIGW_ENVIRONMENT", "production")

        interceptor = ModelMetadataInterceptor()
        assert isinstance(
            interceptor.selected_interceptor, ModelMetadataHeaderBasedInterceptor
        )

    @pytest.mark.asyncio
    async def test_model_metadata_interceptor_delegation(
        self, mock_patch_file, mock_user, monkeypatch
    ):
        """Test that the ModelMetadataInterceptor delegates to the selected interceptor."""
        current_user.set(mock_user)
        monkeypatch.setenv("AIGW_ENVIRONMENT", "evaluation")

        with patch.object(
            ModelMetadataEvalBasedInterceptor, "PATCH_LOOKUP_PATH", mock_patch_file
        ):
            interceptor = ModelMetadataInterceptor()

            handler_call_details = MagicMock()
            continuation = AsyncMock()

            with patch.object(
                interceptor.selected_interceptor, "intercept_service"
            ) as mock_intercept:
                mock_intercept.return_value = "test_response"

                result = await interceptor.intercept_service(
                    continuation, handler_call_details
                )

                # Verify that the selected interceptor's method was called
                mock_intercept.assert_called_once_with(
                    continuation, handler_call_details
                )
                assert result == "test_response"
