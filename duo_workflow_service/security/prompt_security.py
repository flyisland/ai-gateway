# flake8: noqa: W605
import re
from typing import Any, Callable, Dict, List


class SecurityException(Exception):
    """Custom exception raised when security validation fails."""


def encode_dangerous_tags(response: Any) -> Any:
    """Recursively encode dangerous HTML tags in the response.

    Args:
        response: The response data to encode

    Returns:
        Response with encoded dangerous tags
    """
    # Define dangerous tags to encode
    DANGEROUS_TAGS = {
        "goal": "goal",
        "system": "system",
    }

    def _encode_tags_in_string(text: str) -> str:
        """Encode all dangerous tags in a string."""
        for tag_name, replacement in DANGEROUS_TAGS.items():
            # Pattern 1: Regular HTML tags like <goal> or </goal>
            text = re.sub(
                rf"<\s*(/?)\s*{re.escape(tag_name)}\s*>",
                f"&lt;\\1{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

            # Pattern 2: Unicode-escaped tags like \u003cgoal\u003e
            text = re.sub(
                rf"\\u003c\s*(/?)\s*{re.escape(tag_name)}\s*\\u003e",
                f"&lt;\\1{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

            # Pattern 3: Mixed format with double backslashes
            text = re.sub(
                rf"\\\\u003c\s*(/?)\s*{re.escape(tag_name)}\s*\\\\u003e",
                f"&lt;\\1{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

        return text

    # Recursively process the response
    if isinstance(response, str):
        return _encode_tags_in_string(response)
    elif isinstance(response, dict):
        return {k: encode_dangerous_tags(v) for k, v in response.items()}
    elif isinstance(response, list):
        return [encode_dangerous_tags(item) for item in response]
    else:
        return response


class PromptSecurity:
    """Security class with configurable security functions."""

    # Default security functions to apply to ALL tools
    DEFAULT_SECURITY_FUNCTIONS: List[Callable[[Any], Any]] = [
        encode_dangerous_tags,
    ]

    # Tool-specific additional security functions
    TOOL_SPECIFIC_FUNCTIONS: Dict[str, List[Callable[[Any], Any]]] = {
        # 'file_read': [validate_no_script_tags],
        # Add tools that need EXTRA security functions
    }

    @staticmethod
    def apply_security(response: Any, tool_name: str) -> Any:
        """Apply all configured security functions for a specific tool.

        Each security function should either:
        - Return the (possibly modified) response
        - Raise SecurityException if validation fails

        Args:
            response: The response to secure
            tool_name: Name of the tool being used

        Returns:
            Secured response (same type as input)

        Raises:
            SecurityException: If any security validation fails
        """
        # Get all applicable functions
        all_functions = list(PromptSecurity.DEFAULT_SECURITY_FUNCTIONS)
        if tool_name in PromptSecurity.TOOL_SPECIFIC_FUNCTIONS:
            all_functions.extend(PromptSecurity.TOOL_SPECIFIC_FUNCTIONS[tool_name])

        # Apply each function in sequence
        secured_response = response
        for func in all_functions:
            try:
                secured_response = func(secured_response)

            except SecurityException:
                raise

            except Exception as e:
                # Wrap other exceptions for better error context
                raise SecurityException(
                    f"Security function {func.__name__} failed: {str(e)}"
                ) from e

        return secured_response
