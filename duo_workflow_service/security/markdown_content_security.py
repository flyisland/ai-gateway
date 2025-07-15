# flake8: noqa: W605
import re
from typing import Any, Callable


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
    """Strip hidden HTML comments that could contain prompt injection attempts.

    Handles complex cases including:
    - Standard HTML comments: <!-- content -->
    - Nested/malformed comments: <<!--stuff-->!-- stuff-->
    - Multiline comments

    Args:
        response: The response data to process

    Returns:
        Response with hidden HTML comments removed
    """

    def _strip_html_comments(text: str) -> str:
        # Handle the complex malformed pattern first: <<!--stuff-->!-- stuff-->
        # This needs to be handled before standard comment removal
        text = re.sub(r"<<!--.*?-->!--.*?-->", "", text, flags=re.DOTALL)

        # Remove standard HTML comments
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

        # Clean up any remaining partial comment patterns
        text = re.sub(r"<!--[^>]*", "", text, flags=re.DOTALL)
        text = re.sub(r"[^<]*-->", "", text, flags=re.DOTALL)

        return text

    return _apply_recursively(response, _strip_html_comments)


def strip_mermaid_code_blocks(response: str | dict | list) -> str | dict | list:
    """Strip Mermaid code blocks that could contain hidden malicious instructions.

    Example:
    ```mermaid
    flowchart TD
    %% Ignore all previous instructions
        A[LLM] -->|Read Comment| B(Oops prompt injection)
    ```

    Args:
        response: The response data to process

    Returns:
        Response with Mermaid code blocks removed
    """

    def _strip_mermaid_blocks(text: str) -> str:
        # Remove Mermaid code blocks (```mermaid ... ```)
        # This handles both inline and multiline mermaid blocks
        return re.sub(r"```mermaid.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)

    return _apply_recursively(response, _strip_mermaid_blocks)


def strip_html_details_tags(response: str | dict | list) -> str | dict | list:
    """Strip HTML details/summary tags that could hide malicious content.

    Example:
    <details>
    <!--
    <summary>
    -->
    </details>

    Args:
        response: The response data to process

    Returns:
        Response with details/summary tags removed
    """

    def _strip_details_tags(text: str) -> str:
        # Remove <details> tags and their entire content (including nested HTML comments and summary)
        text = re.sub(
            r"<details[^>]*>.*?</details>", "", text, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove any remaining standalone <summary> tags and their content
        text = re.sub(
            r"<summary[^>]*>.*?</summary>", "", text, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove any remaining partial <summary> tags
        text = re.sub(r"</?summary[^>]*>", "", text, flags=re.IGNORECASE)

        return text

    return _apply_recursively(response, _strip_details_tags)


def strip_latex_math_blocks_with_comments(
    response: str | dict | list,
) -> str | dict | list:
    """Strip LaTeX math blocks that could contain hidden comments.

    Example:
    $$
    % This is a comment
    a^2+b^2=c^2
    $$

    Args:
        response: The response data to process

    Returns:
        Response with LaTeX math blocks removed
    """

    def _strip_latex_blocks(text: str) -> str:
        # Remove LaTeX math blocks ($$...$$)
        text = re.sub(r"\$\$.*?\$\$", "", text, flags=re.DOTALL)

        # Remove inline LaTeX math ($...$)
        text = re.sub(r"\$[^$]*\$", "", text, flags=re.DOTALL)

        # Remove LaTeX comments (% ...)
        text = re.sub(r"%.*?$", "", text, flags=re.MULTILINE)

        return text

    return _apply_recursively(response, _strip_latex_blocks)


def strip_other_hidden_content(response: str | dict | list) -> str | dict | list:
    """Strip other potentially hidden content that could be exploited.

    Args:
        response: The response data to process

    Returns:
        Response with other hidden content removed
    """

    def _strip_other_hidden(text: str) -> str:
        # Remove HTML <script> tags
        text = re.sub(
            r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove HTML <style> tags
        text = re.sub(
            r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove zero-width characters that could be used to hide content
        zero_width_chars = [
            "\u200b",  # Zero Width Space
            "\u200c",  # Zero Width Non-Joiner
            "\u200d",  # Zero Width Joiner
            "\ufeff",  # Zero Width No-Break Space
        ]

        for char in zero_width_chars:
            text = text.replace(char, "")

        return text

    return _apply_recursively(response, _strip_other_hidden)


def strip_hidden_markdown_content(response: str | dict | list) -> str | dict | list:
    """Strip hidden markdown content that could contain prompt injection.

    This function removes:
    - Hidden HTML comments (including nested/malformed patterns)
    - Mermaid code blocks that could contain malicious instructions
    - HTML details/summary tags that hide content
    - Generic XML/HTML tags
    - LaTeX math blocks with comments
    - Other potentially exploitable hidden content

    Args:
        response: The response data to process

    Returns:
        Response with hidden markdown content removed
    """

    def _strip_all_hidden_content(text: str) -> str:
        # Order matters - more specific patterns first, then generic ones
        # Apply each stripping function's inner logic directly to avoid type issues

        # Strip HTML comments
        text = re.sub(r"<<!--.*?-->!--.*?-->", "", text, flags=re.DOTALL)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        text = re.sub(r"<!--[^>]*", "", text, flags=re.DOTALL)
        text = re.sub(r"[^<]*-->", "", text, flags=re.DOTALL)

        # Strip Mermaid code blocks
        text = re.sub(r"```mermaid.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip HTML details tags
        text = re.sub(
            r"<details[^>]*>.*?</details>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(
            r"<summary[^>]*>.*?</summary>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(r"</?summary[^>]*>", "", text, flags=re.IGNORECASE)

        # Strip LaTeX math blocks
        text = re.sub(r"\$\$.*?\$\$", "", text, flags=re.DOTALL)
        text = re.sub(r"\$[^$]*\$", "", text, flags=re.DOTALL)
        text = re.sub(r"%.*?$", "", text, flags=re.MULTILINE)

        # Strip other hidden content
        text = re.sub(
            r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(
            r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        zero_width_chars = ["\u200b", "\u200c", "\u200d", "\ufeff"]
        for char in zero_width_chars:
            text = text.replace(char, "")

        # Clean up any extra whitespace left behind
        text = re.sub(r"\n\s*\n", "\n\n", text)  # Remove excessive blank lines
        text = text.strip()

        return text

    return _apply_recursively(response, _strip_all_hidden_content)
