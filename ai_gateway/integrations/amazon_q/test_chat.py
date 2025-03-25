from unittest import mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGenerationChunk

from ai_gateway.integrations.amazon_q.chat import (
    ChatAmazonQ,
    CodeReference,
    CodeReferenceEvent,
    Repository,
)
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory


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

    def assert_chunk_content(self, chunks, expected_content):
        """Helper method to assert chunk content"""
        chunk_list = list(chunks)
        if not expected_content:
            assert len(chunk_list) == 1
            assert chunk_list[0].message.content == ""
        else:
            assert len(chunk_list) == 1
            assert chunk_list[0].message.content == expected_content

    def test_process_complete_reference(self, chat_amazon_q):
        """Test processing a complete reference with all fields present"""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": "aws-sdk"},
                        "licenseName": {"shape": "MIT"},
                        "url": {"shape": "https://github.com/aws/aws-sdk"},
                        "recommendationContentSpan": {"shape": "lines 10-20"},
                    }
                ]
            }
        }
        expected = "aws-sdk [MIT]: https://github.com/aws/aws-sdk (lines 10-20)"
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, expected)

    def test_process_multiple_references(self, chat_amazon_q):
        """Test processing multiple references"""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": "aws-sdk"},
                        "licenseName": {"shape": "MIT"},
                        "url": {"shape": "https://github.com/aws/aws-sdk"},
                        "recommendationContentSpan": {"shape": "lines 10-20"},
                    },
                    {
                        "repository": {"shape": "boto3"},
                        "licenseName": {"shape": "Apache-2.0"},
                        "url": {"shape": "https://github.com/boto/boto3"},
                        "recommendationContentSpan": {"shape": "lines 5-15"},
                    },
                ]
            }
        }
        expected = (
            "aws-sdk [MIT]: https://github.com/aws/aws-sdk (lines 10-20)\n"
            "boto3 [Apache-2.0]: https://github.com/boto/boto3 (lines 5-15)"
        )
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, expected)

    def test_process_missing_optional_fields(self, chat_amazon_q):
        """Test processing reference with missing optional fields"""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": "aws-sdk"},
                        "licenseName": {"shape": "MIT"},
                    }
                ]
            }
        }
        expected = "aws-sdk [MIT]"
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, expected)

    def test_process_direct_string_values(self, chat_amazon_q):
        """Test processing reference with direct string values instead of shape objects"""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": "aws-sdk",
                        "licenseName": "MIT",
                        "url": "https://github.com/aws/aws-sdk",
                        "recommendationContentSpan": "lines 10-20",
                    }
                ]
            }
        }
        expected = "aws-sdk [MIT]: https://github.com/aws/aws-sdk (lines 10-20)"
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, expected)

    def test_process_empty_references(self, chat_amazon_q):
        """Test processing empty references list"""
        event = {"codeReferenceEvent": {"references": []}}
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, "")

    def test_process_invalid_data_structure(self, chat_amazon_q):
        """Test processing invalid data structure"""
        event = {"codeReferenceEvent": "invalid"}
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, "")

    def test_process_mixed_format(self, chat_amazon_q):
        """Test processing mixed format of shape objects and direct strings"""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": {"shape": "aws-sdk"},
                        "licenseName": "MIT",
                        "url": {"shape": "https://github.com/aws/aws-sdk"},
                        "recommendationContentSpan": "lines 10-20",
                    }
                ]
            }
        }
        expected = "aws-sdk [MIT]: https://github.com/aws/aws-sdk (lines 10-20)"
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, expected)

    def test_process_missing_code_reference_event(self, chat_amazon_q):
        """Test processing event with missing codeReferenceEvent"""
        event = {}
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, "")

    def test_process_none_values(self, chat_amazon_q):
        """Test processing reference with None values"""
        event = {
            "codeReferenceEvent": {
                "references": [
                    {
                        "repository": None,
                        "licenseName": None,
                        "url": None,
                        "recommendationContentSpan": None,
                    }
                ]
            }
        }
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, "")

    def test_pydantic_model_validation(self):
        """Test Pydantic model validation"""
        # Test CodeReference model
        reference = CodeReference(
            repository={"shape": "test-repo"},
            licenseName="MIT",
            url={"shape": "https://example.com"},
            recommendationContentSpan="lines 1-10",
        )
        assert isinstance(reference, CodeReference)

        # Test CodeReferenceEvent model
        event = CodeReferenceEvent(references=[reference])
        assert isinstance(event, CodeReferenceEvent)
        assert len(event.references) == 1

    @pytest.mark.parametrize(
        "input_data,expected",
        [
            ({"shape": "test-repo"}, "test-repo"),
            ("direct-string", "direct-string"),
            (None, ""),
        ],
    )
    def test_repository_shape_handling(self, input_data, expected):
        """Test different repository shape formats"""
        reference = CodeReference(repository=input_data)
        shape_value = (
            reference.repository.shape
            if isinstance(reference.repository, Repository)
            else reference.repository or ""
        )
        assert str(shape_value) == expected

    def test_malformed_reference_structure(self, chat_amazon_q):
        """Test handling of malformed reference structure"""
        event = {"codeReferenceEvent": {"references": [{"invalid_key": "value"}]}}
        chunks = chat_amazon_q._process_code_reference_event(event)
        self.assert_chunk_content(chunks, "")

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
