from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import ChatMessage

from ai_gateway.auth.glgo import GlgoAuthority
from ai_gateway.integrations.amazon_q.chat import ChatAmazonQ
from ai_gateway.integrations.amazon_q.client import AmazonQClient, AmazonQClientFactory


class TestChatAmazonQ:
    @pytest.fixture
    def mock_credentials(self):
        return {
            "AccessKeyId": "test-access-key",
            "SecretAccessKey": "test-secret-key",
            "SessionToken": "test-session-token",
        }

    @pytest.fixture
    def mock_glgo_authority(self):
        return MagicMock(spec=GlgoAuthority)

    @pytest.fixture
    def mock_sts_client(self):
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def mock_boto3(self, mock_sts_client):
        with patch("ai_gateway.integrations.amazon_q.client.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_sts_client
            yield mock_boto3

    @pytest.fixture
    def mock_q_client(self):
        with patch(
            "ai_gateway.integrations.amazon_q.client.q_boto3.client"
        ) as mock_client:
            yield mock_client.return_value

    @pytest.fixture
    def q_client(self, mock_credentials, mock_q_client):
        return AmazonQClient(
            url="https://q-api.example.com",
            region="us-west-2",
            credentials=mock_credentials,
        )

    @pytest.fixture
    def amazon_q_client_factory(self, mock_glgo_authority, mock_boto3, q_client):
        with patch(
            "ai_gateway.integrations.amazon_q.client.AmazonQClientFactory.get_client"
        ) as mock_get_client:
            mock_get_client.return_value = q_client
            yield AmazonQClientFactory(
                glgo_authority=mock_glgo_authority,
                endpoint_url="https://mock.endpoint",
                region="us-east-1",
            )

    @pytest.fixture
    def chat_amazon_q(self, amazon_q_client_factory):
        return ChatAmazonQ(amazon_q_client_factory=amazon_q_client_factory)

    @pytest.fixture
    def sample_messages(self):
        return [
            ChatMessage(content="What is the weather like in some city?", role="user")
        ]

    def test_generate_response(self, chat_amazon_q, sample_messages, mock_q_client):
        mock_q_client.send_message.return_value = (
            "Amazon Q Response: Some response content"
        )

        result = chat_amazon_q.invoke(sample_messages)

        assert result.content.startswith("Amazon Q Response:")

        assert result.response_metadata["token_usage"] == 100
        assert result.response_metadata["model"] == "amazon_q"

    def test_stream_response(
        self, chat_amazon_q, sample_messages, mock_boto3, mock_q_client
    ):
        mock_q_client.send_message.return_value = {
            "responseStream": [
                {
                    "assistantResponseEvent": {
                        "content": "Amazon Q Response: Some response content"
                    }
                }
            ]
        }

        stream_generator = chat_amazon_q.stream(sample_messages)

        chunk = next(stream_generator)

        assert chunk.content.startswith("Amazon Q Response:")

    def test_identifying_params(self, chat_amazon_q):
        params = chat_amazon_q._identifying_params
        assert params == {"model": "amazon_q"}

    def test_llm_type(self, chat_amazon_q):
        assert chat_amazon_q._llm_type == "amazon_q"
