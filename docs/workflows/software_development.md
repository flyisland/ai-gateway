# Software Development Workflow

## What It Does

Helps you build features, fix bugs, refactor code, and create tests through AI-powered development assistance. Since
it's connected to your GitLab project, it can directly solve issues from your GitLab instance.

## When to Use

- **Feature Development**: Build new functionality from requirements
- **Bug Fixing**: Debug and fix issues across multiple files
- **Code Refactoring**: Improve code structure and quality
- **Test Creation**: Generate comprehensive test suites
- **Documentation**: Create or update code documentation
- **GitLab Issue Resolution**: Directly implement fixes for issues in your GitLab project

## How to Use

1. **Describe your task clearly**

   ```text
   Implement user authentication with JWT tokens, including login/logout endpoints,
   middleware for protected routes, and proper error handling
   ```

2. **Provide context**
   - Tech stack (for example, Node.js, Express, PostgreSQL)
   - Coding standards or patterns to follow
   - Existing code examples if applicable

3. **Review the plan** before execution

4. **Test thoroughly** after completion

## Examples

### Good Request

```text
Add input validation to the user registration endpoint:
- Validate email format
- Ensure password meets security requirements (8+ chars, uppercase, number)
- Check username uniqueness
- Return specific error messages
- Follow our existing validation pattern from auth.validator.js
```

### GitLab Issue Request

```text
Implement the fix for issue #342 - users can't upload files larger than 5MB
```

### Too Vague

```text
Fix the login bug
Make the code better
```

## Capabilities

### Can Do

- Create new files and modules
- Modify existing code
- Implement design patterns
- Write unit/integration tests
- Add error handling and logging
- Performance optimizations
- Read and implement GitLab issues directly
- Access project context and existing code

### Cannot Do

- Access external APIs during execution
- Run or debug code directly
- Handle extremely large files (token limits apply)

## Best Practices

1. **Break down complex tasks** into smaller, focused requests
2. **Include examples** of existing patterns you want followed
3. **Specify test requirements** upfront
4. **Mention constraints** (performance, security, compatibility)

## Tips for Success

- Start with clear requirements
- Provide code style preferences
- Include success criteria
- Review changes carefully
- Run all tests before merging
