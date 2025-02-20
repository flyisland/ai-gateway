"""
Error handling module for AWS-specific exceptions in Amazon Q integration.
Provides standardized error handling and message formatting for AWS service interactions.
"""

from dataclasses import dataclass
from typing import Dict

from botocore.exceptions import ClientError


@dataclass
class ErrorConfig:
    """
    Configuration class for error details.

    Attributes:
        code (str): The AWS error code identifier
        message (str): Human-readable error message describing the issue
    """

    code: str
    message: str


class AWSErrorHandler:
    """
    Handles AWS-specific errors and provides standardized error messages.
    Maps AWS error codes to user-friendly messages and processes AWS client exceptions.
    """

    # Mapping of AWS error codes to user-friendly error messages
    ERROR_MAPPING: Dict[str, str] = {
        "ExpiredTokenException": "AWS credentials have expired. Please refresh your credentials.",
        "UnrecognizedClientException": "Invalid AWS credentials. Please check your credentials.",
        "AccessDeniedException": "Insufficient permissions to access Amazon Q.",
        "ThrottlingException": "Request was throttled. Please try again later.",
        "RequestTimeoutException": "Request timed out. Please try again.",
    }

    @classmethod
    def handle_client_error(cls, error: ClientError) -> ErrorConfig:
        """
        Processes AWS client errors and creates a standardized error configuration.

        This method extracts error details from AWS ClientError exceptions and maps them
        to user-friendly messages using the ERROR_MAPPING dictionary. If the error code
        is not found in the mapping, a generic error message is generated.

        Args:
            error (ClientError): The AWS client error to process

        Returns:
            ErrorConfig: A configuration object containing the error code and formatted message

        Example:
            try:
                # AWS API call
                pass
            except ClientError as e:
                error_config = AWSErrorHandler.handle_client_error(e)
                print(f"Error {error_config.code}: {error_config.message}")
        """
        # Extract error details from the AWS response
        error_code = error.response["Error"]["Code"]
        error_message = error.response["Error"]["Message"]

        # Get the user-friendly message from the mapping or create a generic one
        error_text = cls.ERROR_MAPPING.get(
            error_code, f"AWS error occurred: {error_message}"
        )

        # Return a standardized error configuration
        return ErrorConfig(error_code, error_text)
