from typing import List, Sequence
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.integrations.amazon_q.message_processor import (
    HistoryItem,
    MessageProcessor,
    ProcessedMessage,
)


@pytest.fixture
def message_processor() -> MessageProcessor:
    return MessageProcessor()


@pytest.fixture
def mock_user() -> StarletteUser:
    user = Mock(spec=StarletteUser)
    user.global_user_id = "test-user-123"
    return user


def test_process_empty_messages(
    message_processor: MessageProcessor, mock_user: StarletteUser
) -> None:
    messages: List[BaseMessage] = []
    result = message_processor.process_messages(messages, mock_user)

    assert isinstance(result, ProcessedMessage)
    assert result.content == ""
    assert result.conversation_id == "test-user-123"
    assert result.history == []


def test_process_single_human_message(
    message_processor: MessageProcessor, mock_user: StarletteUser
) -> None:
    messages: List[BaseMessage] = [HumanMessage(content="Hello")]
    result = message_processor.process_messages(messages, mock_user)

    assert result.content == "Hello"
    assert result.conversation_id == "test-user-123"
    assert result.history == []


def test_process_conversation_with_history(
    message_processor: MessageProcessor, mock_user: StarletteUser
) -> None:
    messages: List[BaseMessage] = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
        HumanMessage(content="How are you?"),
    ]

    result = message_processor.process_messages(messages, mock_user)

    assert result.content == "How are you?"
    assert len(result.history) == 2
    assert result.history[0] == {"userInputMessage": "Hello"}
    assert result.history[1] == {"assistantResponseMessage": "Hi there!"}


def test_handle_empty_content(
    message_processor: MessageProcessor, mock_user: StarletteUser
) -> None:
    messages: List[BaseMessage] = [HumanMessage(content="")]
    result = message_processor.process_messages(messages, mock_user)

    assert result.content == ""
    assert result.history == []


def test_handle_missing_content(
    message_processor: MessageProcessor, mock_user: StarletteUser
) -> None:
    messages: List[BaseMessage] = []
    result = message_processor.process_messages(messages, mock_user)

    assert result.content == ""
    assert result.history == []


def test_create_history_alternating_messages(
    message_processor: MessageProcessor, mock_user: StarletteUser
) -> None:
    messages: List[BaseMessage] = [
        HumanMessage(content="Message 1"),
        AIMessage(content="Response 1"),
        HumanMessage(content="Message 2"),
        AIMessage(content="Response 2"),
        HumanMessage(content="Current message"),
    ]

    result = message_processor.process_messages(messages, mock_user)

    expected_history: List[HistoryItem] = [
        {"userInputMessage": "Message 1"},
        {"assistantResponseMessage": "Response 1"},
        {"userInputMessage": "Message 2"},
        {"assistantResponseMessage": "Response 2"},
    ]

    assert result.content == "Current message"
    assert result.history == expected_history


def test_conversation_id_generation(
    message_processor: MessageProcessor, mock_user: StarletteUser
) -> None:
    messages: List[BaseMessage] = [HumanMessage(content="Test message")]
    result = message_processor.process_messages(messages, mock_user)

    assert result.conversation_id == "test-user-123"


def test_copy_messages_maintains_original(message_processor: MessageProcessor) -> None:
    original_messages: List[BaseMessage] = [HumanMessage(content="Original message")]
    copied_messages = message_processor._copy_messages(original_messages)

    assert copied_messages is not original_messages
    assert copied_messages[0].content == original_messages[0].content


def test_extract_content_with_empty_messages(
    message_processor: MessageProcessor,
) -> None:
    messages: List[BaseMessage] = []
    content = message_processor._extract_content(messages)

    assert content == ""


def test_create_history_empty_messages(message_processor: MessageProcessor) -> None:
    messages: List[BaseMessage] = []
    history = message_processor._create_history(messages)

    assert history == []
