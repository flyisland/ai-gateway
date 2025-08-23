from unittest.mock import MagicMock, patch

from ai_gateway.model_metadata import BaseModelMetadata, ModelSelectionMetadata
from duo_workflow_service.agents.model_selection import (
    resolve_model_from_prompt_registry,
)
from lib.feature_flags import FeatureFlag
from lib.internal_events.event_enum import CategoryEnum


class TestResolveModelFromPromptRegistry:
    @patch("duo_workflow_service.agents.model_selection.current_model_metadata_context")
    def test_existing_model_metadata_is_returned(self, mock_context):
        mock_metadata = MagicMock(spec=BaseModelMetadata)
        mock_context.get.return_value = mock_metadata

        result = resolve_model_from_prompt_registry(CategoryEnum.WORKFLOW_CHAT)

        assert result == mock_metadata
        mock_context.get.assert_called_once()

    @patch("duo_workflow_service.agents.model_selection.current_model_metadata_context")
    @patch("duo_workflow_service.agents.model_selection.is_feature_enabled")
    def test_software_development_with_feature_flag_enabled(
        self, mock_is_feature_enabled, mock_context
    ):
        mock_context.get.return_value = None
        mock_is_feature_enabled.return_value = True

        result = resolve_model_from_prompt_registry(
            CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT
        )

        mock_is_feature_enabled.assert_called_once_with(
            FeatureFlag.FLOW_SOFTWARE_DEVELOPMENT_OPENAI_GPT_5
        )
        assert isinstance(result, ModelSelectionMetadata)
        assert result.name == "gpt_5"

    @patch("duo_workflow_service.agents.model_selection.current_model_metadata_context")
    @patch("duo_workflow_service.agents.model_selection.is_feature_enabled")
    def test_chat_with_feature_flag_enabled(
        self, mock_is_feature_enabled, mock_context
    ):
        mock_context.get.return_value = None
        mock_is_feature_enabled.return_value = True

        result = resolve_model_from_prompt_registry(CategoryEnum.WORKFLOW_CHAT)

        mock_is_feature_enabled.assert_called_once_with(
            FeatureFlag.DUO_AGENTIC_CHAT_OPENAI_GPT_5
        )
        assert isinstance(result, ModelSelectionMetadata)
        assert result.name == "gpt_5"

    @patch("duo_workflow_service.agents.model_selection.current_model_metadata_context")
    @patch("duo_workflow_service.agents.model_selection.is_feature_enabled")
    def test_software_development_with_feature_flag_disabled(
        self, mock_is_feature_enabled, mock_context
    ):
        mock_context.get.return_value = None
        mock_is_feature_enabled.return_value = False

        result = resolve_model_from_prompt_registry(
            CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT
        )

        mock_is_feature_enabled.assert_called_once_with(
            FeatureFlag.FLOW_SOFTWARE_DEVELOPMENT_OPENAI_GPT_5
        )
        assert result is None

    @patch("duo_workflow_service.agents.model_selection.current_model_metadata_context")
    @patch("duo_workflow_service.agents.model_selection.is_feature_enabled")
    def test_chat_with_feature_flag_disabled(
        self, mock_is_feature_enabled, mock_context
    ):
        mock_context.get.return_value = None
        mock_is_feature_enabled.return_value = False

        result = resolve_model_from_prompt_registry(CategoryEnum.WORKFLOW_CHAT)

        mock_is_feature_enabled.assert_called_once_with(
            FeatureFlag.DUO_AGENTIC_CHAT_OPENAI_GPT_5
        )
        assert result is None
