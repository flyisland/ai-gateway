# Tool Security Override Guide

## Overview

By default, all tools apply a standard set of security functions to their responses. However, some tools may require custom security configurations based on their risk profile and data sources.

**⚠️ Important: All security function overrides require AppSec team approval before merging.**

## When to Use Overrides

Use `TOOL_SECURITY_OVERRIDES` when:
- Your tool processes trusted, controlled data sources
- Default security is too restrictive for your use case
- You need a specific combination of security functions

**Do NOT use overrides for:**
- Tools handling user-generated content (issues, comments, MRs)
- Tools processing untrusted external data
- When in doubt - default security is appropriate

## How to Configure

### Step 1: Import Required Components

```python
from duo_workflow_service.security.prompt_security import (
    PromptSecurity,
    encode_dangerous_tags,  # Import specific functions as needed
)
```

### Step 2: Set Override During Initialization

Add your override configuration where tools are initialized (e.g., tool registration, app startup):

```python
# Example: Minimal security for read-only file tools
PromptSecurity.TOOL_SECURITY_OVERRIDES['read_file'] = [
    encode_dangerous_tags,
]

# Example: No security for internal code analysis tools
PromptSecurity.TOOL_SECURITY_OVERRIDES['lint_code'] = []
```

### Step 3: Document Your Decision

Always add a comment explaining why the override is needed:

```python
# read_file accesses only our controlled repository content.
# Standard security is too restrictive and modifies legitimate file content.
# We apply minimal security to preserve file integrity.
PromptSecurity.TOOL_SECURITY_OVERRIDES['read_file'] = [
    encode_dangerous_tags,
]
```

## Available Security Functions

You can import and use these functions in your override:

```python
from duo_workflow_service.security.prompt_security import (
    encode_dangerous_tags,
    strip_hidden_unicode_tags,
)
from duo_workflow_service.security.markdown_content_security import (
    strip_hidden_html_comments,
    strip_mermaid_comments,
)
```

## Configuration Patterns

### Pattern 1: Reduced Security (Subset of Functions)

For tools with controlled data sources:

```python
PromptSecurity.TOOL_SECURITY_OVERRIDES['my_tool'] = [
    encode_dangerous_tags,
    strip_hidden_unicode_tags,
]
```

### Pattern 2: No Security (Empty List)

For fully trusted internal tools:

```python
PromptSecurity.TOOL_SECURITY_OVERRIDES['internal_tool'] = []
```

### Pattern 3: Default Security (No Override)

For tools with user content, simply don't add an override:

```python
# No override needed - 'get_issue' automatically gets default security
# This is the safest option when unsure
```

## Testing Your Configuration

After adding an override, verify it works as expected:

```python
result = PromptSecurity.apply_security_to_tool_response(
    "test input",
    "my_tool"
)
print(result)
```

Run the test suite to ensure no regressions:

```bash
poetry run pytest tests/duo_workflow_service/security/ -v
```

## Risk Assessment Checklist

Before adding an override, verify:

- [ ] Tool does NOT process user-generated content
- [ ] Data source is controlled/trusted
- [ ] Override is necessary (default security causes issues)
- [ ] You've documented the reason for the override
- [ ] You've tested with sample data
- [ ] **AppSec approval obtained** (required for all security overrides)

## Examples

### Example 1: File Reading Tool

```python
# read_file reads from our git repository only
PromptSecurity.TOOL_SECURITY_OVERRIDES['read_file'] = [
    encode_dangerous_tags,
]
```

### Example 2: Code Analysis Tool

```python
# Static analysis tool - needs exact code content
PromptSecurity.TOOL_SECURITY_OVERRIDES['analyze_code'] = []
```

### Example 3: High-Risk Tool (No Override)

```python
# get_issue fetches user content - use default security
# NO override configured - defaults apply automatically ✓
```

## Important Notes

1. **Configure Early**: Set overrides during application initialization, before tools are used
2. **Tool Name Match**: Use exact tool name string (case-sensitive)
3. **Empty List Valid**: `[]` means no security functions
4. **Order Matters**: Functions execute in the order listed

## Need Help?

- Review existing overrides in the codebase for examples
- Check test cases: `tests/duo_workflow_service/tools/test_prompt_security.py`
- Contact the AppSec team for approval and guidance on security overrides

## Future: Phase 2 - Flow-Level Security

This guide covers Phase 1 (tool-level overrides). Phase 2 will introduce flow-level security policies where the same tool can have different security based on the flow context. Your tool-level overrides will integrate seamlessly with future flow-level policies.
