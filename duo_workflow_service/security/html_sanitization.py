from typing import Any, Dict, List, Union

import bleach


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

        decoded_text = text.replace("\\u003c", "<").replace("\\u003e", ">")
        decoded_text = decoded_text.replace("\\u003C", "<").replace("\\u003E", ">")

        if "<" not in decoded_text and "&lt;" not in decoded_text:
            return text

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

        return bleach.clean(
            decoded_text,
            tags=allowed_tags,
            attributes=allowed_attributes,
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
