# flake8: noqa: W605
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Union

from duo_workflow_service.security.exceptions import SecurityException
from duo_workflow_service.security.markdown_content_security import (
    strip_hidden_html_comments,
)


def run_from_args():
    args = sys.argv[1:]
    filename = args[0]
    content = Path(filename).read_text()

    return PromptSecurity.apply_security_to_tool_response(content, "test-tool")


def encode_dangerous_tags(response: Union[str, Dict[str, Any], List[Any]]) -> Union[str, List[Union[str, Dict[str, Any]]]]:
    """Recursively encode dangerous HTML tags in the response.

    Args:
        response: The response data to encode

    Returns:
        Response with encoded dangerous tags
    """
    # Define dangerous tags to encode
    # These tags are commonly used in prompt injection attacks to manipulate LLM behavior:
    # - "goal": Used to override or redirect the primary task objective
    # - "system": Used to inject system-level instructions or override system prompts
    DANGEROUS_TAGS = {
        "goal": "goal",
        "system": "system",
    }

    if isinstance(response, dict):
        result = {k: encode_dangerous_tags(v) for k, v in response.items()}
        return [result]  # Convert dict to list for ToolMessage compatibility
    elif isinstance(response, list):
        return [encode_dangerous_tags(item) for item in response]

    # Process string responses
    for tag_name, replacement in DANGEROUS_TAGS.items():
        # Pattern 1: Regular HTML tags like <goal> or </goal>
        response = re.sub(
            rf"<\s*(/?)\s*{re.escape(tag_name)}\s*>",
            f"&lt;\\1{replacement}&gt;",
            response,
            flags=re.IGNORECASE,
        )

        # Pattern 2: Unicode-escaped tags like \u003cgoal\u003e
        response = re.sub(
            rf"\\u003c\s*(/?)\s*{re.escape(tag_name)}\s*\\u003e",
            f"&lt;\\1{replacement}&gt;",
            response,
            flags=re.IGNORECASE,
        )

        # Pattern 3: Mixed format with double backslashes
        response = re.sub(
            rf"\\\\u003c\s*(/?)\s*{re.escape(tag_name)}\s*\\\\u003e",
            f"&lt;\\1{replacement}&gt;",
            response,
            flags=re.IGNORECASE,
        )

    return response


class PromptSecurity:
    """Security class with configurable security functions."""

    # Default security functions to apply to ALL tools
    DEFAULT_SECURITY_FUNCTIONS: List[
        Callable[
            [Union[str, Dict[str, Any], List[Any]]],
            Union[str, List[Union[str, Dict[str, Any]]]],
        ]
    ] = [
        encode_dangerous_tags,
        strip_hidden_html_comments,
    ]

    # Tool-specific additional security functions
    TOOL_SPECIFIC_FUNCTIONS: Dict[
        str,
        List[
            Callable[
                [Union[str, Dict[str, Any], List[Any]]],
                Union[str, List[Union[str, Dict[str, Any]]]],
            ]
        ],
    ] = {
        # Example: 'file_read': [validate_no_script_tags],
        # Add tools that need EXTRA security functions beyond the defaults
    }

    @staticmethod
    def apply_security_to_tool_response(
        response: Union[str, Dict[str, Any], List[Any]], tool_name: str
    ) -> Union[str, List[Union[str, Dict[str, Any]]]]:
        """Apply all configured security functions for a specific tool.

        Each security function should either:
        - Return the (possibly modified) response
        - Raise SecurityException if validation fails

        Args:
            response: The response to secure (compatible with LangChain ToolCall/ToolMessage)
            tool_name: Name of the tool being used

        Returns:
            Secured response compatible with ToolMessage.content (str | list[str | dict])

        Raises:
            SecurityException: If any security validation fails
        """
        all_functions = list(PromptSecurity.DEFAULT_SECURITY_FUNCTIONS)
        if tool_name in PromptSecurity.TOOL_SPECIFIC_FUNCTIONS:
            all_functions.extend(PromptSecurity.TOOL_SPECIFIC_FUNCTIONS[tool_name])

        secured_response = response
        for func in all_functions:
            try:
                secured_response = func(secured_response)

            except SecurityException:
                raise

            except Exception as e:
                raise SecurityException(
                    f"Security function {func.__name__} failed for tool '{tool_name}': {str(e)}"
                ) from e

        # Type assertion: security functions guarantee proper return type
        return secured_response  # type: ignore[return-value]
