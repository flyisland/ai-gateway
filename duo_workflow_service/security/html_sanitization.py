import re
from typing import Any, Dict, List, Union

import bleach


def decode_unicode_escapes(text: str) -> str:
    """Decode JSON Unicode escape sequences at multiple levels.

    Handles single and multi-level encoded sequences like:
    - \\u003c -> <
    - \\\\u003c -> <
    - \\u0026 -> &
    - \\\\u0026lt; -> &lt; -> (sanitized by Bleach)

    This is needed because Bleach doesn't decode JSON Unicode escapes.
    We decode iteratively to handle multiple levels of encoding.
    """
    if not text or not isinstance(text, str):
        return text

    # Decode iteratively to handle multiple levels of encoding
    for _ in range(3):
        prev_text = text
        text = re.sub(r"\\+u003c", "<", text, flags=re.IGNORECASE)
        text = re.sub(r"\\+u003e", ">", text, flags=re.IGNORECASE)
        text = re.sub(r"\\+u0026", "&", text, flags=re.IGNORECASE)

        if text == prev_text:
            break

    return text


def sanitize_html_content(
    response: Union[str, Dict[str, Any], List[Any]],
) -> Union[str, List[Union[str, Dict[str, Any]]]]:
    """Sanitize HTML content using allowlist approach.

    Args:
        response: Response data to sanitize (dict, list, or str)

    Returns:
        Sanitized response with unauthorized HTML tags removed
    """

    def _sanitize_string(text: str) -> str:
        """Sanitize HTML content in a string using Bleach allowlist."""
        if not text or not isinstance(text, str):
            return text

        # Decode JSON Unicode escapes that could be used to bypass sanitization
        decoded_text = decode_unicode_escapes(text)

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

        return bleach.clean(
            decoded_text,
            tags=allowed_tags,
            attributes={},
            strip=True,
            strip_comments=True,
        )

    def _apply_recursively(data: Any) -> Any:
        """Apply sanitization recursively to dict/list structures."""
        if isinstance(data, dict):
            return {k: _apply_recursively(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [_apply_recursively(item) for item in data]
        elif isinstance(data, str):
            return _sanitize_string(data)
        elif isinstance(data, (int, float, bool)) or data is None:
            return data
        else:
            return None

    return _apply_recursively(response)
