from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatResult

from ai_gateway.models.v2.chat_fireworks import ChatFireworks


class TestChatFireworks:
    """Test suite for ChatFireworks class focusing on header configuration."""

    @pytest.fixture
    def chat_fireworks(self):
        """Create a ChatFireworks instance for testing."""
        return ChatFireworks()

    @pytest.fixture
    def sample_messages(self):
        """Sample messages for testing."""
        return [HumanMessage(content="Hello, world!")]

    def test_setup_fireworks_kwargs_with_cache_disabled(self, chat_fireworks):
        """Test that prompt caching is disabled when using_cache is False."""
        kwargs = {"using_cache": "False", "other_param": "value"}

        chat_fireworks._setup_fireworks_kwargs(kwargs)

        assert kwargs["prompt_cache_max_len"] == 0
        assert "using_cache" not in kwargs  # Should be popped
        assert kwargs["other_param"] == "value"  # Other params preserved

    def test_setup_fireworks_kwargs_with_cache_enabled(self, chat_fireworks):
        """Test that prompt caching is not modified when using_cache is True."""
        kwargs = {"using_cache": "True", "other_param": "value"}

        chat_fireworks._setup_fireworks_kwargs(kwargs)

        assert "prompt_cache_max_len" not in kwargs
        assert "using_cache" not in kwargs  # Should be popped
        assert kwargs["other_param"] == "value"  # Other params preserved

    def test_setup_fireworks_kwargs_with_session_id(self, chat_fireworks):
        """Test that session affinity header is added when session_id is provided."""
        kwargs = {"session_id": "test-session-123", "other_param": "value"}

        chat_fireworks._setup_fireworks_kwargs(kwargs)

        assert "session_id" not in kwargs  # Should be popped
        assert "extra_headers" in kwargs
        assert kwargs["extra_headers"]["x-session-affinity"] == "test-session-123"
        assert kwargs["other_param"] == "value"  # Other params preserved

    @pytest.mark.asyncio
    async def test_astream_passes_modified_kwargs_to_super(
        self, chat_fireworks, sample_messages
    ):
        """Test that _astream passes modified kwargs to super()._astream."""
        with (
            patch.object(
                chat_fireworks,
                "_setup_fireworks_kwargs",
                wraps=chat_fireworks._setup_fireworks_kwargs,
            ) as mock_setup,
            patch(
                "ai_gateway.models.v2.chat_litellm.ChatLiteLLM._astream"
            ) as mock_super_astream,
        ):

            # Configure mock to return an async generator
            async def mock_generator():
                yield AsyncMock()

            mock_super_astream.return_value = mock_generator()

            kwargs = {
                "using_cache": "False",
                "session_id": "test-session",
                "temperature": 0.7,
            }

            # Consume the async generator
            result = []
            async for chunk in chat_fireworks._astream(
                messages=sample_messages, **kwargs
            ):
                result.append(chunk)

            mock_setup.assert_called_once()

            # Verify super()._astream was called with modified kwargs
            mock_super_astream.assert_called_once()
            call_kwargs = mock_super_astream.call_args.kwargs

            # Check that fireworks-specific params were processed
            assert "using_cache" not in call_kwargs
            assert "session_id" not in call_kwargs
            assert call_kwargs["prompt_cache_max_len"] == 0
            assert call_kwargs["extra_headers"]["x-session-affinity"] == "test-session"
            assert call_kwargs["temperature"] == 0.7  # Other params preserved

    @pytest.mark.asyncio
    async def test_agenerate_passes_modified_kwargs_to_super(
        self, chat_fireworks, sample_messages
    ):
        """Test that _agenerate passes modified kwargs to super()._agenerate."""
        with (
            patch.object(
                chat_fireworks,
                "_setup_fireworks_kwargs",
                wraps=chat_fireworks._setup_fireworks_kwargs,
            ) as mock_setup,
            patch(
                "ai_gateway.models.v2.chat_litellm.ChatLiteLLM._agenerate"
            ) as mock_super_agenerate,
        ):

            # Configure mock to return a ChatResult
            mock_super_agenerate.return_value = AsyncMock(spec=ChatResult)

            kwargs = {
                "using_cache": "True",
                "session_id": "test-session-gen",
                "max_tokens": 100,
            }

            await chat_fireworks._agenerate(messages=sample_messages, **kwargs)

            # Verify _setup_fireworks_kwargs was called with the kwargs
            mock_setup.assert_called_once()

            # Verify super()._agenerate was called with modified kwargs
            mock_super_agenerate.assert_called_once()
            call_kwargs = mock_super_agenerate.call_args.kwargs

            # Check that fireworks-specific params were processed
            assert "using_cache" not in call_kwargs
            assert "session_id" not in call_kwargs
            assert (
                "prompt_cache_max_len" not in call_kwargs
            )  # Should not be set for "True"
            assert (
                call_kwargs["extra_headers"]["x-session-affinity"] == "test-session-gen"
            )
            assert call_kwargs["max_tokens"] == 100  # Other params preserved

    def test_setup_fireworks_kwargs_edge_cases(self, chat_fireworks):
        """Test edge cases for _setup_fireworks_kwargs method."""
        # Test with empty kwargs
        kwargs = {}
        chat_fireworks._setup_fireworks_kwargs(kwargs)
        assert kwargs == {}

        # Test with None session_id (should be treated as falsy)
        kwargs = {"session_id": None}
        chat_fireworks._setup_fireworks_kwargs(kwargs)
        assert "extra_headers" not in kwargs
        assert "session_id" not in kwargs

        # Test with empty string session_id (should be treated as falsy)
        kwargs = {"session_id": ""}
        chat_fireworks._setup_fireworks_kwargs(kwargs)
        assert "extra_headers" not in kwargs
        assert "session_id" not in kwargs

        # Test with using_cache as different string values
        kwargs = {"using_cache": "false"}  # lowercase
        chat_fireworks._setup_fireworks_kwargs(kwargs)
        assert kwargs["prompt_cache_max_len"] == 0

        kwargs = {"using_cache": "FALSE"}  # uppercase
        chat_fireworks._setup_fireworks_kwargs(kwargs)
        assert kwargs["prompt_cache_max_len"] == 0
