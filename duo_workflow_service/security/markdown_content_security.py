# flake8: noqa: W605
import re
from typing import Any, Callable

from lxml import html
from lxml_html_clean import Cleaner
from markdown import markdown


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

    This bulletproof implementation handles multiple bypass techniques:
    - Whitespace variations (spaces, tabs after backticks)
    - Unicode lookalike characters
    - HTML-style Mermaid blocks
    - Incomplete/malformed blocks
    - Alternative language identifiers
    - Nested patterns and edge cases

    Args:
        response: The response data to process

    Returns:
        Response with Mermaid code blocks removed
    """

    def _strip_mermaid_blocks(text: str) -> str:
        if not text or not isinstance(text, str):
            return text

        import unicodedata

        # Step 1: Normalize Unicode and handle lookalike characters
        text = unicodedata.normalize("NFKC", text)

        # Replace common Unicode lookalikes with standard ASCII
        unicode_mappings = {
            "\u02cb": "`",
            "\u0060": "`",
            "\u00b4": "`",
            "\u2018": "`",
            "\u2019": "`",
            "\u201b": "`",
            "\u2032": "`",
            "\uff40": "`",
            "\u200b": "",
            "\u200c": "",
            "\u200d": "",
            "\ufeff": "",
            "\u2060": "",
        }

        for unicode_char, replacement in unicode_mappings.items():
            text = text.replace(unicode_char, replacement)

        # Step 2: Handle markdown code blocks with extensive variations
        markdown_patterns = [
            # Standard and extended backtick blocks
            r"`{3,}\s*mermaid[a-z0-9\-\.\_]*\s*.*?`{3,}",
            # Incomplete blocks (no closing) - remove to end or next block
            r"`{3,}\s*mermaid[a-z0-9\-\.\_]*\s*(?:(?!`{3,}).)*$",
            r"`{3,}\s*mermaid[a-z0-9\-\.\_]*\s*(?:(?!`{3,}).)*?(?=`{3,})",
            # Alternative quote characters
            r"'{3,}\s*mermaid[a-z0-9\-\.\_]*\s*.*?'{3,}",
            r'"{3,}\s*mermaid[a-z0-9\-\.\_]*\s*.*?"{3,}',
            # Mixed quote patterns
            r"`{2,}'\s*mermaid.*?'`{2,}",
            r"'{2,}`\s*mermaid.*?`'{2,}",
            r'`{2,}"\s*mermaid.*?"`{2,}',
            r'"{2,}`\s*mermaid.*?`"{2,}',
        ]

        for pattern in markdown_patterns:
            text = re.sub(
                pattern, "", text, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE
            )

        # Step 3: Handle HTML-style Mermaid blocks comprehensively
        html_patterns = [
            # Standard HTML tags with mermaid references
            r"<(?:pre|div|code|span|section)[^>]*(?:class|data-language|data-lang|lang)\s*=\s*['\"][^'\"]*mermaid[^'\"]*['\"][^>]*>.*?</(?:pre|div|code|span|section)>",
            r"<script[^>]*type\s*=\s*['\"][^'\"]*mermaid[^'\"]*['\"][^>]*>.*?</script>",
            # Any tag with mermaid in any attribute
            r"<[^>]*mermaid[^>]*>.*?</[^>]+>",
        ]

        for pattern in html_patterns:
            text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

        # Step 4: Handle split/partial mermaid keywords across lines
        # Remove "mer" followed by "maid" across whitespace/newlines
        text = re.sub(
            r"```\s*mer\s*\n\s*maid[a-z0-9\-\.\_]*.*?```",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        text = re.sub(
            r"`{3,}[^`\n]*mer[^`\n]*maid[^`]*",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # Step 5: Clean up remaining artifacts and nested content
        # Remove any remaining backtick blocks that might contain fragments
        text = re.sub(
            r"`{3,}[^`]*mermaid[^`]*`*", "", text, flags=re.IGNORECASE | re.DOTALL
        )
        text = re.sub(r"^\s*[`'\"]{3,}\s*$", "", text, flags=re.MULTILINE)

        # Step 6: Final cleanup
        text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
        text = re.sub(r" {3,}", "  ", text)

        return text.strip()

    return _apply_recursively(response, _strip_mermaid_blocks)


def strip_html_details_tags(response: str | dict | list) -> str | dict | list:
    """Strip HTML details/summary tags that could hide malicious content.

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
    """Strip hidden markdown content.

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
        Response with hidden Markdown content removed
    """

    def _strip_all_hidden_content(text: str) -> str:
        # Order matters - more specific patterns first, then generic ones
        # Apply each stripping function's inner logic directly to avoid type issues

        # Strip Mermaid code blocks FIRST (before HTML comments to avoid conflicts with -->)
        text = re.sub(r"```mermaid.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip HTML comments - handle malformed patterns first
        # Handle complex malformed patterns: <<!--stuff-->!-- stuff-->
        text = re.sub(r"<<!--.*?-->!--.*?-->", "", text, flags=re.DOTALL)
        # Handle malformed <!--> patterns FIRST (replace with single space)
        text = re.sub(r"<!-->", " ", text, flags=re.DOTALL)
        # Handle malformed comments like <!-- > patterns (remove to end of line)
        text = re.sub(r"<!--\s*>.*?(?=\n|$)", "", text, flags=re.DOTALL)
        # Handle standard HTML comments
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        # Handle incomplete opening comments (<!-- without closing) - but not <!--> which is already handled
        text = re.sub(r"<!--(?!>)(?!.*-->).*", "", text, flags=re.DOTALL)
        # Clean up orphaned closing tags
        text = re.sub(r"^\s*-->.*?$", "", text, flags=re.MULTILINE)

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
        text = re.sub(r" {3,}", "  ", text)  # Replace 3+ spaces with 2 spaces
        text = text.strip()

        return text

    return _apply_recursively(response, _strip_all_hidden_content)


def get_user_visible_text(content: str) -> str:
    """Convert markdown/HTML to the text representation that users actually see. This is much more robust than regex-
    based stripping.

    Args:
        content: Markdown or HTML content to process

    Returns:
        User-visible text content with hidden elements removed
    """
    if not content or not isinstance(content, str):
        return content

    try:
        # Step 1: Comprehensive HTML comment removal
        # Handle complex malformed patterns first: <<!--stuff-->!-- stuff-->
        content_no_comments = re.sub(
            r"<<!--.*?-->!--.*?-->", "", content, flags=re.DOTALL
        )

        # Handle standard HTML comments
        content_no_comments = re.sub(
            r"<!--.*?-->", "", content_no_comments, flags=re.DOTALL
        )

        # Handle malformed comments like <!-- > or <!-- without proper closing
        # Remove from <!-- to end of line if no closing -->
        content_no_comments = re.sub(
            r"<!--(?!.*-->).*?(?=\n|$)", "", content_no_comments, flags=re.DOTALL
        )

        # Clean up any remaining orphaned --> patterns (but preserve regular text with -->)
        # Only remove --> that appears to be orphaned (at start of line or after whitespace)
        content_no_comments = re.sub(
            r"^\s*-->", "", content_no_comments, flags=re.MULTILINE
        )

        # Step 2: Convert Markdown to HTML
        html_content = markdown(
            content_no_comments,
            extensions=["fenced_code", "tables", "codehilite", "toc"],
        )

        # Step 3: Parse HTML properly
        # Wrap in a div to ensure we have a single root element
        try:
            doc = html.fromstring(f"<div>{html_content}</div>")
        except Exception:
            # If HTML parsing fails, fall back to regex approach
            result = strip_hidden_markdown_content(content)
            return result if isinstance(result, str) else content

        # Step 4: Use lxml.html.clean.Cleaner for proper sanitization
        cleaner = Cleaner(
            scripts=True,  # Remove <script> tags
            javascript=True,  # Remove javascript: URLs and onclick attributes
            comments=True,  # Remove HTML comments
            style=True,  # Remove <style> tags
            links=False,  # Keep links but sanitize them
            meta=True,  # Remove <meta> tags
            page_structure=False,  # Keep basic structure (div, p, etc.)
            processing_instructions=True,  # Remove <?xml ... ?>
            embedded=True,  # Remove <embed>, <object>, etc.
            frames=True,  # Remove <frame>, <iframe>
            forms=True,  # Remove forms as well
            annoying_tags=True,  # Remove <blink>, <marquee>, etc.
            remove_unknown_tags=False,
            safe_attrs_only=True,
            safe_attrs=frozenset(
                ["href", "src", "alt", "title", "class", "id", "name"]
            ),
        )

        # Step 5: Clean the HTML
        cleaned_doc = cleaner.clean_html(doc)

        # Step 6: Extract text content (what user actually sees)
        text_content = cleaned_doc.text_content()

        # Step 7: Clean up whitespace while preserving structure
        # Replace multiple whitespace with single space, but preserve line breaks
        text_content = re.sub(
            r"[ \t]+", " ", text_content
        )  # Multiple spaces/tabs -> single space
        text_content = re.sub(
            r"\n\s*\n\s*\n+", "\n\n", text_content
        )  # Multiple newlines -> double newline
        text_content = text_content.strip()

        return text_content

    except Exception:
        # Fallback: return regex-based processing if parsing fails
        result = strip_hidden_markdown_content(content)
        return result if isinstance(result, str) else content


def strip_hidden_markdown_content_robust(
    response: str | dict | list,
) -> str | dict | list:
    """Extract only the user-visible text content from markdown/HTML.

    This eliminates hidden content while preserving legitimate information that
    the user would actually see when the Markdown is rendered.

    Uses proper HTML/Markdown parsing with fallback to regex approach on errors.

    Args:
        response: The response data to process (string, dict, or list)

    Returns:
        Response with only user-visible content preserved
    """
    return _apply_recursively(response, get_user_visible_text)
