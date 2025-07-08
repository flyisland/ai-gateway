# flake8: noqa: W605
import re
from enum import Enum
from typing import Any, Callable, Dict


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
        # Removed "s" mapping to prevent false positives with legitimate HTML
    }

    # Default security functions to apply to ALL tools
    DEFAULT_SECURITY_FUNCTIONS = [SecurityFunction.ENCODE_TAGS]

    # Tool-specific additional validators (on top of default functions)
    TOOL_SPECIFIC_VALIDATORS: Dict[str, Callable] = {
        # 'file_read': '_additional_file_read_validation',
        # Add tools that need EXTRA validation beyond the default
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
        # Apply ALL default security functions
        secured_response = response
        for func in PromptSecurity.DEFAULT_SECURITY_FUNCTIONS:
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

        # Apply tool-specific additional validation if defined
        if tool_name in PromptSecurity.TOOL_SPECIFIC_VALIDATORS:
            validator_func = PromptSecurity.TOOL_SPECIFIC_VALIDATORS[tool_name]
            if callable(validator_func):
                secured_response = validator_func(secured_response)
            elif isinstance(validator_func, str) and hasattr(
                PromptSecurity, validator_func
            ):
                # If it's a string, try to get the method
                method = getattr(PromptSecurity, validator_func)
                secured_response = method(secured_response)

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
            # Pattern 1: Regular HTML tags like <goal> or </goal>
            text = re.sub(
                f"<\s*(/?)\s*{tag_name}\s*>",
                f"&lt;\\1{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

            # Pattern 2: Unicode-escaped tags like \u003cgoal\u003e or \u003c/goal\u003e
            text = re.sub(
                f"\\\\u003c\s*(/?)\s*{tag_name}\s*\\\\u003e",
                f"&lt;\\1{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

            # Pattern 3: Mixed format like \\u003cgoal\\u003e (with double backslashes)
            text = re.sub(
                f"\\\\\\\\u003c\s*(/?)\s*{tag_name}\s*\\\\\\\\u003e",
                f"&lt;\\1{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

        return text
