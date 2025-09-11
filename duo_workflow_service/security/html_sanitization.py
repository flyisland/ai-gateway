# flake8: noqa: W605
import re
from typing import Any, Dict, List, Union

import bleach

from duo_workflow_service.security.markdown_content_security import _apply_recursively


def sanitize_html_content(
    response: Union[str, Dict[str, Any], List[Any]],
) -> Union[str, List[Union[str, Dict[str, Any]]]]:
    """Sanitize HTML content by removing unauthorized tags and attributes.

    Uses an allowlist approach to only permit safe HTML tags and attributes while
    preserving markdown code blocks. This prevents HTML injection attacks while
    maintaining legitimate content formatting.

    Args:
        response: The response data to process

    Returns:
        Response with unauthorized HTML tags removed, compatible with ToolMessage.content
    """

    def _strip_tags(text: str) -> str:
        if not text or not isinstance(text, str):
            return text

        # Preserve markdown code blocks by temporarily replacing them
        code_blocks = []
        placeholder_pattern = "___CODE_BLOCK_PLACEHOLDER_{}___ "

        # Match markdown code blocks (```...```)
        def code_block_replacer(match):
            code_blocks.append(match.group(0))
            return placeholder_pattern.format(len(code_blocks) - 1)

        # Temporarily replace code blocks
        text_with_placeholders = re.sub(r"```[\s\S]*?```", code_block_replacer, text)

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
            text_with_placeholders,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True,
            strip_comments=True,
        )

        # Restore code blocks
        for i, code_block in enumerate(code_blocks):
            placeholder = placeholder_pattern.format(i)
            cleaned = cleaned.replace(placeholder, code_block)

        return cleaned

    return _apply_recursively(response, _strip_tags)
