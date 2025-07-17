from contextlib import nullcontext as does_not_raise
from unittest.mock import Mock, patch

import pytest

from ai_gateway.models import KindAnthropicModel
from ai_gateway.models.openai import KindOpenAIModel
from duo_workflow_service.llm_factory import (
    AnthropicConfig,
    OpenAIConfig,
    VertexConfig,
    create_chat_model,
    validate_llm_access,
)


@pytest.mark.parametrize(
    "env_vars,expectation,calls_llm",
    [
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
                "DUO_WORKFLOW__VERTEX_LOCATION": "test-loc",
            },
            does_not_raise(),
            "vertex",
        ),
        (
            {
                "OPENAI_API_KEY": "test-key",
            },
            does_not_raise(),
            "openai",  # Falls back to OpenAI and succeeds
        ),
        (
            {
                "ANTHROPIC_API_KEY": "test-key",
            },
            does_not_raise(),
            "anthropic",  # Falls back to Anthropic and succeeds
        ),
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
            },
            pytest.raises(
                RuntimeError,
                match="ANTHROPIC_API_KEY needs to be set for Anthropic provider",
            ),
            None,
        ),
        (
            {},
            pytest.raises(
                RuntimeError,
                match="ANTHROPIC_API_KEY needs to be set for Anthropic provider",
            ),  # Falls back to Anthropic but no API key
            None,
        ),
    ],
)
@patch("duo_workflow_service.llm_factory.ChatAnthropicVertex")
@patch("duo_workflow_service.llm_factory.ChatAnthropic")
@patch("duo_workflow_service.llm_factory.ChatOpenAI")
def test_validate_anthropic_variables(
    mock_openai_client,
    mock_anthropic_client,
    mock_vertex_client,
    env_vars,
    expectation,
    calls_llm,
):
    # Mock the invoke method to return a response
    mock_response = Mock()
    mock_response.content = "I am Claude, an AI assistant."
    mock_anthropic_client.return_value.invoke.return_value = mock_response
    mock_vertex_client.return_value.invoke.return_value = mock_response
    mock_openai_client.return_value.invoke.return_value = mock_response

    with patch("os.environ", env_vars):
        with expectation:
            validate_llm_access()

        if calls_llm == "vertex":
            mock_anthropic_client.assert_not_called()
            mock_openai_client.assert_not_called()
            mock_vertex_client.assert_called_once()

            call_kwargs = mock_vertex_client.call_args.kwargs
            assert (
                call_kwargs["model_name"]
                == KindAnthropicModel.CLAUDE_SONNET_4_VERTEX.value
            )
            assert call_kwargs["project"] == "test-proj"
            assert call_kwargs["location"] == "test-loc"
        elif calls_llm == "openai":
            mock_vertex_client.assert_not_called()
            mock_anthropic_client.assert_not_called()
            mock_openai_client.assert_called_once()

            call_kwargs = mock_openai_client.call_args.kwargs
            assert call_kwargs["model_name"] == KindOpenAIModel.GPT_4_1.value
        elif calls_llm == "anthropic":
            mock_vertex_client.assert_not_called()
            mock_openai_client.assert_not_called()
            mock_anthropic_client.assert_called_once()

            call_kwargs = mock_anthropic_client.call_args.kwargs
            assert call_kwargs["model_name"] == KindAnthropicModel.CLAUDE_SONNET_4.value
            assert call_kwargs["betas"] == ["extended-cache-ttl-2025-04-11"]
        else:
            mock_vertex_client.assert_not_called()
            mock_anthropic_client.assert_not_called()
            mock_openai_client.assert_not_called()


@pytest.mark.parametrize(
    "env_vars,config_class,model_name,calls_llm",
    [
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
                "DUO_WORKFLOW__VERTEX_LOCATION": "test-loc",
            },
            VertexConfig,
            None,
            "vertex",
        ),
        (
            {
                "ANTHROPIC_API_KEY": "test-key",
            },
            AnthropicConfig,
            "claude-sonnet-4-20250514",  # Required for AnthropicConfig
            "anthropic",
        ),
    ],
)
@patch("duo_workflow_service.llm_factory.ChatAnthropicVertex")
@patch("duo_workflow_service.llm_factory.ChatAnthropic")
def test_clients_receive_max_retries_from_config(
    mock_anthropic_client,
    mock_vertex_client,
    env_vars,
    config_class,
    model_name,
    calls_llm,
):
    # Mock the invoke method to return a response
    mock_response = Mock()
    mock_response.content = "I am Claude, an AI assistant."
    mock_anthropic_client.return_value.invoke.return_value = mock_response
    mock_vertex_client.return_value.invoke.return_value = mock_response

    with patch("os.environ", env_vars):
        # Create the appropriate config based on the test case
        if config_class == VertexConfig:
            config = VertexConfig()
        else:
            config = AnthropicConfig(model_name=model_name)

        expected_retries = config.max_retries

        # Use validate_llm_access with the config
        validate_llm_access(config)

        if calls_llm == "vertex":
            mock_vertex_client.assert_called_once()
            assert (
                mock_vertex_client.call_args.kwargs["max_retries"] == expected_retries
            )
            mock_anthropic_client.assert_not_called()
        else:
            mock_anthropic_client.assert_called_once()
            call_kwargs = mock_anthropic_client.call_args.kwargs
            assert call_kwargs["max_retries"] == expected_retries
            assert call_kwargs["betas"] == ["extended-cache-ttl-2025-04-11"]
            mock_vertex_client.assert_not_called()


