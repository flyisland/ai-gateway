from unittest.mock import AsyncMock, MagicMock

import pytest

from duo_workflow_service.components.tools_registry import ToolMetadata
from duo_workflow_service.entities.state import Plan, WorkflowState, WorkflowStatusEnum
from duo_workflow_service.executor.client import ExecutorClient
from duo_workflow_service.gitlab.http_client import GitlabHttpClient


@pytest.fixture(scope="function")
def gl_http_client():
    return AsyncMock(spec=GitlabHttpClient)


@pytest.fixture(scope="function")
def tool_metadata(gl_http_client):
    return ToolMetadata(
        executor_client=MagicMock(spec=ExecutorClient),
        gitlab_client=gl_http_client,
        gitlab_host="gitlab.example.com",
    )


@pytest.fixture(scope="function")
def graph_input() -> WorkflowState:
    return WorkflowState(
        status=WorkflowStatusEnum.NOT_STARTED,
        conversation_history={},
        last_human_input=None,
        handover=[],
        ui_chat_log=[],
        plan=Plan(steps=[]),
    )


@pytest.fixture
def graph_config():
    return {"configurable": {"thread_id": "test-workflow"}}
