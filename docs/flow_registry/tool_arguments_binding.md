# Tool Arguments Binding - Security Feature

## Overview

The `tool_arguments_binding` feature provides a security mechanism to prevent prompt injection attacks by restricting the scope in which an agent operates. It works by **overriding tool call arguments** at execution time, ensuring that agents cannot be manipulated into accessing resources outside their prescribed data perimeter.

## Problem Statement

Prompt injection attacks can manipulate AI agents into:
- Accessing unauthorized projects or resources
- Reading files outside designated directories
- Executing commands with unintended parameters
- Bypassing security boundaries through crafted prompts

## Solution

`tool_arguments_binding` enforces security boundaries by **binding specific tool parameters to flow state values**, overriding any arguments the agent attempts to pass. This creates an immutable security perimeter that cannot be bypassed through prompt manipulation.

## Configuration

### Basic Syntax

```yaml
components:
  - name: "secure_agent"
    type: AgentComponent
    prompt_id: "my_prompt"
    prompt_version: "^1.0.0"
    inputs:
      - from: "context:project_id"
        as: "project_id"
    toolset:
      - "get_repository_file"
      - "list_repository_tree"
    tool_arguments_binding:
      - from: "context:project_id"  # Binds to parameter named "project_id"
```

### Field Requirements

- **from**: Source path in flow state (using IOKey syntax) - **Required**
- **as**: Tool parameter name to bind - **Optional**
  - If omitted, uses the last segment of the path as the parameter name
  - `from: "context:project_id"` → binds to parameter `project_id`
  - `from: "context:merge_request.iid"` → binds to parameter `iid`
- The binding applies to **all tools** in the toolset that have a matching parameter

### Syntax Examples

```yaml
# Without alias - parameter name inferred from path
tool_arguments_binding:
  - from: "context:project_id"  # Binds to "project_id"
  - from: "context:merge_request_iid"  # Binds to "merge_request_iid"

# With alias - explicit parameter name
tool_arguments_binding:
  - from: "context:project_id"
    as: "pid"  # Binds to "pid" instead of "project_id"
  - from: "context:current_branch"
    as: "ref"  # Binds to "ref" parameter
```

## How It Works

### Execution Flow

1. **Agent generates tool call** with arguments
2. **Binding layer intercepts** the tool call
3. **Bound values are extracted** from flow state
4. **Agent arguments are overridden** with bound values
5. **Tool executes** with enforced arguments
6. **Tool response** is being wrapped with JIT (just-in-time) instructions informing LLM that tool call arguments has been overrode

### Example Scenario

**Configuration:**
```yaml
tool_arguments_binding:
  - from: "context:project_id"  # No 'as' needed - infers "project_id"
```

**Agent attempts to call:**
```python
get_repository_file(project_id=999, file_path="secret.txt")
```

**Binding enforcement:**
1. Extracts `context.project_id` from state using `template_variable_from_state()` → `{"project_id": 42}`
2. Detects parameter name: `"project_id"` (from last segment of path)
3. Compares: agent value `999` ≠ bound value `42`
4. Overrides agent's argument: `project_id=999` → `project_id=42`
5. Logs the security override
6. Tool executes with `project_id=42`
7. LLM receives tool response wrapped in JIT instruction informing it that arguments has been overrode

**Result:** Agent cannot access project 999 even if prompted to do so.

## Use Cases

### 1. Project Scope Restriction

Prevent agents from accessing projects outside their authorization:

```yaml
components:
  - name: "code_reviewer"
    type: AgentComponent
    prompt_id: "code_review"
    prompt_version: "^1.0.0"
    inputs:
      - from: "context:project_id"
        as: "project_id"
      - from: "context:merge_request_iid"
        as: "mr_iid"
    toolset:
      - "get_repository_file"
      - "list_repository_tree"
      - "get_merge_request"
      - "list_merge_request_diffs"
    tool_arguments_binding:
      - from: "context:project_id"
        as: "project_id"
      - from: "context:merge_request_iid"
        as: "merge_request_iid"
```

**Security benefit:** Agent can only review the specific merge request, even if prompted to access others.

### 2. File System Boundary Enforcement

Restrict file operations to specific directories:

```yaml
components:
  - name: "file_processor"
    type: AgentComponent
    prompt_id: "process_files"
    prompt_version: "^1.0.0"
    inputs:
      - from: "context:allowed_directory"
        as: "base_path"
    toolset:
      - "read_file"
      - "list_dir"
      - "find_files"
    tool_arguments_binding:
      - from: "context:allowed_directory"
        as: "search_directory"  # For find_files, grep tools
```

### 3. Multi-Project Code Review

Lock each agent to analyze only their assigned project:

```yaml
components:
  - name: "prescan_codebase"
    type: AgentComponent
    prompt_id: "code_review_prescan"
    prompt_version: "^1.0.0"
    inputs:
      - from: "context:project_id"
        as: "project_id"
      - from: "context:goal"
        as: "merge_request_iid"
    toolset:
      - "build_review_merge_request_context"
      - "list_repository_tree"
      - "get_repository_file"
      - "read_file"
      - "find_files"
      - "blob_search"
    tool_arguments_binding:
      - from: "context:project_id"
        as: "project_id"
    ui_log_events:
      - "on_tool_execution_success"
      - "on_tool_execution_failed"
      - "on_agent_final_answer"
```

### 4. Branch Protection

Ensure agents only work on designated branches:

```yaml
components:
  - name: "branch_worker"
    type: AgentComponent
    prompt_id: "branch_operations"
    prompt_version: "^1.0.0"
    inputs:
      - from: "context:working_branch"
        as: "branch_name"
      - from: "context:project_id"
        as: "project_id"
    toolset:
      - "get_repository_file"
      - "list_repository_tree"
    tool_arguments_binding:
      - from: "context:project_id"
        as: "project_id"
      - from: "context:working_branch"
        as: "ref"  # Binds branch reference
```

## Security Guarantees

### What's Protected

✅ **Parameter values** - Bound parameters cannot be changed by agent  
✅ **Cross-tool enforcement** - Bindings apply to all tools with matching parameters  
✅ **Runtime enforcement** - Overrides happen at execution time, not configuration time  
✅ **Audit logging** - All overrides are logged for security monitoring

### What's NOT Protected

❌ **Non-bound parameters** - Agent controls unbound parameters  
❌ **Tool selection** - Agent can still choose which tools to call  
❌ **Tool call frequency** - Agent controls how often tools are called  
❌ **Literal values** - Cannot bind to literal strings (must come from state)
