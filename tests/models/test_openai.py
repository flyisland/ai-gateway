from typing import Type
from unittest.mock import AsyncMock, Mock

import pytest
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, BadRequestError
from openai.types import Completion
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice as ChatCompletionChoice
from openai.types.chat.chat_completion_chunk import Choice as ChatCompletionChunkChoice
from openai.types.chat.chat_completion_chunk import (
    ChoiceDelta as ChatCompletionChunkChoiceDelta,
)
from openai.types.completion_choice import CompletionChoice

from ai_gateway.models.base_chat import Message, Role
from ai_gateway.models.base_text import TextGenModelOutput
from ai_gateway.models.openai import (
    KindOpenAIModel,
    OpenAIAPIConnectionError,
    OpenAIAPIStatusError,
    OpenAIAPITimeoutError,
    OpenAIChatModel,
    OpenAIModel,
)
from ai_gateway.safety_attributes import SafetyAttributes


class TestOpenAIModel:
    @pytest.mark.parametrize(
        "model_name_version",
        ["gpt-5"],
    )
    def test_openai_model_from_name(self, model_name_version: str):
        model = OpenAIModel.from_model_name(model_name_version, Mock())

        assert model.metadata.name == model_name_version

    def test_openai_model_from_name_invalid_model(self):
        with pytest.raises(ValueError, match="no model found by the name"):
            OpenAIModel.from_model_name("invalid-model", Mock())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception_class,api_error_class",
        [
            (APIConnectionError, OpenAIAPIConnectionError),
            (APITimeoutError, OpenAIAPITimeoutError),
        ],
    )
    async def test_openai_model_generate_errors_non_status(
        self, exception_class: Type[Exception], api_error_class: Type[Exception]
    ):
        client_mock = Mock(spec=AsyncOpenAI)
        if exception_class == APIConnectionError:
            exception_instance = APIConnectionError(request=Mock())
        elif exception_class == APITimeoutError:
            exception_instance = APITimeoutError(request=Mock())
        else:
            raise ValueError(f"Unexpected exception class: {exception_class}")

        model = OpenAIModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        create_mock = AsyncMock(side_effect=exception_instance)
        setattr(model.client.completions, "create", create_mock)

        with pytest.raises(api_error_class):
            await model.generate("test prefix")

    @pytest.mark.asyncio
    async def test_openai_model_generate_bad_request_error(self):
        client_mock = Mock(spec=AsyncOpenAI)
        exception_instance = BadRequestError("Bad request", response=Mock(), body=None)
        exception_instance.status_code = 400
        exception_instance.message = "Bad request"

        model = OpenAIModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.completions.create = AsyncMock(side_effect=exception_instance)

        with pytest.raises(OpenAIAPIStatusError):
            await model.generate("test prefix")

    @pytest.mark.asyncio
    async def test_openai_model_generate_success(self):
        client_mock = Mock(spec=AsyncOpenAI)

        # Mock the completion response
        choice_mock = Mock(spec=CompletionChoice)
        choice_mock.text = "test completion"

        completion_mock = Mock(spec=Completion)
        completion_mock.choices = [choice_mock]

        model = OpenAIModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.completions.create = AsyncMock(return_value=completion_mock)

        result = await model.generate("test prefix")

        assert isinstance(result, TextGenModelOutput)
        assert result.text == "test completion"
        assert result.score == 10**5
        assert isinstance(result.safety_attributes, SafetyAttributes)

    @pytest.mark.asyncio
    async def test_openai_model_generate_empty_choices(self):
        client_mock = Mock(spec=AsyncOpenAI)

        completion_mock = Mock(spec=Completion)
        completion_mock.choices = []

        model = OpenAIModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.completions.create = AsyncMock(return_value=completion_mock)

        result = await model.generate("test prefix")

        assert isinstance(result, TextGenModelOutput)
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_openai_model_streaming_success(self):
        client_mock = Mock(spec=AsyncOpenAI)

        # Mock streaming response chunks
        async def mock_stream():
            choice_mock1 = Mock(spec=CompletionChoice)
            choice_mock1.text = "chunk1"

            completion_mock1 = Mock(spec=Completion)
            completion_mock1.choices = [choice_mock1]

            yield completion_mock1

            # Second chunk
            choice_mock2 = Mock(spec=CompletionChoice)
            choice_mock2.text = "chunk2"

            completion_mock2 = Mock(spec=Completion)
            completion_mock2.choices = [choice_mock2]

            yield completion_mock2

        model = OpenAIModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.completions.create = AsyncMock(return_value=mock_stream())

        result = await model.generate("test prefix", stream=True)

        # Collect streaming results
        chunks = []
        async for chunk in result:
            chunks.append(chunk.text)

        assert chunks == ["chunk1", "chunk2"]


