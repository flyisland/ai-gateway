"""
Amazon Q Chat Integration Module.
Provides the main chat interface for interacting with Amazon Q, handling message generation,
streaming responses, and error management.

Example Usage:
    # Initialize the chat model
    amazon_q = ChatAmazonQ(
        amazon_q_client_factory=AmazonQClientFactory(),
        model="amazon_q"
    )

    # Generate a response
    messages = [
        SystemMessage(content="You are a helpful assistant"),
        HumanMessage(content="Hello, how can you help me?")
    ]
    response = amazon_q.generate(messages)

    # Stream responses
    for chunk in amazon_q.stream(messages):
        print(chunk.content)
"""

import os
from dataclasses import field
from typing import Any, Dict, Iterator, List, Optional, cast

from botocore.exceptions import ClientError
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from requests.exceptions import Timeout

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.integrations.amazon_q.error_handers import AWSErrorHandler
from ai_gateway.integrations.amazon_q.message_processor import (
    MessageProcessor,
    ProcessedMessage,
)
from ai_gateway.integrations.amazon_q.response_handlers import (
    ResponseHandler,
    StreamEvent,
)


class ChatAmazonQ(BaseChatModel):
    """
    Main chat model class for Amazon Q integration.
    Handles message generation, streaming responses, and error management.

    The class is organized into these main sections:
    1. Initialization and Properties
    2. Message Generation and Processing
    3. Streaming Functionality
    4. Error Handling
    5. Client Management
    """

    # Section 1: Initialization and Properties
    amazon_q_client_factory: Any
    model: str = field(default="amazon_q")
    message_processor: MessageProcessor = field(default_factory=MessageProcessor)
    response_handler: ResponseHandler = field(default_factory=ResponseHandler)

    def __post_init__(self) -> None:
        """
        Post-initialization setup.
        Called after dataclass initialization.
        """
        self.metadata: Dict[str, Any] = {}
        super().__init__()

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Get identifying parameters for the model."""
        return {"model": self.model}

    @property
    def _llm_type(self) -> str:
        """Get the LLM type identifier."""
        return "amazon_q"

    # Section 2: Message Generation and Processing
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate a response for the given messages.

        Args:
            messages: List of input messages to process
            stop: Optional stop sequences for generation
            run_manager: Optional callback manager
            kwargs: Additional keyword arguments

        Returns:
            ChatResult: Generated response wrapped in a ChatResult object
        """
        message: str = self._build_response(messages=messages)
        return self._create_chat_result(message)

    def _create_chat_result(self, message: str) -> ChatResult:
        """
        Create a ChatResult object from a message.

        Args:
            message: The message to wrap in a ChatResult

        Returns:
            ChatResult: Formatted chat result with the message
        """
        return ChatResult(
            generations=[self._create_chat_generation(message)],
            llm_output=self._create_llm_output(),
        )

    def _create_chat_generation(self, message: str) -> ChatGeneration:
        """
        Create a ChatGeneration object from a message.

        Args:
            message: The message content

        Returns:
            ChatGeneration: Wrapped message in a ChatGeneration object
        """
        return ChatGeneration(message=AIMessage(content=message))

    def _create_llm_output(self) -> Dict[str, Any]:
        """
        Create the LLM output dictionary with metadata.

        Returns:
            Dict[str, Any]: Dictionary containing token usage and model information
        """
        return {"token_usage": 100, "model": "amazon_q"}

    def _build_response(self, messages: List[BaseMessage]):
        """
        Build a response from the given messages.

        Args:
            messages: List of messages to process

        Returns:
            str: The built response from Amazon Q
        """
        current_user: StarletteUser = self._get_current_user()
        q_client: Any = self._get_client(current_user)
        processed_message: ProcessedMessage = self._process_messages(
            messages, current_user
        )
        return self._send_chat_message(q_client, processed_message)

    def _process_messages(
        self, messages: List[BaseMessage], current_user: StarletteUser
    ) -> ProcessedMessage:
        """
        Process the input messages for the current user.

        Args:
            messages: List of messages to process
            current_user: The current user

        Returns:
            ProcessedMessage: Processed message ready for sending
        """
        return self.message_processor.process_messages(messages, current_user)

    def _create_chat_message_params(
        self, processed_message: ProcessedMessage
    ) -> Dict[str, Any]:
        """
        Create parameters for sending a chat message.

        Args:
            processed_message: The processed message

        Returns:
            Dict[str, Any]: Parameters for the chat message
        """
        return {
            "message": processed_message.content,
            "conversation_id": processed_message.conversation_id,
            "history": processed_message.history,
        }

    # Section 3: Streaming Functionality
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """
        Stream responses for the given messages.

        Args:
            messages: List of input messages to process
            stop: Optional stop sequences for generation
            run_manager: Optional callback manager
            kwargs: Additional keyword arguments

        Yields:
            ChatGenerationChunk: Chunks of the generated response
        """
        try:
            response: Dict[str, Any] = self._build_response(messages=messages)
            yield from self._handle_stream(response["responseStream"])
        except Exception as e:
            yield from self._handle_stream_error(e)

    def _handle_stream(
        self, stream: Iterator[Dict[str, Any]]
    ) -> Iterator[ChatGenerationChunk]:
        """
        Handle the streaming response from Amazon Q.

        Args:
            stream: Iterator of response events

        Yields:
            ChatGenerationChunk: Response content chunks
        """
        try:
            yield from self._process_stream_events(stream)
        finally:
            self._close_stream(stream)

    def _process_stream_events(
        self, stream: Iterator[Dict[str, Any]]
    ) -> Iterator[ChatGenerationChunk]:
        """
        Process individual events from the response stream.

        Args:
            stream: Iterator of response events

        Yields:
            ChatGenerationChunk: Processed content chunks
        """
        for event in stream:
            if not isinstance(event, dict):
                yield self.response_handler.create_error_chunk(
                    "Invalid event format: not a dictionary"
                )
                continue

            # Cast the validated dictionary to StreamEvent
            stream_event = cast(StreamEvent, event)
            response = self.response_handler.process_stream_event(stream_event)

            if response.error:
                yield self.response_handler.create_error_chunk(response.error)
            else:
                yield self.response_handler.create_content_chunk(response.content)

    def _close_stream(self, stream: Iterator[Dict[str, Any]]) -> None:
        """
        Safely close the response stream.

        Args:
            stream: The stream to close
        """
        if hasattr(stream, "close") and callable(getattr(stream, "close")):
            try:
                stream.close()
            except Exception:
                pass

    # Section 4: Error Handling
    def _handle_stream_error(self, error: Exception) -> Iterator[ChatGenerationChunk]:
        """
        Handle different types of streaming errors.

        Args:
            error: The exception that occurred

        Yields:
            ChatGenerationChunk: Error message chunks
        """
        if isinstance(error, Timeout):
            yield self._create_timeout_error()
        elif isinstance(error, ClientError):
            yield self._create_aws_error(error)
        else:
            yield self._create_generic_error(error)

    def _create_timeout_error(self) -> ChatGenerationChunk:
        """
        Create an error chunk for timeout errors.

        Returns:
            ChatGenerationChunk: Timeout error message
        """
        return self.response_handler.create_error_chunk(
            "Connection timed out while receiving data from Amazon Q."
        )

    def _create_aws_error(self, error: ClientError) -> ChatGenerationChunk:
        """
        Create an error chunk for AWS-specific errors.

        Args:
            error: The AWS client error

        Returns:
            ChatGenerationChunk: AWS error message
        """
        error_config = AWSErrorHandler.handle_client_error(error)
        return self.response_handler.create_error_chunk(
            f"({error_config.code}): {error_config.message}"
        )

    def _create_generic_error(self, error: Exception) -> ChatGenerationChunk:
        """
        Create an error chunk for general exceptions.

        Args:
            error: The exception that occurred

        Returns:
            ChatGenerationChunk: Generic error message
        """
        return self.response_handler.create_error_chunk(str(error))

    # Section 5: Client Management
    def _get_current_user(self) -> StarletteUser:
        """
        Get the current user from metadata.

        Returns:
            StarletteUser: The current user making the request
        """
        return self.metadata["user"]

    def _get_client(self, current_user: StarletteUser) -> Any:
        """
        Get an Amazon Q client for the current user.

        Args:
            current_user: The current user

        Returns:
            Any: Configured Amazon Q client
        """
        role_arn: Optional[str] = self._get_role_arn()
        return self._create_client(current_user, role_arn)

    def _get_role_arn(self) -> Optional[str]:
        """
        Get the AWS role ARN from environment variables.

        Returns:
            Optional[str]: The role ARN if configured
        """
        return os.environ.get("AWS_ROLE_ARN")

    def _create_client(
        self, current_user: StarletteUser, role_arn: Optional[str]
    ) -> Any:
        """
        Create an Amazon Q client.

        Args:
            current_user: The current user
            role_arn: Optional role ARN for AWS authentication

        Returns:
            Any: Configured Amazon Q client
        """
        return self.amazon_q_client_factory.get_client(
            current_user=current_user,
            auth_header=current_user.cloud_connector_token,
            role_arn=role_arn,
        )

    def _send_chat_message(
        self, q_client: Any, processed_message: ProcessedMessage
    ) -> str:
        """
        Send a chat message to Amazon Q.

        Args:
            q_client: The Amazon Q client
            processed_message: The processed message to send

        Returns:
            str: Response from Amazon Q
        """
        return q_client.send_chat_message(
            self._create_chat_message_params(processed_message)
        )
