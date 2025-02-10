"""
Message Processor Module for Amazon Q Integration.
Handles the processing, transformation, and organization of chat messages between users and Amazon Q.
This module is responsible for managing message history, system messages, and conversation state.

Example Usage:
    processor = MessageProcessor()
    messages = [
        SystemMessage(content="You are a helpful assistant"),
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
        HumanMessage(content="How are you?")
    ]
    user = StarletteUser(global_user_id="user123")
    processed = processor.process_messages(messages, user)
"""

from dataclasses import dataclass
from typing import List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ai_gateway.api.auth_utils import StarletteUser


class HistoryItem(TypedDict, total=False):
    """Type definition for history items"""

    userInputMessage: str
    assistantResponseMessage: str


@dataclass
class ProcessedMessage:
    """
    Data class representing a fully processed message ready for transmission to Amazon Q.

    Attributes:
        content (str): The primary message content to be sent to Amazon Q
        conversation_id (str): Unique identifier for tracking the conversation thread
        history (List[HistoryItem]): Chronological list of previous message exchanges
    """

    content: str
    conversation_id: str
    history: List[HistoryItem]


class MessageProcessor:
    """
    Handles the processing and transformation of chat messages for Amazon Q integration.

    This class is responsible for:
    - Processing and organizing message history
    - Handling system messages and their integration
    - Managing conversation state and context
    - Creating standardized message formats for Amazon Q
    """

    def process_messages(
        self, messages: List[BaseMessage], user: StarletteUser
    ) -> ProcessedMessage:
        """
        Process a list of messages and prepare them for sending to Amazon Q.

        This method orchestrates the entire message processing workflow:
        1. Creates a copy of the message list
        2. Processes any system messages
        3. Extracts the main content
        4. Builds the conversation history
        5. Generates a conversation ID

        Args:
            messages (List[BaseMessage]): Raw list of messages to process
            user (StarletteUser): Current user context for the conversation

        Returns:
            ProcessedMessage: Fully processed message ready for Amazon Q
        """
        messages_copy = self._copy_messages(messages)
        content = self._extract_content(messages_copy)
        history = self._create_history(messages_copy)
        conversation_id = self._create_conversation_id(user)

        return self._create_processed_message(content, conversation_id, history)

    def _copy_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Create a safe copy of messages and handle system messages.

        Creates a copy of the message list to prevent modifications to the original
        and processes any system messages present in the list.

        Args:
            messages (List[BaseMessage]): Original list of messages

        Returns:
            List[BaseMessage]: Processed copy of messages with system messages handled
        """
        messages_copy = messages.copy()
        print("messages_copy", messages_copy)
        self._handle_system_message(messages_copy)
        return messages_copy

    def _handle_system_message(self, messages: List[BaseMessage]) -> None:
        """
        Process and integrate system messages with user messages.

        If a system message is present at the start of the list:
        1. Removes it from the list
        2. Merges its content with the next message if one exists
        This ensures system instructions are properly integrated into the conversation.

        Args:
            messages (List[BaseMessage]): List of messages to process
        """
        if messages and isinstance(messages[0], SystemMessage):
            system_message = messages.pop(0)
            print("system_message", system_message)
            print(
                "messages and system_message.content is not None",
                messages and system_message.content is not None,
            )
            if messages and system_message.content is not None:
                # Create new content by concatenating strings
                new_content = f"{system_message.content}\n{messages[0].content}"
                messages[0].content = new_content

    def _extract_content(self, messages: List[BaseMessage]) -> str:
        """
        Extract the content from the last message in the list.

        Removes and returns the content of the last message, which represents
        the current message to be processed.

        Args:
            messages (List[BaseMessage]): List of messages

        Returns:
            str: Content of the last message, or empty string if no messages exist
        """
        if not messages:
            return ""

        current_message: Optional[BaseMessage] = messages.pop() if messages else None
        if not current_message:
            raise ValueError("No current message found")

        content = current_message.content

        return "" if content is None else str(content)

    def _create_history(self, messages: List[BaseMessage]) -> List[HistoryItem]:
        """
        Create a structured history of message exchanges.

        Processes the remaining messages in pairs (user message and assistant response)
        to build a chronological history of the conversation.

        Args:
            messages (List[BaseMessage]): List of messages to process

        Returns:
            List[Dict[str, str]]: Structured list of message exchanges
        """
        history: List[HistoryItem] = []

        for message in messages:
            if isinstance(message, HumanMessage):
                history.append({"userInputMessage": str(message.content)})
            elif isinstance(message, AIMessage):
                history.append({"assistantResponseMessage": str(message.content)})

        return history

    def _create_conversation_id(self, user: StarletteUser) -> str:
        """
        Generate a unique conversation identifier for the current user.

        Creates a conversation ID based on the user's global identifier
        to maintain conversation context.

        Args:
            user (StarletteUser): The current user

        Returns:
            str: Generated conversation ID
        """
        return str(user.global_user_id)

    def _create_processed_message(
        self, content: str, conversation_id: str, history: List[HistoryItem]
    ) -> ProcessedMessage:
        """
        Create a final ProcessedMessage instance with all components.

        Combines all processed elements into a single ProcessedMessage object
        ready for transmission to Amazon Q.

        Args:
            content (str): The main message content
            conversation_id (str): The generated conversation identifier
            history (List[Dict[str, str]]): The processed conversation history

        Returns:
            ProcessedMessage: Complete processed message ready for sending
        """
        return ProcessedMessage(
            content=content, conversation_id=conversation_id, history=history
        )
