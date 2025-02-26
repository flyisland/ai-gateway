"""
Response handlers for Amazon Q chat interactions.
This module provides classes and utilities for handling streaming responses
and managing chat message processing.

Example event structure:
    {
        "assistantResponseEvent": {
            "content": "Hello, how can I help you?"
        }
    }
"""

from dataclasses import dataclass
from typing import Optional, TypedDict

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk


class AssistantEvent(TypedDict, total=False):
    content: str


class StreamEvent(TypedDict, total=False):
    assistantResponseEvent: AssistantEvent
    messageMetadataEvent: AssistantEvent
    followupPrompt: AssistantEvent
    supplementaryWebLinks: AssistantEvent
    references: AssistantEvent


@dataclass
class StreamResponse:
    """
    Data class representing a streaming response from Amazon Q.

    Attributes:
        content (str): The actual content of the response
        error (Optional[str]): Optional error message if an error occurred during processing
    """

    content: str
    error: Optional[str] = None


class ResponseHandler:
    """
    Handles the processing and management of streaming responses from Amazon Q.
    Provides methods for creating and processing response chunks and error handling.

    The handler supports different types of events:
    - Assistant responses (main conversation)
    - Metadata events (system information)
    - Followup prompts (suggested next questions)
    - Web links (supplementary information)
    - References (source citations)
    """

    # Event type constants
    EVENT_METADATA = "messageMetadataEvent"
    EVENT_ASSISTANT_RESPONSE = "assistantResponseEvent"
    EVENT_FOLLOWUP = "followupPrompt"
    EVENT_WEB_LINKS = "supplementaryWebLinks"
    EVENT_REFERENCES = "references"

    def __init__(self):
        """Initialize the response handler with event type mappings."""
        self._event_handlers = {
            self.EVENT_METADATA: self._create_empty_response,
            self.EVENT_ASSISTANT_RESPONSE: self._process_assistant_response,
            self.EVENT_FOLLOWUP: self._process_followup_prompt_response,
            self.EVENT_WEB_LINKS: self._process_web_link_response,
            self.EVENT_REFERENCES: self._process_references_response,
        }

    # Main Public Interface Methods
    def process_stream_event(self, event: StreamEvent) -> StreamResponse:
        """
        Processes an incoming stream event and converts it to a StreamResponse.
        Handles different types of events and provides error handling.

        Args:
            event (StreamEvent): The event to be processed

        Returns:
            StreamResponse: A processed response containing the appropriate content

        Raises:
            Exception: If there's an error processing the event
        """
        try:
            if not isinstance(event, dict):
                return StreamResponse(
                    content="", error="Invalid event format: not a dictionary"
                )

            for event_type, handler in self._event_handlers.items():
                if event_type in event:
                    return handler(event)

            return self._process_default_event(event)
        except Exception as e:
            return StreamResponse(content="", error=f"Error processing event: {str(e)}")

    def create_error_chunk(self, error_message: str) -> ChatGenerationChunk:
        """
        Creates a chat generation chunk containing an error message.

        Args:
            error_message (str): The error message to be included in the chunk

        Returns:
            ChatGenerationChunk: A formatted error message chunk
        """
        return self._create_chunk(f"Error: {error_message}")

    def create_content_chunk(self, content: str) -> ChatGenerationChunk:
        """
        Creates a chat generation chunk containing normal content.

        Args:
            content (str): The content to be included in the chunk

        Returns:
            ChatGenerationChunk: A formatted content chunk
        """
        return self._create_chunk(content)

    # Event Handler Methods
    def _process_assistant_response(self, event: StreamEvent) -> StreamResponse:
        """
        Processes an assistant response event and extracts its content.

        Args:
            event (StreamEvent): The assistant response event to process

        Returns:
            StreamResponse: A response containing the assistant's message content
        """
        assistant_response = event.get("assistantResponseEvent")
        if not assistant_response:
            return StreamResponse(content="", error="Invalid assistant response event")

        # Type narrowing
        if isinstance(assistant_response, dict):
            content = assistant_response.get("content", "")
            return StreamResponse(content=content)

        return StreamResponse(content="", error="Invalid assistant response format")

    def _process_followup_prompt_response(self, event: StreamEvent) -> StreamResponse:
        """
        Processes a followup prompt event and extracts suggested next questions.

        Args:
            event (StreamEvent): The followup prompt event to process

        Returns:
            StreamResponse: A response containing the followup suggestions
        """
        followup = event.get("followupPrompt")
        if not followup:
            return StreamResponse(content="", error="Invalid followup prompt event")

        if isinstance(followup, dict):
            content = followup.get("content", "")
            return StreamResponse(content=content)

        return StreamResponse(content="", error="Invalid followup prompt format")

    def _process_web_link_response(self, event: StreamEvent) -> StreamResponse:
        """
        Processes a web links event and extracts supplementary information URLs.

        Args:
            event (StreamEvent): The web links event to process

        Returns:
            StreamResponse: A response containing the web links
        """
        web_links = event.get("supplementaryWebLinks")
        if not web_links:
            return StreamResponse(content="", error="Invalid web links event")

        if isinstance(web_links, dict):
            content = web_links.get("content", "")
            return StreamResponse(content=content)

        return StreamResponse(content="", error="Invalid web links format")

    def _process_references_response(self, event: StreamEvent) -> StreamResponse:
        """
        Processes a references event and extracts citation information.

        Args:
            event (StreamEvent): The references event to process

        Returns:
            StreamResponse: A response containing the reference information
        """
        references = event.get("references")
        if not references:
            return StreamResponse(content="", error="Invalid references event")

        if isinstance(references, dict):
            content = references.get("content", "")
            return StreamResponse(content=content)

        return StreamResponse(content="", error="Invalid references format")

    def _process_default_event(self, event: StreamEvent) -> StreamResponse:
        """
        Processes any event that doesn't match other specific event types.
        Extracts content from the default event structure.

        Args:
            event (StreamEvent): The event to process

        Returns:
            StreamResponse: A response containing the event's content
        """
        if isinstance(event, dict):
            content = event.get("content", "")
            if not isinstance(content, str):
                content = str(content)
            return StreamResponse(content=content)
        return StreamResponse(content="")

    # Utility Methods
    def _create_chunk(self, content: str) -> ChatGenerationChunk:
        """
        Internal helper method to create a chat generation chunk with the given content.

        Args:
            content (str): The content to be wrapped in a chunk

        Returns:
            ChatGenerationChunk: A new chunk containing the provided content
        """
        return ChatGenerationChunk(message=AIMessageChunk(content=content))

    def _create_empty_response(self, event: StreamEvent) -> StreamResponse:
        """
        Creates an empty stream response.
        Used for events that don't require content (like metadata events).

        Args:
            event (StreamEvent): The event being processed (unused)

        Returns:
            StreamResponse: A response with empty content
        """
        return StreamResponse(content="")
