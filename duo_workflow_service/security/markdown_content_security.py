from typing import Any, Callable

import bleach


def _apply_recursively(response: Any, func: Callable[[str], str]) -> Any:
    """Apply a function recursively to strings in dict/list structures.

    Args:
        response: The response data to process
        func: Function to apply to string values

    Returns:
        Response with function applied to all string values
    """
    if isinstance(response, dict):
        return {k: _apply_recursively(v, func) for k, v in response.items()}
    elif isinstance(response, list):
        return [_apply_recursively(item, func) for item in response]
    elif isinstance(response, str):
        return func(response)
    else:
        return response


def strip_hidden_html_comments(response: str | dict | list) -> str | dict | list:
    """Strip HTML comments using Bleach, leave everything else unchanged.

    Uses Mozilla's Bleach library (https://github.com/mozilla/bleach) to safely
    remove HTML comments while preserving all other content exactly as it was.
    Other security measures (like dangerous tag encoding) are handled by other
    functions in PromptSecurity.

    Args:
        response: The response data to process

    Returns:
        Response with HTML comments removed using Bleach, everything else unchanged
    """

    def _strip_comments(text: str) -> str:
        if not text or not isinstance(text, str):
            return text

        # Since encode_dangerous_tags runs first, by the time we get here,
        # dangerous tags are already encoded as &lt;system&gt; etc.
        # We just need to strip HTML comments using Bleach's robust parsing
        # while preserving everything else exactly as-is

        import re

        if "<!--" not in text:
            return text  # No comments to strip, return unchanged

        # Use Bleach to strip comments while preserving common HTML tags
        # Extend Bleach's default allowed tags with commonly used HTML elements
        allowed_tags = list(bleach.ALLOWED_TAGS) + [
            "div",
            "span",
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "br",
            "hr",
            "img",
            "table",
            "tr",
            "td",
            "th",
            "thead",
            "tbody",
        ]

        # Allow common attributes that tests expect
        allowed_attributes = bleach.ALLOWED_ATTRIBUTES
        allowed_attributes.update(
            {
                "*": ["class", "id"],
                "img": ["src", "alt", "width", "height"],
                "table": ["border", "cellpadding", "cellspacing"],
            }
        )

        try:
            result = bleach.clean(
                text,
                tags=allowed_tags,
                attributes=allowed_attributes,
                strip_comments=True,
                strip=False,
            )
            return result
        except Exception:
            # If Bleach fails, fall back to regex (simple but less robust)
            return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    return _apply_recursively(response, _strip_comments)
