import pytest
from langchain_core.messages import ChatMessage

from ai_gateway.integrations.amazon_q.chat import ChatAmazonQ


class TestChatAmazonQ:
    @pytest.fixture
    def chat_amazon_q(self):
        return ChatAmazonQ()

    @pytest.fixture
    def sample_messages(self):
        return [
            ChatMessage(content="What is the weather like in some city?", role="user")
        ]

    def test_generate_response(self, chat_amazon_q, sample_messages):
        result = chat_amazon_q.invoke(sample_messages)

        assert result.content.startswith("Amazon Q Response:")

        assert result.response_metadata["token_usage"] == 100
        assert result.response_metadata["model"] == "amazon_q"

    def test_stream_response(self, chat_amazon_q, sample_messages):
        stream_generator = chat_amazon_q.stream(sample_messages)

        chunk = next(stream_generator)

        assert chunk.content.startswith("Amazon Q Response:")

    def test_identifying_params(self, chat_amazon_q):
        params = chat_amazon_q._identifying_params
        assert params == {"model": "amazon_q"}

    def test_llm_type(self, chat_amazon_q):
        assert chat_amazon_q._llm_type == "amazon_q"
