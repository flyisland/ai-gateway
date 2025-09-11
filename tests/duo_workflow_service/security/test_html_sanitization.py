from duo_workflow_service.security.exceptions import SecurityException
from duo_workflow_service.security.html_sanitization import sanitize_html_content


class TestHtmlSanitization:
    """Test suite for HTML sanitization module."""

    def test_malformed_attributes_attack_vector(self):
        """Test that malformed attributes are properly stripped."""
        # Primary attack vector: malformed attributes that could render invisibly
        result = sanitize_html_content("<div this is injected>content</div>")
        assert result == "<div>content</div>"

        # Multiple malformed attributes
        result = sanitize_html_content('<p random="value" another>text</p>')
        assert result == "<p>text</p>"

        # Mixed valid and invalid attributes
        result = sanitize_html_content(
            '<div class="valid" onclick="alert(1)" id="test">content</div>'
        )
        assert result == '<div class="valid" id="test">content</div>'

    def test_dangerous_script_attributes(self):
        """Test that dangerous script attributes are stripped."""
        # onclick handler
        result = sanitize_html_content('<span onclick="alert(1)">click me</span>')
        assert result == "<span>click me</span>"

        # onerror handler
        result = sanitize_html_content(
            '<img src="image.jpg" onerror="alert(1)" alt="test">'
        )
        assert result == '<img src="image.jpg" alt="test">'

        # style attribute (potential for CSS injection)
        result = sanitize_html_content(
            '<div style="display:none" hidden>hidden content</div>'
        )
        assert result == "<div>hidden content</div>"

    def test_unauthorized_attributes_stripped(self):
        """Test that unauthorized attributes are stripped."""
        # data-* attributes not in allowlist
        result = sanitize_html_content('<div data-custom="value">custom data</div>')
        assert result == "<div>custom data</div>"

        # target attribute not allowed for links (not in allowlist)
        result = sanitize_html_content(
            '<a href="http://example.com" target="_blank">link</a>'
        )
        assert result == '<a href="http://example.com">link</a>'

        # unknown attributes
        result = sanitize_html_content('<p align="center" bgcolor="red">text</p>')
        assert result == "<p>text</p>"

    def test_authorized_attributes_preserved(self):
        """Test that authorized attributes are preserved."""
        # Global attributes: class, id
        result = sanitize_html_content(
            '<div class="valid" id="also-valid">normal content</div>'
        )
        assert result == '<div class="valid" id="also-valid">normal content</div>'

        # Link attributes: href, title
        result = sanitize_html_content(
            '<a href="http://example.com" title="Example">link</a>'
        )
        assert result == '<a href="http://example.com" title="Example">link</a>'

        # Image attributes: src, alt, width, height
        result = sanitize_html_content(
            '<img src="image.jpg" alt="test" width="100" height="100">'
        )
        assert result == '<img src="image.jpg" alt="test" width="100" height="100">'

        # Table attributes
        result = sanitize_html_content(
            '<table border="1" cellpadding="5"><tr><td>cell</td></tr></table>'
        )
        assert (
            result == '<table border="1" cellpadding="5"><tr><td>cell</td></tr></table>'
        )

    def test_dangerous_tags_stripped(self):
        """Test that dangerous tags are completely removed."""
        # Script tags
        result = sanitize_html_content('<script>alert("xss")</script>')
        assert result == 'alert("xss")'

        # Object/embed tags
        result = sanitize_html_content('<object data="malicious.swf">fallback</object>')
        assert result == "fallback"

        # Form elements
        result = sanitize_html_content('<form><input type="text"></form>')
        assert result == ""

    def test_html_comments_stripped(self):
        """Test that HTML comments are stripped."""
        result = sanitize_html_content(
            "<!-- malicious comment --><p>content</p><!-- another -->"
        )
        assert result == "<p>content</p>"

        # Comments with potential injection
        result = sanitize_html_content(
            "<!--<script>alert(1)</script>--><div>safe</div>"
        )
        assert result == "<div>safe</div>"

    def test_nested_data_structures(self):
        """Test sanitization in nested data structures."""
        # Dictionary input
        data = {
            "content": '<div this is injected onclick="alert(1)">text</div>',
            "nested": {"html": '<span random="attr">content</span>'},
        }
        result = sanitize_html_content(data)
        expected = {
            "content": "<div>text</div>",
            "nested": {"html": "<span>content</span>"},
        }
        assert result == expected

        # List input
        data = ["<div this is injected>item1</div>", '<p onclick="bad()">item2</p>']
        result = sanitize_html_content(data)
        expected = ["<div>item1</div>", "<p>item2</p>"]
        assert result == expected

    def test_empty_and_none_inputs(self):
        """Test handling of empty and None inputs."""
        # None input
        result = sanitize_html_content(None)
        assert result is None

        # Empty string
        result = sanitize_html_content("")
        assert result == ""

    def test_unsupported_types_raise_exception(self):
        """Test that unsupported types raise SecurityException."""
        # Non-string, non-dict, non-list types should raise exception
        try:
            sanitize_html_content(123)
            assert False, "Should have raised SecurityException"
        except SecurityException as e:
            assert "Unsupported type for security processing: int" in str(e)

    def test_markdown_code_blocks_preserved(self):
        """Test that markdown code blocks are preserved and not HTML-encoded."""
        # Mermaid diagram with arrows
        result = sanitize_html_content(
            """```mermaid
flowchart TD
    A --> B
    B --> C
```"""
        )
        assert "A --> B" in result
        assert "A --&gt; B" not in result

        # Code block with HTML-like content
        result = sanitize_html_content(
            """```html
<div onclick="alert(1)">
    <script>dangerous()</script>
</div>
```"""
        )
        assert '<div onclick="alert(1)">' in result
        assert "<script>dangerous()</script>" in result

        # Multiple code blocks
        result = sanitize_html_content(
            """Some text with <script>alert(1)</script>

```javascript
function test() {
    return '<div>safe</div>';
}
```

More text with <span onclick="bad()">dangerous</span>"""
        )

        assert (
            "<script>alert(1)</script>" not in result
        )  # HTML outside code blocks sanitized
        assert '<span onclick="bad()">dangerous</span>' not in result
        assert "return '<div>safe</div>';" in result  # Code block content preserved
        assert "<span>dangerous</span>" in result  # Sanitized HTML outside code blocks

    def test_allowlist_completeness(self):
        """Test that the allowlist covers common HTML formatting needs."""
        # Basic formatting tags
        html_content = """
        <b>bold</b> <i>italic</i> <u>underline</u> <strong>strong</strong> <em>emphasis</em>
        <br><p>paragraph</p> <span>span</span> <div>div</div>
        <h1>header1</h1> <h2>header2</h2> <h3>header3</h3>
        <ul><li>list item</li></ul> <ol><li>ordered item</li></ol>
        <a href="http://example.com" title="Example">link</a>
        <img src="image.jpg" alt="image" width="100" height="100">
        <code>inline code</code> <pre>preformatted</pre>
        <blockquote>quote</blockquote>
        <table border="1"><tr><td>cell</td><th>header</th></tr></table>
        """

        result = sanitize_html_content(html_content)

        # Verify all allowed elements are preserved
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<strong>strong</strong>" in result
        assert "<em>emphasis</em>" in result
        assert "<br>" in result
        assert "<p>paragraph</p>" in result
        assert "<h1>header1</h1>" in result
        assert "<ul><li>list item</li></ul>" in result
        assert 'href="http://example.com"' in result
        assert 'src="image.jpg"' in result
        assert "<code>inline code</code>" in result
        assert "<pre>preformatted</pre>" in result
        assert "<blockquote>quote</blockquote>" in result
        assert "<table" in result and "<tr><td>" in result
