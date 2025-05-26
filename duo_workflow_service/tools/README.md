# Duo Workflow Service Tools

This directory contains the LangGraph-compatible tools that power GitLab's AI features.

## 📖 Documentation

For comprehensive documentation about the tools architecture, usage, testing, and integration with GitLab's backend, see:

**[📋 Tools Documentation](../../docs/tools.md)**

## Quick Overview

The tools in this directory are backend services that:
- Power GitLab's AI features (Duo Chat, Code Reviews, etc.)
- Run on GitLab's infrastructure (not in IDEs)
- Make direct calls to GitLab's REST APIs
- Execute automatically when users interact with GitLab's web interface

## Tool Categories

- **Search & Discovery**: `search.py`, `previous_context.py`
- **Repository Management**: `repository_files.py`, `filesystem.py`, `commit.py`
- **Project Management**: `issue.py`, `merge_request.py`, `epic.py`, `pipeline.py`
- **Workflow Orchestration**: `planner.py`, `handover.py`, `request_user_clarification.py`

## Development

```bash
# Setup development environment
poetry install --with test

# Run all tool tests (409 tests)
poetry run pytest tests/duo_workflow_service/tools/ -v

# Run specific tool tests
poetry run pytest tests/duo_workflow_service/tools/test_repository_files.py -v
```

For detailed development instructions, testing strategies, and examples of adding new tools (including security tools), see the [full documentation](../../docs/tools.md).
