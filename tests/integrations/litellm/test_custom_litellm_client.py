from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_community.chat_models.litellm import ChatLiteLLM
from langchain_core.messages import BaseMessage, BaseMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from ai_gateway.integrations.litellm.chat import CustomChatLiteLLM

# Shared parameterized values
stream_options_test_cases = [
    # respect stream_options if provided
    (True, {}, {"include_usage": True}),
    (True, {"key_1": "value_1"}, {"include_usage": True, "key_1": "value_1"}),
    # remove stream_options if stream is False
    (False, None, None),
    (False, {"key_1": "value_1"}, None),
]


@pytest.mark.parametrize(
    "stream, custom_stream_options, expected_stream_options", stream_options_test_cases
)
def test_generate_with_stream_options(
    stream, custom_stream_options, expected_stream_options
):
    """Test that stream_options is added correctly to super()._generate call."""
    messages = [HumanMessage(content="Hello")]

    # Create a patch for the parent class's _generate method
    with patch(
        "langchain_community.chat_models.ChatLiteLLM._generate"
    ) as mock_super_generate:
        mock_super_generate.return_value = ChatResult(generations=[])

        # Create the instance and call _generate
        chat = CustomChatLiteLLM()

        chat._generate(
            messages=messages,
            stream=stream,
            **{"stream_options": custom_stream_options}
        )

        # Assert that super()._generate was called with the correct stream_options
        mock_super_generate.assert_called_once()
        call_kwargs = mock_super_generate.call_args.kwargs

        if stream:
            assert call_kwargs["stream_options"] == expected_stream_options
        else:
            assert "stream_options" not in call_kwargs


@pytest.mark.parametrize(
    "stream, custom_stream_options, expected_stream_options", stream_options_test_cases
)
@pytest.mark.asyncio
async def test_agenerate_with_stream_options(
    stream, custom_stream_options, expected_stream_options
):
    """Test that stream_options is added correctly to super()._agenerate call."""
    messages = [HumanMessage(content="Hello")]

    # Create a patch for the parent class's _agenerate method
    with patch(
        "langchain_community.chat_models.ChatLiteLLM._agenerate"
    ) as mock_super_generate:
        mock_super_generate.return_value = ChatResult(generations=[])

        # Create the instance and call _agenerate
        chat = CustomChatLiteLLM()
        await chat._agenerate(
            messages=messages,
            stream=stream,
            **{"stream_options": custom_stream_options}
        )

        # Assert that super()._agenerate was called with the correct stream_options
        mock_super_generate.assert_called_once()
        call_kwargs = mock_super_generate.call_args.kwargs

        if stream:
            assert call_kwargs["stream_options"] == expected_stream_options
        else:
            assert "stream_options" not in call_kwargs


@pytest.mark.parametrize("stream", [True, False])
def test_stream_with_stream_options(stream):
    """Test that stream_options is added correctly to super()._stream call."""
    message = HumanMessage(content="Hello")
    message_chunk = BaseMessageChunk(content=message.content, type=message.type)

    # Create a patch for the parent class's _stream method
    with patch(
        "langchain_community.chat_models.ChatLiteLLM._stream"
    ) as mock_super_stream:
        mock_super_stream.return_value = iter(
            [ChatGenerationChunk(message=message_chunk)]
        )

        chat = CustomChatLiteLLM()

        # The stream parameter should have no effect on _stream
        list(chat._stream(messages=[message], stream=stream))

        # Assert that super()._generate was called with the correct stream_options
        mock_super_stream.assert_called_once()
        call_kwargs = mock_super_stream.call_args.kwargs

        assert call_kwargs["stream_options"] == chat.default_stream_options


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.asyncio
async def test_astream_with_stream_options(stream):
    """Test that stream_options is added correctly to super()._astream call."""
    message = HumanMessage(content="Hello")

    with patch(
        "langchain_community.chat_models.ChatLiteLLM._astream"
    ) as mock_super_astream:

        chat = CustomChatLiteLLM()

        # The stream parameter should have no effect on _astream
        result = []
        async for item in chat._astream(messages=[message], stream=stream):
            result.append(item)

        # Assert that the correct stream_options were passed
        mock_super_astream.assert_called_once()

        call_kwargs = mock_super_astream.call_args.kwargs
        assert call_kwargs["stream_options"] == chat.default_stream_options
