# pylint: disable=file-naming-for-tests

from contextlib import nullcontext as does_not_raise
from unittest.mock import Mock, patch

import pytest

from duo_workflow_service.llm_factory import (
    VertexConfig,
    create_chat_model,
    validate_llm_access,
)


@pytest.mark.parametrize(
    "env_vars,expectation,calls_llm",
    [
        (
            {
                "ANTHROPIC_API_KEY": "anthropic-key1",
            },
            does_not_raise(),
            "anthropic",
        ),
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "hello2",
                "DUO_WORKFLOW__VERTEX_LOCATION": "key2",
                "ANTHROPIC_API_KEY": "anthropic-key2",
            },
            does_not_raise(),
            "anthropic",  # Since is_vertex is not passed, it defaults to Anthropic
        ),
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "hello3",
                "DUO_WORKFLOW__VERTEX_LOCATION": "key3",
            },
            pytest.raises(RuntimeError),  # No ANTHROPIC_API_KEY
            None,
        ),
        (
            {
                "ANTHROPIC_API_KEY": "",  # Empty key
            },
            pytest.raises(RuntimeError),
            None,
        ),
        ({}, pytest.raises(RuntimeError), None),  # No env vars at all
    ],
)
@patch("duo_workflow_service.llm_factory.get_anthropic_model_name")
@patch("duo_workflow_service.llm_factory.ChatAnthropicVertex")
@patch("duo_workflow_service.llm_factory.ChatAnthropic")
def test_validate_anthropic_variables(
    mock_anthropic_client,
    mock_vertex_client,
    mock_get_model_name,
    env_vars,
    expectation,
    calls_llm,
):
    # Mock the model name function to return a string
    mock_get_model_name.return_value = "claude-3-5-sonnet-20241022"

    # Mock the invoke method to return a response
    mock_response = Mock()
    mock_response.content = "I am Claude, an AI assistant."
    mock_anthropic_client.return_value.invoke.return_value = mock_response
    mock_vertex_client.return_value.invoke.return_value = mock_response

    with patch("os.environ", env_vars):
        with expectation:
            validate_llm_access()

        if calls_llm == "vertex":
            mock_anthropic_client.assert_not_called()
            mock_vertex_client.assert_called_once()
        elif calls_llm == "anthropic":
            mock_vertex_client.assert_not_called()
            mock_anthropic_client.assert_called_once()
        else:
            mock_vertex_client.assert_not_called()
            mock_anthropic_client.assert_not_called()


@pytest.mark.parametrize(
    "env_vars,calls_llm",
    [
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
                "DUO_WORKFLOW__VERTEX_LOCATION": "test-loc",
                "ANTHROPIC_API_KEY": "test-key",
            },
            "anthropic",  # Without is_vertex=True, it defaults to Anthropic
        ),
        (
            {
                "ANTHROPIC_API_KEY": "test-key",
            },
            "anthropic",
        ),
    ],
)
@patch("duo_workflow_service.llm_factory.get_anthropic_model_name")
@patch("duo_workflow_service.llm_factory.ChatAnthropicVertex")
@patch("duo_workflow_service.llm_factory.ChatAnthropic")
def test_clients_receive_max_retries_from_config(
    mock_anthropic_client,
    mock_vertex_client,
    mock_get_model_name,
    env_vars,
    calls_llm,
):
    # Mock the model name function to return a string
    mock_get_model_name.return_value = "claude-3-5-sonnet-20241022"

    # Mock the invoke method to return a response
    mock_response = Mock()
    mock_response.content = "I am Claude, an AI assistant."
    mock_anthropic_client.return_value.invoke.return_value = mock_response
    mock_vertex_client.return_value.invoke.return_value = mock_response

    config = VertexConfig()
    expected_retries = config.max_retries

    with patch("os.environ", env_vars):
        validate_llm_access(config)

        if calls_llm == "vertex":
            mock_vertex_client.assert_called_once()
            assert (
                mock_vertex_client.call_args.kwargs["max_retries"] == expected_retries
            )
            mock_anthropic_client.assert_not_called()
        else:
            mock_anthropic_client.assert_called_once()
            assert (
                mock_anthropic_client.call_args.kwargs["max_retries"]
                == expected_retries
            )
            mock_vertex_client.assert_not_called()


@pytest.mark.parametrize(
    "env_vars,model_param,expected_model,calls_llm",
    [
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
                "DUO_WORKFLOW__VERTEX_LOCATION": "test-loc",
            },
            "custom-model-name",
            "custom-model-name",
            "vertex",
        ),
        (
            {
                "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-proj",
                "DUO_WORKFLOW__VERTEX_LOCATION": "test-loc",
            },
            None,
            None,  # Will use config.model_name
            "vertex",
        ),
        (
            {
                "ANTHROPIC_API_KEY": "test-key",
            },
            "custom-anthropic-model",
            "custom-anthropic-model",
            "anthropic",
        ),
        (
            {
                "ANTHROPIC_API_KEY": "test-key",
            },
            None,
            None,  # Will use get_anthropic_model_name()
            "anthropic",
        ),
    ],
)
@patch("duo_workflow_service.llm_factory.get_anthropic_model_name")
@patch("duo_workflow_service.llm_factory.ChatAnthropicVertex")
@patch("duo_workflow_service.llm_factory.ChatAnthropic")
def test_new_chat_client_with_custom_model(
    mock_anthropic_client,
    mock_vertex_client,
    mock_get_anthropic_model_name,
    env_vars,
    model_param,
    expected_model,
    calls_llm,
):
    config = VertexConfig()
    mock_get_anthropic_model_name.return_value = "default-anthropic-model"

    with patch("os.environ", env_vars):
        is_vertex = (
            env_vars.get("DUO_WORKFLOW__VERTEX_PROJECT_ID", "").lower() == "test-proj"
        )
        create_chat_model(
            config=config,
            model_name=model_param,
            is_vertex=is_vertex,
        )

        if calls_llm == "vertex":
            mock_vertex_client.assert_called_once()
            if expected_model:
                assert (
                    mock_vertex_client.call_args.kwargs["model_name"] == expected_model
                )
            else:
                assert (
                    mock_vertex_client.call_args.kwargs["model_name"]
                    == config.model_name
                )
            mock_anthropic_client.assert_not_called()
        else:
            mock_anthropic_client.assert_called_once()
            if expected_model:
                assert (
                    mock_anthropic_client.call_args.kwargs["model_name"]
                    == expected_model
                )
            else:
                assert (
                    mock_anthropic_client.call_args.kwargs["model_name"]
                    == "default-anthropic-model"
                )
            mock_vertex_client.assert_not_called()
