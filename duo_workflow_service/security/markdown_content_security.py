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
    """Strip HTML comments using Bleach for security.

    Uses Mozilla's Bleach library (https://github.com/mozilla/bleach) to safely
    remove HTML comments while preserving all other content.

    Args:
        response: The response data to process

    Returns:
        Response with HTML comments removed using Bleach
    """

    def _strip_comments(text: str) -> str:
        if not text or not isinstance(text, str):
            return text

        return bleach.clean(text, strip_comments=True)

    return _apply_recursively(response, _strip_comments)
