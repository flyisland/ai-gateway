# Workflow Email Configuration

## Overview

This document describes the approach for configuring email addresses for git commits in Duo Workflows, addressing issue #1487.

## Problem

The executor currently hardcodes the email address `duo.workflow.agent@gitlab.com` for git commits, which:
- Does not exist as a real email address
- Provides poor user experience
- Makes it difficult to track commits created by the service

## Solution

The solution involves updating three repositories to pass the service account email from the composite identity:

### 1. GitLab Rails Repository Changes

**File: `ee/lib/api/ai/duo_workflows/workflows.rb` (around line 95)**
- Extract the email from the composite identity
- Pass it to the start workflow service

**File: `ee/app/services/ai/duo_workflows/start_workflow_service.rb` (around line 109)**
- Accept the email parameter from the workflows API
- Pass it to the executor via environment variable

### 2. Executor Repository Changes

**File: `main.go` (around line 93)**
- Replace hardcoded email `duo.workflow.agent@gitlab.com` with environment variable
- Use `os.Getenv("WORKFLOW_GIT_AUTHOR_EMAIL")` with fallback to hardcoded value
- Example implementation:
```go
email := os.Getenv("WORKFLOW_GIT_AUTHOR_EMAIL")
if email == "" {
    email = "duo.workflow.agent@gitlab.com" // fallback
}
```

### 3. AI Gateway Repository Changes

Currently, the AI Gateway communicates with the executor via gRPC using the contract protocol. The contract would need to be extended to support passing environment variables or configuration to the executor.

## Environment Variable

- **Name**: `WORKFLOW_GIT_AUTHOR_EMAIL`
- **Purpose**: Set the email address for git commits made by the workflow executor
- **Source**: Service account email from composite identity
- **Fallback**: `duo.workflow.agent@gitlab.com` (for backward compatibility)

## Implementation Steps

1. **Update Executor**: Modify `main.go` to read email from environment variable
2. **Update GitLab Rails**: Extract email from composite identity and pass to executor
3. **Update Contract** (if needed): Extend gRPC contract to support environment variables
4. **Update Tests**: Add test coverage for email handling
5. **Update Documentation**: Document the new environment variable

## Testing

- Verify that commits use the service account email when available
- Verify fallback behavior when environment variable is not set
- Test with different composite identity configurations

## Backward Compatibility

The implementation maintains backward compatibility by:
- Using the hardcoded email as fallback when environment variable is not set
- Not breaking existing workflow functionality
- Allowing gradual rollout of the feature

## Related Issues

- Issue #1487: Email address for git commits in Flows does not exist
- MR !3442: Draft implementation (needs completion)