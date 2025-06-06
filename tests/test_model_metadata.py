# Import your model classes
from unittest import mock
from unittest.mock import patch

import pytest
from gitlab_cloud_connector import GitLabUnitPrimitive
from pydantic import HttpUrl

from ai_gateway.model_metadata import (
    AmazonQModelMetadata,
    ModelMetadata,
    auth_parameters_for_gitlab_model,
    create_model_metadata,
    parameters_for_gitlab_provider,
)
from ai_gateway.model_selection import (
    LLMDefinition,
    ModelSelectionConfig,
    UnitPrimitiveConfig,
)


def test_create_amazon_q_model_metadata():
    # Arrange
    data = {
        "provider": "amazon_q",
        "name": "amazon_q",
        "role_arn": "arn:aws:iam::123456789012:role/example-role",
    }

    # Act
    result = create_model_metadata(data)

    # Assert
    assert isinstance(result, AmazonQModelMetadata)
    assert result.provider == "amazon_q"
    assert result.name == "amazon_q"
    assert result.role_arn == "arn:aws:iam::123456789012:role/example-role"


def test_create_regular_model_metadata():
    # Arrange
    data = {
        "name": "gpt-4",
        "provider": "openai",
        "endpoint": "https://api.openai.com/v1",
        "api_key": "test-key",
        "identifier": "openai/gpt-4",
    }

    # Act
    result = create_model_metadata(data)

    # Assert
    assert isinstance(result, ModelMetadata)
    assert result.name == "gpt-4"
    assert result.provider == "openai"
    assert str(result.endpoint) == "https://api.openai.com/v1"
    assert result.api_key == "test-key"
    assert result.identifier == "openai/gpt-4"


class TestCreateGitlabModelMetadata:
    @pytest.fixture(autouse=True)
    def get_llm_definitions(self):
        mock_models = {
            "gitlab_model1": LLMDefinition(
                gitlab_identifier="gitlab_model1",
                name="gitlab_model",
                provider="custom_openai",
                provider_identifier="mixtral_8x7b",
                family="mixtral",
            )
        }

        mock_definitions = {
            "duo_chat": UnitPrimitiveConfig(
                feature_setting="duo_chat",
                unit_primitives=[GitLabUnitPrimitive.DUO_CHAT],
                default_model="gitlab_model1",
            )
        }

        with patch.multiple(
            ModelSelectionConfig,
            get_llm_definitions=mock.Mock(return_value=mock_models),
            get_unit_primitive_config_map=mock.Mock(return_value=mock_definitions),
        ) as mock_method:
            yield mock_method

    def test_create_gitlab_model_metadata_with_identifier(self):
        data = {
            "provider": "gitlab",
            "identifier": "gitlab_model1",
        }

        result = create_model_metadata(data)

        assert result.provider == "custom_openai"
        assert result.identifier == "mixtral_8x7b"
        assert result.name == "mixtral"

    def test_create_gitlab_model_metadata_with_feature_setting(self):
        data = {
            "provider": "gitlab",
            "feature_setting": "duo_chat",
        }

        result = create_model_metadata(data)

        assert result.provider == "custom_openai"
        assert result.identifier == "mixtral_8x7b"
        assert result.name == "mixtral"

    def test_required_parameters(self):
        data = {
            "provider": "gitlab",
        }

        with pytest.raises(
            ValueError,
            match=r"Argument error: either identifier or feature_setting must be present.",
        ):
            create_model_metadata(data)

    def test_create_gitlab_model_metadata_non_existing(self):
        data = {
            "provider": "gitlab",
            "identifier": "non_existing_gitlab_model",
        }

        with pytest.raises(ValueError):
            create_model_metadata(data)


def test_create_model_metadata_invalid_data():
    # Arrange
    invalid_data = {
        "provider": "amazon_q",
        "name": "amazon_q",
        # missing required role_arn
    }

    with pytest.raises(ValueError):
        create_model_metadata(invalid_data)


