import asyncio
import os
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Optional

from fastapi import HTTPException, status
from gitlab_cloud_connector import GitLabUnitPrimitive

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.api.v1.amazon_q.typing import (
    CodeRecommendation,
    CodeSuggestionRequest,
    CodeSuggestionResponse,
    FileContext,
    ProgrammingLanguage,
)
from ai_gateway.api.v3.code.typing import EditorContentCodeSuggestionPayload
from ai_gateway.code_suggestions.base import ModelProvider
from ai_gateway.code_suggestions.processing.base import ModelEngineOutput
from ai_gateway.code_suggestions.processing.ops import lang_from_filename
from ai_gateway.code_suggestions.processing.typing import MetadataPromptBuilder
from ai_gateway.integrations.amazon_q.client import AmazonQClient, AmazonQClientFactory
from ai_gateway.integrations.amazon_q.errors import AWSException
from ai_gateway.internal_events.client import InternalEventsClient
from ai_gateway.models import ModelMetadata as EngineOutputModelMetadata
from ai_gateway.models.base import TokensConsumptionMetadata

logger = getLogger(__name__)


@dataclass
class CodeSuggestionContext:
    """Data class to hold completion context information."""

    current_user: StarletteUser
    internal_event_client: InternalEventsClient
    amazon_q_client_factory: AmazonQClientFactory
    payload: EditorContentCodeSuggestionPayload


class CodeSuggestionService:
    """Service class for handling code completion requests with Amazon Q."""

    def __init__(self, context: CodeSuggestionContext):
        """
        Initialize the CodeCompletionService.

        Args:
            context: CodeCompletionContext containing all necessary dependencies
        """
        self.context = context
        self.q_client: AmazonQClient = None

    async def execute(self) -> list[ModelEngineOutput]:
        """
        Execute the code completion request.

        Returns:
            list[ModelEngineOutput]: List of code completion suggestions

        Raises:
            HTTPException: If user is unauthorized
            AWSException: If AWS service encounters an error
        """
        try:
            self._validate_user_permission()
            self._track_completion_request()
            self._initialize_q_client()

            completion_payload: CodeSuggestionRequest = self._build_completion_payload()
            suggestions = await self._get_completion_suggestions(completion_payload)
            print("DEBUG: Return suggestions", suggestions)

            return self._process_suggestions(suggestions)

        except AWSException as e:
            logger.error("Amazon Q API error: %s", str(e))
            raise e.to_http_exception()

    def _validate_user_permission(self) -> None:
        """Validate if user has required permissions."""
        if not self.context.current_user.can(GitLabUnitPrimitive.AMAZON_Q_INTEGRATION):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized to perform action",
            )

    def _track_completion_request(self) -> None:
        """Track the completion request event."""
        self.context.internal_event_client.track_event(
            f"request_{GitLabUnitPrimitive.AMAZON_Q_INTEGRATION}",
            category=__name__,
        )

    def _initialize_q_client(self) -> None:
        """Initialize Amazon Q client."""
        role_arn = os.environ.get("AWS_ROLE_ARN")
        self.q_client = self.context.amazon_q_client_factory.get_client(
            current_user=self.context.current_user,
            auth_header=self.context.current_user.auth_header,
            role_arn=role_arn,
        )

    def _build_completion_payload(self) -> CodeSuggestionRequest:
        """
        Build the completion request payload.

        Returns:
            dict: Structured payload for Amazon Q API
        """
        payload = self.context.payload.payload
        language = self._get_language_info(payload.file_name)

        return CodeSuggestionRequest(
            fileContext=FileContext(
                leftFileContent=self._get_content_snippet(
                    payload.content_above_cursor, -100
                ),
                rightFileContent=self._get_content_snippet(
                    payload.content_below_cursor, 100
                ),
                filename=payload.file_name,
                programmingLanguage=ProgrammingLanguage(
                    languageName=language.name.lower() if language else ""
                ),
            ),
            maxResults=1,
        )

    async def _get_completion_suggestions(
        self, completion_payload: CodeSuggestionRequest
    ) -> CodeSuggestionResponse:
        """
        Get completion suggestions from Amazon Q API.

        Args:
            completion_payload: The structured payload for the API

        Returns:
            CodeSuggestionResponse: Raw API response with suggestions

        Raises:
            ValueError: If empty response from API
            AWSException: If AWS API call fails after all retries
            ConnectionError: If connection fails after all retries
        """
        logger.debug("Sending event to AmazonQ API: %s", completion_payload)
        # Make API call with retry logic
        max_retries = 3
        retry_delay = 1  # seconds

        for attempt in range(max_retries):
            try:
                response: CodeSuggestionResponse = (
                    self.q_client.send_inline_code_message(
                        completion_payload.model_dump()
                    )
                )
                if not response:
                    raise ValueError("Empty response from Amazon Q API")
                return CodeSuggestionResponse.model_validate(response)
            except (AWSException, ConnectionError) as e:
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(
                        "Failed to get completion after %d attempts: %s",
                        max_retries,
                        str(e),
                    )
                    raise

                logger.warning(
                    "Retry attempt %d/%d failed: %s", attempt + 1, max_retries, str(e)
                )
                await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff

        # This case should not be reached since the last retry will either:
        # 1. Return a valid response
        # 2. Raise an exception
        # But add it for code warning with no return
        raise RuntimeError("Failed to get completion suggestions after all retries")

    def _process_suggestions(
        self, suggestion_resp: CodeSuggestionResponse
    ) -> list[ModelEngineOutput]:
        """
        Process and convert suggestions to ModelEngineOutput format.

        Args:
            suggestion_resp: Raw API response containing suggestions

        Returns:
            list[ModelEngineOutput]: Processed completion suggestions
        """
        payload = self.context.payload.payload
        language = self._get_language_info(payload.file_name)
        output: list[ModelEngineOutput] = []

        for suggestion in suggestion_resp.CodeRecommendations:
            logger.debug("Processing suggestion: %s", suggestion)
            output.append(self._create_model_output(suggestion, language))

        logger.debug("Generated output: %s", output)
        return output

    @staticmethod
    def _get_content_snippet(content: Optional[str], slice_length: int) -> str:
        """
        Get a snippet of content with specified length.

        Args:
            content: The content to slice
            slice_length: Length of the slice (positive or negative)

        Returns:
            str: The sliced content
        """
        if not content:
            return ""
        return content[slice_length:] if slice_length < 0 else content[:slice_length]

    @staticmethod
    def _get_language_info(filename: str) -> Any:
        """
        Get language information from filename.

        Args:
            filename: Name of the file

        Returns:
            Any: Language information
        """
        return lang_from_filename(filename)

    @staticmethod
    def _create_model_output(
        suggestion: CodeRecommendation, language: Any
    ) -> ModelEngineOutput:
        """
        Create a ModelEngineOutput instance from a suggestion.

        Args:
            suggestion: Raw suggestion from API
            language: Language information

        Returns:
            ModelEngineOutput: Structured output
        """
        return ModelEngineOutput(
            text=suggestion.content,
            score=0,
            model=EngineOutputModelMetadata(
                name=ModelProvider.AMAZONQ.value, engine=ModelProvider.AMAZONQ.value
            ),
            metadata=MetadataPromptBuilder(components={}, experiments=[]),
            tokens_consumption_metadata=TokensConsumptionMetadata(
                input_tokens=0, output_tokens=0
            ),
            lang_id=language,
        )
