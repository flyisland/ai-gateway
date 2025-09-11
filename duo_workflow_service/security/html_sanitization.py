# flake8: noqa: W605
import json
import re
from typing import Any, Dict, List, Union

import bleach

from duo_workflow_service.security.markdown_content_security import _apply_recursively


def _sanitize_string(text: str) -> str:
    """Sanitize HTML content using allowlist approach.
    
    Also recursively processes nested JSON strings that may contain HTML.
    """
    if not text or not isinstance(text, str):
        return text

    # Check if this string is itself a JSON string containing more data
    if text.strip().startswith('{') and text.strip().endswith('}'):
        try:
            # This string might be a nested JSON - try to parse and sanitize recursively
            nested_data = json.loads(text)
            sanitized_nested = _apply_recursively(nested_data, _sanitize_string)
            return json.dumps(sanitized_nested)
        except json.JSONDecodeError:
            # Not valid JSON, continue with normal HTML sanitization
            pass

    allowed_tags = [
        "b",
        "i",
        "u",
        "strong",
        "em",
        "br",
        "p",
        "span",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "a",
        "img",
        "code",
        "pre",
        "blockquote",
        "table",
        "tr",
        "td",
        "th",
    ]

    allowed_attributes = {
        "*": ["class", "id"],
        "a": ["href", "title"],
        "img": ["src", "alt", "width", "height"],
        "table": ["border", "cellpadding", "cellspacing"],
    }

    cleaned = bleach.clean(
        text,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True,
        strip_comments=True,
    )

    return cleaned


def sanitize_html_content(
    response: Union[str, Dict[str, Any], List[Any]],
) -> Union[str, List[Union[str, Dict[str, Any]]]]:
    """Sanitize HTML content using allowlist approach.

    Input is always json.dumps() format, so we must parse JSON first to access
    the actual HTML content, then re-serialize to maintain the expected format.

    Args:
        response: JSON string or data structure to sanitize

    Returns:
        Sanitized response with unauthorized HTML tags removed
    """
    if isinstance(response, str):
        try:
            parsed_data = json.loads(response)
            sanitized_data = _apply_recursively(parsed_data, _sanitize_string)
            return json.dumps(sanitized_data)
        except json.JSONDecodeError:
            return _sanitize_string(response)
    else:
        return _apply_recursively(response, _sanitize_string)
