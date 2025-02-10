# test_chat.py
import asyncio
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from requests.exceptions import Timeout

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.integrations.amazon_q.chat import ChatAmazonQ
from ai_gateway.integrations.amazon_q.message_processor import (
    MessageProcessor,
    ProcessedMessage,
)
from ai_gateway.integrations.amazon_q.response_handlers import ResponseHandler


@pytest.fixture
def mock_user() -> StarletteUser:
    """Create a mock StarletteUser for testing."""
    user = Mock(spec=StarletteUser)
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_authenticated = True
    user.cloud_connector_token = ("test_token",)
    return user


@pytest.fixture
def chat_client(mock_user: StarletteUser) -> ChatAmazonQ:
    """Create a ChatAmazonQ instance for testing."""
    client = ChatAmazonQ(
        amazon_q_client_factory=Mock(),
        model="amazon_q",
        message_processor=MessageProcessor(),
        response_handler=ResponseHandler(),
    )
    client.metadata = {"user": mock_user}
    return client


@pytest.fixture
def mock_messages() -> List[BaseMessage]:
    """Create a list of test messages."""
    return [
        SystemMessage(content="System message"),
        HumanMessage(content="Human message"),
        AIMessage(content="AI message"),
    ]


class TestChatAmazonQInitialization:
    def test_post_init(self, chat_client: ChatAmazonQ) -> None:
        """Test post initialization setup."""
        assert isinstance(chat_client.metadata, dict)
        assert "user" in chat_client.metadata
        assert chat_client._llm_type == "amazon_q"
        assert chat_client._identifying_params == {"model": "amazon_q"}

    def test_initialization_with_custom_params(self, mock_user: StarletteUser) -> None:
        """Test initialization with custom parameters."""
        custom_client = ChatAmazonQ(
            amazon_q_client_factory=Mock(),
            model="custom_model",
            message_processor=MessageProcessor(),
            response_handler=ResponseHandler(),
        )
        # Initialize metadata with mock user
        custom_client.metadata = {"user": mock_user}

        assert custom_client._identifying_params["model"] == "custom_model"
        assert isinstance(custom_client.metadata, dict)
        assert custom_client.metadata["user"] == mock_user


class TestChatAmazonQMessageGeneration:
    def test_process_messages(
        self,
        chat_client: ChatAmazonQ,
        mock_user: StarletteUser,
        mock_messages: List[BaseMessage],
    ) -> None:
        """Test message processing."""
        result = chat_client._process_messages(mock_messages, current_user=mock_user)

        # Verify the processed message properties
        assert isinstance(result, ProcessedMessage)
        assert result.content == "AI message"  # The last message content
        assert hasattr(result, "conversation_id")
        assert isinstance(result.history, list)
        assert len(result.history) > 0
        assert "userInputMessage" in result.history[0]
        assert "System message" in result.history[0]["userInputMessage"]
        assert "Human message" in result.history[0]["userInputMessage"]

    @pytest.mark.asyncio
    async def test_agenerate(
        self, chat_client: ChatAmazonQ, mock_messages: List[BaseMessage]
    ) -> None:
        """Test async message generation."""
        mock_response = "Response"  # Direct string response instead of coroutine

        with patch.object(chat_client, "_build_response", return_value=mock_response):
            result = await chat_client._agenerate(mock_messages)
            assert isinstance(result, ChatResult)
            assert len(result.generations) == 1
            assert result.generations[0].message.content == mock_response

    def test_generate(
        self, chat_client: ChatAmazonQ, mock_messages: List[BaseMessage]
    ) -> None:
        """Test synchronous message generation."""
        with patch.object(chat_client, "_build_response", return_value="Response"):
            result = chat_client._generate(mock_messages)
            assert isinstance(result, ChatResult)
            assert result.generations[0].message.content == "Response"

    def test_generate_empty_response(
        self, chat_client: ChatAmazonQ, mock_messages: List[BaseMessage]
    ) -> None:
        """Test handling of empty response."""
        with patch.object(chat_client, "_build_response", return_value=""):
            result = chat_client._generate(mock_messages)
            assert result.generations[0].message.content == ""


