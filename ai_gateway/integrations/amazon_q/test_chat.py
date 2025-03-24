from unittest import mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGenerationChunk

from ai_gateway.integrations.amazon_q.chat import ChatAmazonQ
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory
from langchain_core.messages import AIMessageChunk


class TestChatAmazonQ:
    @pytest.fixture
    def mock_q_client_factory(self):
        return mock.MagicMock(AmazonQClientFactory)

    @pytest.fixture
    def chat_amazon_q(self, mock_q_client_factory):
        return ChatAmazonQ(amazon_q_client_factory=mock_q_client_factory)

    @pytest.fixture
    def messages(self):
        return [
            SystemMessage(content="system message", role="user"),
            HumanMessage(content="user message", role="user"),
            AIMessage(content="assistant message", role="user"),
            HumanMessage(content="latest user message", role="user"),
            AIMessage(content="latest assistant message", role="user"),
        ]

    @pytest.fixture
    def mock_q_client(self, mock_q_client_factory):
        mock_stream = mock.MagicMock()
        mock_stream.close = mock.MagicMock()
        mock_stream.__iter__.return_value = [
            {"assistantResponseEvent": {"content": "Streamed response"}}
        ]
        mock_response = {"responseStream": mock_stream}

        q_client = mock.MagicMock()
        q_client.send_message.return_value = mock_response
        mock_q_client_factory.get_client.return_value = q_client

        return q_client

    @pytest.fixture
    def mock_user(self):
        return mock.MagicMock()

    def test_generate_response(
        self,
        chat_amazon_q,
        messages,
        mock_user,
        mock_q_client,
        mock_q_client_factory,
    ):
        role_arn = "role-arn"
        result = chat_amazon_q.invoke(messages, user=mock_user, role_arn=role_arn)

        assert result.content == "Streamed response"
        mock_q_client_factory.get_client.assert_called_once_with(
            current_user=mock_user, role_arn=role_arn
        )
        mock_q_client.send_message.assert_called_once_with(
            message={
                "content": "system message latest user message latest assistant message"
            },
            history=[
                {"userInputMessage": {"content": "user message"}},
                {"assistantResponseMessage": {"content": "assistant message"}},
            ],
        )

    def test_stream(
        self, chat_amazon_q, mock_user, mock_q_client, mock_q_client_factory
    ):
        role_arn = "role-arn"

        messages = [
            SystemMessage(content="system message", role="user"),
            HumanMessage(content="user message", role="user"),
        ]

        stream = chat_amazon_q._stream(messages, user=mock_user, role_arn=role_arn)

        chunk = next(stream)
        assert isinstance(chunk, ChatGenerationChunk)
        assert chunk.message.content == "Streamed response"
        mock_q_client_factory.get_client.assert_called_once_with(
            current_user=mock_user, role_arn=role_arn
        )
        mock_q_client.send_message.assert_called_once_with(
            message={"content": "system message user message"},
            history=[],
        )

    def test_stream_history(
        self,
        chat_amazon_q,
        messages,
        mock_user,
        mock_q_client,
        mock_q_client_factory,
    ):
        role_arn = "role-arn"

        stream = chat_amazon_q._stream(messages, user=mock_user, role_arn=role_arn)

        chunk = next(stream)
        assert isinstance(chunk, ChatGenerationChunk)
        assert chunk.message.content == "Streamed response"
        mock_q_client_factory.get_client.assert_called_once_with(
            current_user=mock_user, role_arn=role_arn
        )
        mock_q_client.send_message.assert_called_once_with(
            message={
                "content": "system message latest user message latest assistant message"
            },
            history=[
                {"userInputMessage": {"content": "user message"}},
                {"assistantResponseMessage": {"content": "assistant message"}},
            ],
        )

    def test_identifying_params(self, chat_amazon_q):
        params = chat_amazon_q._identifying_params
        assert params == {"model": "amazon_q"}

    def test_llm_type(self, chat_amazon_q):
        assert chat_amazon_q._llm_type == "amazon_q"

    def test_valid_single_reference(self, chat_amazon_q):
        """Test with a valid event containing a single reference."""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": "example-repo"},
                        "licenseName": {"shape": "MIT"},
                        "url": {"shape": "https://github.com/example/repo"},
                        "recommendationContentSpan": {"shape": "lines 10-20"}
                    }
                ]
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert isinstance(result.message, AIMessageChunk)
        assert "example-repo [MIT]: https://github.com/example/repo (lines 10-20)" in result.message.content
        
    def test_valid_multiple_references(self, chat_amazon_q):
        """Test with a valid event containing multiple references."""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": "repo1"},
                        "licenseName": {"shape": "MIT"},
                        "url": {"shape": "https://github.com/repo1"},
                        "recommendationContentSpan": {"shape": "lines 1-10"}
                    },
                    {
                        "repository": {"shape": "repo2"},
                        "licenseName": {"shape": "Apache-2.0"},
                        "url": {"shape": "https://github.com/repo2"},
                        "recommendationContentSpan": {"shape": "lines 5-15"}
                    }
                ]
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert "repo1 [MIT]: https://github.com/repo1 (lines 1-10)" in result.message.content
        assert "repo2 [Apache-2.0]: https://github.com/repo2 (lines 5-15)" in result.message.content
        
    def test_missing_optional_fields(self, chat_amazon_q):
        """Test with missing optional fields in references."""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": "example-repo"},
                        # Missing licenseName
                        "url": {"shape": "https://github.com/example/repo"},
                        # Missing recommendationContentSpan
                    }
                ]
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert "example-repo: https://github.com/example/repo" in result.message.content
        
    def test_empty_references_list(self, chat_amazon_q):
        """Test with an empty references list."""
        event = {
            "codeReferenceEvent": {
                "references": []
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert result.message.content == ""
        
    def test_missing_references_key(self, chat_amazon_q):
        """Test with missing references key."""
        event = {
            "codeReferenceEvent": {}
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert result.message.content == ""
        
    def test_missing_code_reference_event(self, chat_amazon_q):
        """Test with missing codeReferenceEvent."""
        event = {}
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert result.message.content == ""
        
    def test_invalid_references_type(self, chat_amazon_q):
        """Test with invalid references type (string instead of list)."""
        event = {
            "codeReferenceEvent": {
                "references": "not a list"
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert result.message.content == ""
        
    def test_invalid_reference_item_type(self, chat_amazon_q):
        """Test with invalid reference item type (string instead of dict)."""
        event = {
            "codeReferenceEvent": {
                "references": ["not a dict"]
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        assert result.message.content == ""
        
    def test_missing_shape_in_fields(self, chat_amazon_q):
        """Test with missing shape in fields."""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": "missing-shape",
                        "licenseName": {"shape": "MIT"},
                        "url": {"shape": "https://github.com/example/repo"}
                    }
                ]
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        # The method should handle this gracefully, either by skipping the field or using a default
        assert result.message.content != ""
        
    def test_null_values_in_fields(self, chat_amazon_q):
        """Test with null values in fields."""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": None},
                        "licenseName": {"shape": "MIT"},
                        "url": {"shape": "https://github.com/example/repo"}
                    }
                ]
            }
        }
        
        result = chat_amazon_q._process_code_reference_event(event)
        
        assert isinstance(result, ChatGenerationChunk)
        # The method should handle this gracefully
        assert result.message.content != ""
