# flake8: noqa: W605
import re
from enum import Enum
from typing import Any


class SecurityException(Exception):
    """Custom exception raised when security validation fails."""


class SecurityFunction(Enum):
    """Available security functions."""

    ENCODE_TAGS = "encode_tags"


class PromptSecurity:
    """Security class with multiple security functions."""

    # Define dangerous tags to encode
    DANGEROUS_TAGS = {
        "goal": "goal",
        "system": "system",
        "s": "system",
    }

    # Define which security functions to apply for each tool
    TOOL_SECURITY_CONFIG = {
        "get_issue": [SecurityFunction.ENCODE_TAGS],
        "get_epic": [SecurityFunction.ENCODE_TAGS],
        "get_issue_note": [SecurityFunction.ENCODE_TAGS],
    }

    @staticmethod
    def apply_security(response: Any, tool_name: str) -> Any:
        """Apply all configured security functions for a specific tool.

        Args:
            response: The response to secure
            tool_name: Name of the tool being used

        Returns:
            Secured response

        Raises:
            SecurityException: If validation fails
        """
        # Get security functions for this tool
        security_functions = PromptSecurity.TOOL_SECURITY_CONFIG.get(tool_name, [])

        secured_response = response
        for func in security_functions:
            result = PromptSecurity._apply_function(secured_response, func)

            # Check if this is a validation result (tuple) or transformed data
            if isinstance(result, tuple) and len(result) == 2:
                is_safe, error_message = result
                if not is_safe:
                    raise SecurityException(
                        f"Security validation failed: {error_message}"
                    )
            else:
                secured_response = result

        return secured_response

    @staticmethod
    def _apply_function(data: Any, function: SecurityFunction) -> Any:
        """Apply a specific security function to data.

        Returns:
            - For transform functions: transformed data
            - For validation functions: (is_safe, error_message) tuple
        """
        function_map = {
            SecurityFunction.ENCODE_TAGS: PromptSecurity._encode_tags_recursive,
        }

        func = function_map.get(function)
        if func:
            return func(data)
        return data

    @staticmethod
    def _encode_tags_recursive(data: Any) -> Any:
        """Recursively encode all dangerous tags."""
        if isinstance(data, str):
            return PromptSecurity._encode_tags(data)

        if isinstance(data, dict):
            return {
                k: PromptSecurity._encode_tags_recursive(v) for k, v in data.items()
            }

        if isinstance(data, list):
            return [PromptSecurity._encode_tags_recursive(item) for item in data]

        return data

    @staticmethod
    def _encode_tags(text: str) -> str:
        """Encode all dangerous tags in text."""
        for tag_name, replacement in PromptSecurity.DANGEROUS_TAGS.items():
            text = re.sub(
                f"<\s*(/?)\s*{tag_name}\s*>",
                f"&lt;\\1{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

        return text