class TestChatAmazonQStreaming:
    @pytest.mark.asyncio
    async def test_astream(
        self, chat_client: ChatAmazonQ, mock_messages: List[BaseMessage]
    ) -> None:
        """Test async streaming."""
        mock_stream = iter([{"chunk": "Test response"}])

        async def mock_build_response(*args, **kwargs):
            return {"responseStream": mock_stream}

        with patch.object(
            chat_client, "_build_response", side_effect=mock_build_response
        ):
            chunks = []
            async for chunk in chat_client._astream(mock_messages):
                chunks.append(chunk)
            assert len(chunks) > 0
            assert isinstance(chunks[0], ChatGenerationChunk)

    def test_stream(
        self, chat_client: ChatAmazonQ, mock_messages: List[BaseMessage]
    ) -> None:
        """Test synchronous streaming."""
        mock_stream = iter([{"chunk": "Test response"}])
        with patch.object(
            chat_client, "_build_response", return_value={"responseStream": mock_stream}
        ):
            chunks = list(chat_client._stream(mock_messages))
            assert len(chunks) > 0
            assert isinstance(chunks[0], ChatGenerationChunk)

    @pytest.mark.asyncio
    async def test_stream_timeout(
        self, chat_client: ChatAmazonQ, mock_messages: List[BaseMessage]
    ) -> None:
        """Test streaming timeout handling."""
        mock_error = Timeout("Connection timeout")

        with patch.object(chat_client, "_build_response", side_effect=mock_error):
            chunks = []
            async for chunk in chat_client._astream(mock_messages):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert isinstance(chunks[0], ChatGenerationChunk)
            assert (
                "Error: Connection timed out while receiving data from Amazon Q."
                == chunks[0].text
            )

    @pytest.mark.asyncio
    async def test_stream_aws_error(
        self, chat_client: ChatAmazonQ, mock_messages: List[BaseMessage]
    ) -> None:
        """Test AWS error handling in streaming."""
        mock_error = ClientError(
            operation_name="TestOperation",
            error_response={"Error": {"Code": "TestError", "Message": "Test message"}},
        )

        async def mock_build_response(*args, **kwargs):
            raise mock_error

        with patch.object(
            chat_client, "_build_response", side_effect=mock_build_response
        ):
            chunks = [chunk async for chunk in chat_client._astream(mock_messages)]
            assert len(chunks) == 1


class TestChatAmazonQResponseHandling:
    def test_create_chat_message_params(self, chat_client: ChatAmazonQ) -> None:
        """Test chat message parameter creation."""
        mock_message = MagicMock()
        mock_message.content = "Test content"
        mock_message.conversation_id = "test_id"
        mock_message.history = []

        params = chat_client._create_chat_message_params(mock_message)
        assert params["message"] == "Test content"
        assert params["conversation_id"] == "test_id"
        assert params["history"] == []

    def test_handle_stream(self, chat_client: ChatAmazonQ) -> None:
        """Test stream handling."""
        mock_stream = MagicMock()
        mock_stream.__iter__ = Mock(return_value=iter([{"chunk": "Test"}]))
        mock_stream.close = Mock()

        chunks = list(chat_client._handle_stream(mock_stream))
        assert len(chunks) > 0
        mock_stream.close.assert_called_once()

    def test_handle_stream_no_close(self, chat_client: ChatAmazonQ) -> None:
        """Test stream handling without close method."""
        mock_stream = iter([{"chunk": "Test"}])
        chunks = list(chat_client._handle_stream(mock_stream))
        assert len(chunks) > 0


class TestChatAmazonQEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_messages(self, chat_client: ChatAmazonQ) -> None:
        """Test empty message list handling."""
        with pytest.raises(ValueError):
            await chat_client._agenerate([])

    @pytest.mark.asyncio
    async def test_invalid_message_type(self, chat_client: ChatAmazonQ) -> None:
        """Test invalid message type handling."""
        with pytest.raises(AttributeError):
            await chat_client._agenerate([{"invalid": "message"}])  # type: ignore

    @pytest.mark.asyncio
    async def test_large_message(self, chat_client: ChatAmazonQ) -> None:
        """Test large message handling."""
        large_message = HumanMessage(content="x" * 1000000)

        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value="Response")

        with patch.object(chat_client, "_build_response", return_value="Response"):
            result = await chat_client._agenerate([large_message])
            assert result is not None
            assert isinstance(result, ChatResult)
            assert result.generations[0].message.content == "Response"


class TestChatAmazonQAuthentication:
    def test_get_current_user(
        self, chat_client: ChatAmazonQ, mock_user: StarletteUser
    ) -> None:
        """Test current user retrieval."""
        assert chat_client._get_current_user() == mock_user

    def test_missing_user(self, chat_client: ChatAmazonQ) -> None:
        """Test missing user handling."""
        chat_client.metadata = {}
        with pytest.raises(KeyError):
            chat_client._get_current_user()


@pytest.mark.asyncio
async def test_build_response(chat_client: ChatAmazonQ, mock_user: StarletteUser):
    """Test response building."""
    # Create proper message format
    test_messages: List[BaseMessage] = [HumanMessage(content="Test message")]

    mock_response = {"response": "Test response"}
    mock_client = AsyncMock()
    mock_client.send_chat_message = AsyncMock(return_value=mock_response)

    with patch.object(chat_client, "_get_client", return_value=mock_client):
        response = await chat_client._build_response(test_messages)
        assert mock_client.send_chat_message.called
        assert mock_client.send_chat_message.return_value == mock_response
        assert response == mock_response


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
