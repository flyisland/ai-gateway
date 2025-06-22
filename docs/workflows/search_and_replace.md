# Search and Replace Workflow

## What It Does

Intelligently updates code across multiple files using pattern-based rules while maintaining code structure and
functionality.

## Prerequisites

Create configuration file: `.duo_workflow/search_and_replace_config.yaml`

## Configuration Format

```YAML
domain_speciality: "Frontend Development"
assignment_description: "Add accessibility attributes to UI components"
file_types:
  - "*.tsx"
  - "*.jsx"
replacement_rules:
  - element: "button"
    rules: "Add aria-label and ensure keyboard navigation"
  - element: "img"
    rules: "Add descriptive alt text based on context"
```

## Common Use Cases

### Accessibility Compliance

```YAML
domain_speciality: "React Frontend"
assignment_description: "Implement WCAG 2.1 AA standards"
file_types: [ "*.jsx", "*.tsx" ]
replacement_rules:
  - element: "form inputs"
    rules: "Add labels, aria-describedby for errors, and required indicators"
```

### API Migration

```YAML
domain_speciality: "Backend Services"
assignment_description: "Update API from v1 to v2"
file_types: [ "*.js", "*.ts" ]
replacement_rules:
  - element: "API endpoints"
    rules: "Change /api/v1/ to /api/v2/ and update payload structure"
```

### Security Updates

```YAML
domain_speciality: "Full Stack"
assignment_description: "Fix XSS vulnerabilities"
file_types: [ "*.jsx", "*.ejs" ]
replacement_rules:
  - element: "user input rendering"
    rules: "Add proper sanitization before displaying user content"
```

## How to Use

1. **Create config file** with your rules
2. **Test on a few files first** to verify patterns
3. **Review all changes** before committing
4. **Run tests** to ensure functionality

## Best Practices

### Do

- Write specific, actionable rules
- Test patterns on small subsets first
- Use version control
- Be explicit about edge cases

### Don't

- Use vague rules like "fix all issues"
- Run on entire codebase without testing
- Skip the review step

## Troubleshooting

**No files processed?**

- Check file_types patterns match your files
- Verify config file location

**Unexpected changes?**

- Make rules more specific
- Add exclusion patterns
- Review the execution logs

## Limitations

- Cannot execute code to verify changes
- Large files may hit token limits
- Binary files cannot be processed