class TestOpenAIChatModel:
    @pytest.mark.parametrize(
        "model_name_version",
        ["gpt-5"],
    )
    def test_openai_chat_model_from_name(self, model_name_version: str):
        model = OpenAIChatModel.from_model_name(model_name_version, Mock())

        assert model.metadata.name == model_name_version

    def test_openai_chat_model_from_name_invalid_model(self):
        with pytest.raises(ValueError, match="no model found by the name"):
            OpenAIChatModel.from_model_name("invalid-model", Mock())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception_class,api_error_class",
        [
            (APIConnectionError, OpenAIAPIConnectionError),
            (APITimeoutError, OpenAIAPITimeoutError),
        ],
    )
    async def test_openai_chat_model_generate_errors_non_status(
        self, exception_class: Type[Exception], api_error_class: Type[Exception]
    ):
        client_mock = Mock(spec=AsyncOpenAI)
        if exception_class == APIConnectionError:
            exception_instance = APIConnectionError(request=Mock())
        elif exception_class == APITimeoutError:
            exception_instance = APITimeoutError(request=Mock())
        else:
            raise ValueError(f"Unexpected exception class: {exception_class}")

        model = OpenAIChatModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        create_mock = AsyncMock(side_effect=exception_instance)
        setattr(model.client.chat.completions, "create", create_mock)

        messages = [Message(role=Role.USER, content="Hello")]

        with pytest.raises(api_error_class):
            await model.generate(messages)

    @pytest.mark.asyncio
    async def test_openai_chat_model_generate_bad_request_error(self):
        client_mock = Mock(spec=AsyncOpenAI)
        exception_instance = BadRequestError("Bad request", response=Mock(), body=None)
        exception_instance.status_code = 400
        exception_instance.message = "Bad request"

        model = OpenAIChatModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.chat.completions.create = AsyncMock(side_effect=exception_instance)

        messages = [Message(role=Role.USER, content="Hello")]

        with pytest.raises(OpenAIAPIStatusError):
            await model.generate(messages)

    @pytest.mark.asyncio
    async def test_openai_chat_model_generate_success(self):
        client_mock = Mock(spec=AsyncOpenAI)

        # Mock the chat completion response
        message_mock = Mock(spec=ChatCompletionMessage)
        message_mock.content = "test response"

        choice_mock = Mock(spec=ChatCompletionChoice)
        choice_mock.message = message_mock

        completion_mock = Mock(spec=ChatCompletion)
        completion_mock.choices = [choice_mock]

        model = OpenAIChatModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.chat.completions.create = AsyncMock(return_value=completion_mock)

        messages = [Message(role=Role.USER, content="Hello")]
        result = await model.generate(messages)

        assert isinstance(result, TextGenModelOutput)
        assert result.text == "test response"
        assert result.score == 10**5
        assert isinstance(result.safety_attributes, SafetyAttributes)

    @pytest.mark.asyncio
    async def test_openai_chat_model_generate_empty_choices(self):
        client_mock = Mock(spec=AsyncOpenAI)

        completion_mock = Mock(spec=ChatCompletion)
        completion_mock.choices = []

        model = OpenAIChatModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.chat.completions.create = AsyncMock(return_value=completion_mock)

        messages = [Message(role=Role.USER, content="Hello")]
        result = await model.generate(messages)

        assert isinstance(result, TextGenModelOutput)
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_openai_chat_model_streaming_success(self):
        client_mock = Mock(spec=AsyncOpenAI)

        # Mock streaming response chunks
        async def mock_stream():
            delta_mock = Mock(spec=ChatCompletionChunkChoiceDelta)
            delta_mock.content = "chunk1"

            choice_mock = Mock(spec=ChatCompletionChunkChoice)
            choice_mock.delta = delta_mock

            chunk_mock = Mock(spec=ChatCompletionChunk)
            chunk_mock.choices = [choice_mock]

            yield chunk_mock

            # Second chunk
            delta_mock2 = Mock(spec=ChatCompletionChunkChoiceDelta)
            delta_mock2.content = "chunk2"

            choice_mock2 = Mock(spec=ChatCompletionChunkChoice)
            choice_mock2.delta = delta_mock2

            chunk_mock2 = Mock(spec=ChatCompletionChunk)
            chunk_mock2.choices = [choice_mock2]

            yield chunk_mock2

        model = OpenAIChatModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        messages = [Message(role=Role.USER, content="Hello")]
        result = await model.generate(messages, stream=True)

        # Collect streaming results
        chunks = []
        async for chunk in result:
            chunks.append(chunk.text)

        assert chunks == ["chunk1", "chunk2"]

    @pytest.mark.asyncio
    async def test_openai_chat_model_message_building(self):
        """Test that messages are properly converted to OpenAI format."""
        client_mock = Mock(spec=AsyncOpenAI)

        # Mock the response
        message_mock = Mock(spec=ChatCompletionMessage)
        message_mock.content = "test response"

        choice_mock = Mock(spec=ChatCompletionChoice)
        choice_mock.message = message_mock

        completion_mock = Mock(spec=ChatCompletion)
        completion_mock.choices = [choice_mock]

        model = OpenAIChatModel(client_mock, model_name=KindOpenAIModel.GPT_5.value)
        model.client.chat.completions.create = AsyncMock(return_value=completion_mock)

        messages = [
            Message(role=Role.SYSTEM, content="You are a helpful assistant"),
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.ASSISTANT, content="Hi there!"),
            Message(role=Role.USER, content="How are you?"),
        ]

        await model.generate(messages)

        # Verify the client was called with properly formatted messages
        model.client.chat.completions.create.assert_called_once()
        call_args = model.client.chat.completions.create.call_args
        assert call_args is not None

        messages_arg = call_args.kwargs.get("messages")
        assert messages_arg is not None
        assert len(messages_arg) == 4

        assert messages_arg[0]["role"] == "system"
        assert messages_arg[0]["content"] == "You are a helpful assistant"
        assert messages_arg[1]["role"] == "user"
        assert messages_arg[1]["content"] == "Hello"
        assert messages_arg[2]["role"] == "assistant"
        assert messages_arg[2]["content"] == "Hi there!"
        assert messages_arg[3]["role"] == "user"
        assert messages_arg[3]["content"] == "How are you?"


class TestKindOpenAIModel:
    def test_enum_values(self):
        """Test that the OpenAI model enum has expected values."""
        assert KindOpenAIModel.GPT_5.value == "gpt-5"

        # Test that we can iterate over the enum
        model_names = [model.value for model in KindOpenAIModel]
        assert "gpt-5" in model_names
