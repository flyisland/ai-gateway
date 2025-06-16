import re
from enum import Enum
from typing import Any


class SecurityException(Exception):
    """Custom exception raised when security validation fails."""

    pass


class SecurityFunction(Enum):
    """Available security functions."""

    ENCODE_TAGS = "encode_tags"
    STRIP_TOOL_CALLS = "strip_tool_calls"
    DETECT_CONTRADICTIONS = "detect_contradictions"
    MONITOR_DIVERGENCE = "monitor_divergence"


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
        "get_issue": [SecurityFunction.ENCODE_TAGS, SecurityFunction.STRIP_TOOL_CALLS],
        "get_epic": [SecurityFunction.ENCODE_TAGS, SecurityFunction.STRIP_TOOL_CALLS],
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
        elif isinstance(data, dict):
            return {
                k: PromptSecurity._encode_tags_recursive(v) for k, v in data.items()
            }
        elif isinstance(data, list):
            return [PromptSecurity._encode_tags_recursive(item) for item in data]
        return data

    @staticmethod
    def _encode_tags(text: str) -> str:
        """Encode all dangerous tags in text."""
        # Process each dangerous tag
        for tag, replacement in PromptSecurity.DANGEROUS_TAGS.items():
            # Handle exact tag
            text = text.replace(f"<{tag}>", f"&lt;{replacement}&gt;")
            text = text.replace(f"</{tag}>", f"&lt;/{replacement}&gt;")

            # Handle case variations and spaces
            # Create pattern for case-insensitive matching with optional spaces
            tag_pattern = "".join(f"[{c.upper()}{c.lower()}]" for c in tag)

            # Opening tag with optional spaces
            text = re.sub(
                f"<(\\s*{tag_pattern}\\s*)>",
                lambda m: f"&lt;{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

            # Closing tag with optional spaces
            text = re.sub(
                f"</(\\s*{tag_pattern}\\s*)>",
                lambda m: f"&lt;/{replacement}&gt;",
                text,
                flags=re.IGNORECASE,
            )

        return text
