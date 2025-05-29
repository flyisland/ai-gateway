from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contract import contract_pb2
from duo_workflow_service.executor.client import ExecutorClient
from duo_workflow_service.internal_events import InternalEventAdditionalProperties
from duo_workflow_service.internal_events.event_enum import CategoryEnum, EventEnum
from duo_workflow_service.workflows.abstract_workflow import (
    AbstractWorkflow,
    TraceableException,
)


# Concrete implementation for testing
class MockGraph:
    async def astream(self, input, config, stream_mode):
        yield "updates", {"step1": {"key": "value"}}


class MockWorkflow(AbstractWorkflow):
    def _compile(self, goal, tools_registry, checkpointer):
        return MockGraph()

    def get_workflow_state(self, goal):
        return {"goal": goal, "state": "initial"}

    async def _handle_workflow_failure(self, error, compiled_graph, graph_config):
        print(error)

    def log_workflow_elements(self, element):
        print(element)


@pytest.fixture
def workflow():
    workflow_id = "test-workflow-id"
    metadata = {
        "extended_logging": True,
        "git_url": "https://example.com",
        "git_sha": "abc123",
    }
    workflow_type = CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT
    context_elements = []
    return MockWorkflow(workflow_id, metadata, workflow_type, context_elements)


@pytest.fixture
def mock_project():
    return {
        "id": MagicMock(),
        "description": MagicMock(),
        "name": MagicMock(),
        "http_url_to_repo": MagicMock(),
        "web_url": "https://example.com/project",
    }


@pytest.mark.asyncio
async def test_init():
    # Test initialization
    workflow_id = "test-workflow-id"
    metadata = {"key": "value"}
    context_elements = [{"type": 1, "name": "test", "contents": "test content"}]
    mcp_tools = [
        contract_pb2.McpTool(name="get_issue", description="Tool to get issue")
    ]
    workflow = MockWorkflow(
        workflow_id,
        metadata,
        CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
        context_elements,
        {},
        mcp_tools,
    )

    assert workflow._workflow_id == workflow_id
    assert workflow._workflow_metadata == metadata
    assert workflow._context_elements == context_elements
    assert len(workflow._additional_tools) == 1
    tool = workflow._additional_tools[0]
    assert tool.name == "get_issue"
    assert tool.description == "Tool to get issue"
    assert workflow.is_done is False
    assert isinstance(workflow._executor_client, ExecutorClient)


@pytest.mark.asyncio
@patch("duo_workflow_service.workflows.abstract_workflow.fetch_workflow_config")
@patch(
    "duo_workflow_service.workflows.abstract_workflow.fetch_project_data_with_workflow_id"
)
@patch("duo_workflow_service.workflows.abstract_workflow.GitLabWorkflow")
@patch("duo_workflow_service.workflows.abstract_workflow.ToolsRegistry.configure")
async def test_compile_and_run_graph(
    mock_tools_registry,
    mock_gitlab_workflow,
    mock_fetch_project,
    mock_workflow_config,
    workflow,
    mock_project,
):
    # Setup mocks
    mock_tools_registry.return_value = MagicMock()
    mock_checkpointer = AsyncMock()
    mock_checkpointer.aget_tuple = AsyncMock(return_value=None)
    mock_checkpointer.initial_status_event = "START"
    mock_gitlab_workflow.return_value.__aenter__.return_value = mock_checkpointer
    mock_fetch_project.return_value = mock_project

    # Run the method
    await workflow._compile_and_run_graph("Test goal")

    # Assertions
    assert workflow.is_done
    mock_tools_registry.assert_called_once()
    mock_fetch_project.assert_called_once()
    mock_workflow_config.assert_called_once()


@pytest.mark.asyncio
@patch("duo_workflow_service.workflows.abstract_workflow.log_exception")
async def test_cleanup(mock_log_exception, workflow):
    # Run cleanup
    await workflow.cleanup(workflow._workflow_id)

    # Check queues are empty
    assert workflow.is_done is True
    mock_log_exception.assert_not_called()


@patch(
    "duo_workflow_service.workflows.abstract_workflow.DuoWorkflowInternalEvent.track_event"
)
def test_track_internal_event(mock_track_event, workflow):
    # Test tracking an internal event
    event_name = EventEnum.WORKFLOW_START
    workflow_type = CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT
    additional_properties = InternalEventAdditionalProperties()

    workflow._track_internal_event(
        event_name=event_name,
        additional_properties=additional_properties,
        category=workflow_type,
    )

    mock_track_event.assert_called_once_with(
        event_name=event_name.value,
        additional_properties=additional_properties,
        category=workflow_type,
    )


@pytest.mark.asyncio
@patch("duo_workflow_service.workflows.abstract_workflow.fetch_workflow_config")
@patch(
    "duo_workflow_service.workflows.abstract_workflow.fetch_project_data_with_workflow_id"
)
@patch("duo_workflow_service.workflows.abstract_workflow.GitLabWorkflow")
@patch("duo_workflow_service.workflows.abstract_workflow.ToolsRegistry.configure")
async def test_compile_and_run_graph_with_exception(
    mock_tools_registry,
    mock_gitlab_workflow,
    mock_fetch_project,
    mock_workflow_config,
    workflow,
    mock_project,
):
    # Setup mocks to raise an exception
    mock_tools_registry.side_effect = Exception("Test exception")
    mock_fetch_project.return_value = mock_project
    workflow._executor_client.request = AsyncMock(
        return_value=MagicMock(actionResponse=MagicMock(requestID="", response=""))
    )

    with pytest.raises(TraceableException) as exc_info:
        await workflow._compile_and_run_graph("Test goal")

    mock_tools_registry.assert_called_once()
    mock_fetch_project.assert_called_once()
    mock_workflow_config.assert_called_once()
    assert workflow.is_done
    assert isinstance(exc_info.value.original_exception, Exception)
    assert str(exc_info.value.original_exception) == "Test exception"


@pytest.mark.asyncio
@patch.object(MockWorkflow, "_compile_and_run_graph")
async def test_run_passes_correct_metadata_to_langsmith_extra(
    mock_compile_and_run_graph, workflow
):
    await workflow.run("Test goal")

    call_args = mock_compile_and_run_graph.call_args
    args, kwargs = call_args

    metadata = kwargs["langsmith_extra"]["metadata"]
    assert metadata["git_url"] == "https://example.com"
    assert metadata["git_sha"] == "abc123"
    assert metadata["workflow_type"] == CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT.value