class TestModelMetadataToParams:
    def test_without_identifier(self):
        model_metadata = ModelMetadata(
            name="model_family",
            provider="provider",
            endpoint=HttpUrl("https://api.example.com"),
            api_key="abcde",
            identifier=None,
        )

        params = model_metadata.to_params()

        assert params == {
            "api_base": "https://api.example.com",
            "api_key": "abcde",
            "model": "model_family",
            "custom_llm_provider": "provider",
        }

    def test_with_identifier_no_provider(self):
        model_metadata = ModelMetadata(
            name="model_family",
            provider="provider",
            endpoint=HttpUrl("https://api.example.com"),
            api_key="abcde",
            identifier="model_identifier",
        )

        params = model_metadata.to_params()

        assert params == {
            "api_base": "https://api.example.com",
            "api_key": "abcde",
            "model": "model_identifier",
            "custom_llm_provider": "custom_openai",
        }

    def test_with_identifier_with_provider(self):
        model_metadata = ModelMetadata(
            name="model_family",
            provider="provider",
            endpoint=HttpUrl("https://api.example.com"),
            api_key="abcde",
            identifier="custom_provider/model/identifier",
        )

        params = model_metadata.to_params()

        assert params == {
            "api_base": "https://api.example.com",
            "api_key": "abcde",
            "model": "model/identifier",
            "custom_llm_provider": "custom_provider",
        }

    def test_with_identifier_with_bedrock_provider(self):
        model_metadata = ModelMetadata(
            name="model_family",
            provider="provider",
            endpoint=HttpUrl("https://api.example.com"),
            api_key="abcde",
            identifier="bedrock/model/identifier",
        )

        params = model_metadata.to_params()

        assert params == {
            "model": "model/identifier",
            "api_key": "abcde",
            "custom_llm_provider": "bedrock",
        }

    def test_without_api_key_uses_dummy_key(self):
        model_metadata = ModelMetadata(
            name="model_family",
            provider="provider",
            endpoint=HttpUrl("https://api.example.com"),
            api_key=None,
            identifier=None,
        )

        params = model_metadata.to_params()

        assert params == {
            "api_base": "https://api.example.com",
            "api_key": "dummy_key",
            "model": "model_family",
            "custom_llm_provider": "provider",
        }

    def test_anthropic_provider(self):
        model_metadata = ModelMetadata(
            identifier="model_identifier", name="base", provider="anthropic"
        )

        params = model_metadata.to_params()

        assert params == {
            "model": "model_identifier",
        }


def test_create_model_metadata_with_none_data():
    result = create_model_metadata(None)
    assert result is None


def test_create_model_metadata_without_provider():
    result = create_model_metadata({"name": "test"})
    assert result is None


class TestFireworksAuthentication:
    @pytest.fixture
    def mock_config_class(self):
        from ai_gateway.config import ConfigModelEndpoints, ConfigModelKeys

        mock_endpoints = ConfigModelEndpoints(
            fireworks_current_region_endpoint={
                "codestral-2501": {
                    "endpoint": "https://api.fireworks.ai/inference",
                    "identifier": "fireworks-model-id",
                }
            }
        )
        mock_keys = ConfigModelKeys(fireworks_api_key="test-fireworks-key")

        mock_config = mock.Mock()
        mock_config.model_endpoints = mock_endpoints
        mock_config.model_keys = mock_keys
        return mock_config

    @pytest.fixture
    def fireworks_model(self):
        return LLMDefinition(
            gitlab_identifier="codestral_2501_fireworks",
            name="fireworks_model",
            provider="fireworks_ai",
            provider_identifier="original-identifier",
            family="codestral",
        )

    @pytest.fixture
    def regular_model(self):
        return LLMDefinition(
            gitlab_identifier="regular_model",
            name="regular_model",
            provider="custom_openai",
            provider_identifier="original-identifier",
            family="base",
        )

    def test_fireworks_auth_parameters(self, mock_config_class, fireworks_model):
        with patch("ai_gateway.config.Config", return_value=mock_config_class):
            auth_params = auth_parameters_for_gitlab_model(fireworks_model)

            assert auth_params == {
                "endpoint": "https://api.fireworks.ai/inference",
                "api_key": "test-fireworks-key",
                "identifier": "text-completion-openai/fireworks-model-id",
            }

    def test_regular_model_auth_parameters(self, regular_model):
        auth_params = auth_parameters_for_gitlab_model(regular_model)

        assert not auth_params

    def test_fireworks_identifier_override(self, mock_config_class, fireworks_model):
        with patch("ai_gateway.config.Config", return_value=mock_config_class):
            params = parameters_for_gitlab_provider(
                {"identifier": fireworks_model.gitlab_identifier}
            )

            assert params["identifier"] == "text-completion-openai/fireworks-model-id"
            assert params["provider"] == "fireworks_ai"
            assert params["name"] == "codestral"
            assert params["endpoint"] == "https://api.fireworks.ai/inference"
            assert params["api_key"] == "test-fireworks-key"

    def test_regular_model_no_override(self, regular_model):
        params = parameters_for_gitlab_provider(
            {"identifier": regular_model.gitlab_identifier}
        )

        assert params["identifier"] == "original-identifier"
        assert params["provider"] == "custom_openai"
        assert params["name"] == "base"
        assert "endpoint" not in params
        assert "api_key" not in params

    @pytest.fixture(autouse=True)
    def mock_model_selection(self, fireworks_model, regular_model):
        mock_models = {
            fireworks_model.gitlab_identifier: fireworks_model,
            regular_model.gitlab_identifier: regular_model,
        }

        with patch.multiple(
            ModelSelectionConfig,
            get_llm_definitions=mock.Mock(return_value=mock_models),
        ):
            yield