@pytest.mark.parametrize(
    "model_name,expectation",
    [
        (KindOpenAIModel.GPT_4_1.value, does_not_raise()),
        (KindOpenAIModel.GPT_4_TURBO.value, does_not_raise()),
        (
            "invalid-model",
            pytest.raises(ValueError, match="model_name 'invalid-model' is not valid"),
        ),
    ],
)
def test_openai_config_validation(model_name, expectation):
    """Test that OpenAIConfig validates model names correctly."""
    with expectation:
        config = OpenAIConfig(model_name=model_name)
        assert config.model_name == model_name
        assert config.provider == "openai"


@patch("duo_workflow_service.llm_factory.ChatOpenAI")
def test_create_chat_model_with_openai_config(mock_openai_client):
    """Test that create_chat_model works with OpenAI configuration."""
    config = OpenAIConfig(model_name=KindOpenAIModel.GPT_4_1.value)

    with patch("os.environ", {"OPENAI_API_KEY": "test-key"}):
        create_chat_model(config)

        mock_openai_client.assert_called_once()
        call_kwargs = mock_openai_client.call_args.kwargs
        assert call_kwargs["model_name"] == KindOpenAIModel.GPT_4_1.value
        assert call_kwargs["max_retries"] == 6  # default from ModelConfig


@patch("duo_workflow_service.llm_factory.ChatOpenAI")
def test_create_chat_model_with_openai_config_missing_key(mock_openai_client):
    """Test that create_chat_model raises error when OpenAI API key is missing."""
    config = OpenAIConfig(model_name=KindOpenAIModel.GPT_4_1.value)

    with patch("os.environ", {}):
        with pytest.raises(
            RuntimeError, match="OPENAI_API_KEY needs to be set for OpenAI provider"
        ):
            create_chat_model(config)

        mock_openai_client.assert_not_called()


@pytest.mark.parametrize(
    "env_vars,config_type,model_param,expected_model,calls_llm",
    [
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
                "DUO_WORKFLOW__VERTEX_LOCATION": "test-loc",
            },
            "vertex",
            "custom-model-name",
            "custom-model-name",
            "vertex",
        ),
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
                "DUO_WORKFLOW__VERTEX_LOCATION": "test-loc",
            },
            "vertex",
            None,
            "claude-sonnet-4@20250514",  # Default when no feature flags
            "vertex",
        ),
        (
            {
                "ANTHROPIC_API_KEY": "test-key",
            },
            "anthropic",
            "claude-3-7-sonnet-20250219",
            "claude-3-7-sonnet-20250219",
            "anthropic",
        ),
        (
            {
                "ANTHROPIC_API_KEY": "test-key",
            },
            "anthropic",
            None,
            None,  # Will fail validation if None
            "anthropic",
        ),
    ],
)
@patch("duo_workflow_service.llm_factory.ChatAnthropicVertex")
@patch("duo_workflow_service.llm_factory.ChatAnthropic")
def test_new_chat_client_with_custom_model(
    mock_anthropic_client,
    mock_vertex_client,
    env_vars,
    config_type,
    model_param,
    expected_model,
    calls_llm,
):
    with patch("os.environ", env_vars):
        if config_type == "vertex":
            if model_param:
                config = VertexConfig(model_name=model_param)
            else:
                config = VertexConfig()
        else:  # anthropic
            if model_param:
                config = AnthropicConfig(model_name=model_param)
            else:
                # This should raise validation error since model_name is required
                # and must be a valid KindAnthropicModel value
                with pytest.raises(ValueError):
                    config = AnthropicConfig()
                return

        create_chat_model(config=config)

        if calls_llm == "vertex":
            mock_vertex_client.assert_called_once()
            assert mock_vertex_client.call_args.kwargs["model_name"] == expected_model
            assert mock_vertex_client.call_args.kwargs["project"] == "test-proj"
            assert mock_vertex_client.call_args.kwargs["location"] == "test-loc"
            mock_anthropic_client.assert_not_called()
        else:
            mock_anthropic_client.assert_called_once()
            call_kwargs = mock_anthropic_client.call_args.kwargs
            assert call_kwargs["model_name"] == expected_model
            assert call_kwargs["betas"] == ["extended-cache-ttl-2025-04-11"]
            mock_vertex_client.assert_not_called()
