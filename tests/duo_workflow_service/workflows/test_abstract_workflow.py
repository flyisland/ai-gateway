import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contract import contract_pb2
from duo_workflow_service.components import ToolsRegistry
from duo_workflow_service.internal_events import InternalEventAdditionalProperties
from duo_workflow_service.internal_events.event_enum import CategoryEnum, EventEnum
from duo_workflow_service.workflows.abstract_workflow import (
    AbstractWorkflow,
    TraceableException,
)
from duo_workflow_service.workflows.chat import Workflow


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

    def _get_chat_model_name(self) -> str:
        """Use the default implementation from AbstractWorkflow."""
        return super()._get_chat_model_name()


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
    assert workflow.is_done is False
    assert workflow._outbox.maxsize == 1
    assert workflow._inbox.maxsize == 1
    assert len(workflow._additional_tools) == 1
    tool = workflow._additional_tools[0]
    assert tool.name == "get_issue"
    assert tool.description == "Tool to get issue"


@pytest.mark.asyncio
async def test_outbox_empty(workflow):
    await workflow._outbox.put("test_item")
    assert not workflow.outbox_empty()

    item = await workflow.get_from_outbox()

    assert item == "test_item"
    assert workflow.outbox_empty()


@pytest.mark.asyncio
async def test_get_from_outbox(workflow):
    # Put an item in the outbox
    await workflow._outbox.put("test_item")

    # Get the item
    item = await workflow.get_from_outbox()

    assert item == "test_item"
    assert workflow._outbox.empty()


@pytest.mark.asyncio
async def test_get_from_streaming_outbox(workflow):
    await workflow._streaming_outbox.put("test_item")

    item = workflow.get_from_streaming_outbox()

    assert item == "test_item"
    assert workflow._streaming_outbox.empty()


@pytest.mark.asyncio
async def test_add_to_inbox(workflow):
    # Create a mock event
    mock_event = MagicMock()

    # Add to inbox
    workflow.add_to_inbox(mock_event)

    # Check if it was added
    assert workflow._inbox.qsize() == 1
    assert await workflow._inbox.get() == mock_event


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
    assert workflow.is_done is True


@pytest.mark.asyncio
@patch("duo_workflow_service.workflows.abstract_workflow.log_exception")
async def test_cleanup(mock_log_exception, workflow):
    # Add items to queues
    await workflow._outbox.put("outbox_item")
    await workflow._inbox.put("inbox_item")

    # Run cleanup
    await workflow.cleanup(workflow._workflow_id)

    # Check queues are empty
    assert workflow._outbox.empty()
    assert workflow._inbox.empty()
    assert workflow.is_done is True
    mock_log_exception.assert_not_called()


@pytest.mark.asyncio
@patch("duo_workflow_service.workflows.abstract_workflow.log_exception")
async def test_cleanup_with_exception(mock_log_exception, workflow):
    await workflow._outbox.put("test_item")
    # Make drain_queue raise an exception
    with patch.object(
        workflow._outbox, "get_nowait", side_effect=RuntimeError("Test error")
    ):
        # Catch exception raised during cleanup
        try:
            await workflow.cleanup(workflow._workflow_id)
        except RuntimeError:
            pass

    # Two log_exception calls: one from _drain_queue and one from cleanup
    assert mock_log_exception.call_count == 2

    # Check the first call (from _drain_queue)
    first_call = mock_log_exception.call_args_list[0]
    args, kwargs = first_call
    assert isinstance(args[0], RuntimeError)
    assert str(args[0]) == "Test error"
    assert kwargs["extra"]["workflow_id"] == workflow._workflow_id
    assert kwargs["extra"]["context"] == "Error draining outbox queue"

    # Check the second call (from cleanup)
    second_call = mock_log_exception.call_args_list[1]
    args, kwargs = second_call
    assert isinstance(args[0], RuntimeError)
    assert kwargs["extra"]["workflow_id"] == workflow._workflow_id
    assert kwargs["extra"]["context"] == "Workflow cleanup failed"


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
    workflow._inbox.get = AsyncMock(
        return_value=MagicMock(actionResponse=MagicMock(requestID="", response=""))
    )
    workflow._inbox.task_done = AsyncMock()

    with pytest.raises(TraceableException) as exc_info:
        await workflow._compile_and_run_graph("Test goal")

    assert workflow.is_done is True
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


@pytest.mark.asyncio
@patch.dict(os.environ, {"DUO_WORKFLOW__VERTEX_PROJECT_ID": ""})
@patch("duo_workflow_service.workflows.abstract_workflow.ToolsRegistry", autospec=True)
@patch(
    "duo_workflow_service.workflows.abstract_workflow.fetch_project_data_with_workflow_id"
)
@patch("duo_workflow_service.workflows.abstract_workflow.fetch_workflow_config")
@patch("duo_workflow_service.workflows.convert_to_gitlab_ci.workflow.create_chat_model")
@patch("duo_workflow_service.workflows.abstract_workflow.GitLabWorkflow", autospec=True)
@patch("duo_workflow_service.workflows.abstract_workflow.UserInterface", autospec=True)
async def test_workflow_creates_chat_model_without_vertex(
    mock_checkpoint_notifier,
    mock_gitlab_workflow,
    mock_create_chat_model,
    mock_fetch_workflow_config,
    mock_fetch_project_data_with_workflow_id,
    mock_tools_registry_cls,
):
    """Test workflow creates chat model with standard model name when VERTEX_PROJECT_ID is not set."""
    # Set up the mocks based on the existing test pattern
    mock_checkpoint_notifier_instance = mock_checkpoint_notifier.return_value
    mock_tools_registry = MagicMock(spec=ToolsRegistry)
    mock_tools_registry_cls.configure = AsyncMock(return_value=mock_tools_registry)

    mock_fetch_project_data_with_workflow_id.return_value = {
        "id": 1,
        "name": "test-project",
        "description": "This is a test project",
        "http_url_to_repo": "https://example.com/project",
        "web_url": "https://example.com/project",
    }

    mock_git_lab_workflow_instance = mock_gitlab_workflow.return_value
    mock_git_lab_workflow_instance.__aenter__.return_value = (
        mock_git_lab_workflow_instance
    )
    mock_git_lab_workflow_instance.__aexit__.return_value = None
    mock_git_lab_workflow_instance._offline_mode = False
    mock_git_lab_workflow_instance.aget_tuple = AsyncMock(return_value=None)
    mock_git_lab_workflow_instance.alist = AsyncMock(return_value=[])
    mock_git_lab_workflow_instance.aput = AsyncMock(
        return_value={
            "configurable": {"thread_id": "123", "checkpoint_id": "checkpoint1"}
        }
    )
    mock_git_lab_workflow_instance.get_next_version = MagicMock(return_value=1)

    # Create a mock that will cause the run to exit early
    class AsyncIterator:
        def __init__(self):
            self.called = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.called:
                self.called = True
                raise StopAsyncIteration
            raise StopAsyncIteration

    workflow = Workflow(
        "123",
        {},
        workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
    )

    with patch(
        "duo_workflow_service.workflows.convert_to_gitlab_ci.workflow.StateGraph"
    ) as graph:
        compiled_graph = MagicMock()
        compiled_graph.aget_state = AsyncMock(return_value=None)
        compiled_graph.astream.return_value = AsyncIterator()
        instance = graph.return_value
        instance.compile.return_value = compiled_graph

        await workflow.run("Test goal")

    # Assert that create_chat_model was called without vertex configuration
    mock_create_chat_model.assert_called_with(
        max_tokens=8192,
        model="claude-3-7-sonnet-20250219",
        is_vertex=False,
    )


@pytest.mark.asyncio
@patch.dict(
    os.environ,
    {
        "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-project-id",
        "DUO_WORKFLOW__VERTEX_LOCATION": "us-central1",
    },
)
@pytest.mark.asyncio
@patch.dict(
    os.environ,
    {
        "DUO_WORKFLOW__VERTEX_PROJECT_ID": "test-project-id",
        "DUO_WORKFLOW__VERTEX_LOCATION": "us-central1",
    },
)
@patch("duo_workflow_service.workflows.abstract_workflow.ToolsRegistry", autospec=True)
@patch(
    "duo_workflow_service.workflows.abstract_workflow.fetch_project_data_with_workflow_id"
)
@patch("duo_workflow_service.workflows.abstract_workflow.fetch_workflow_config")
@patch("duo_workflow_service.workflows.convert_to_gitlab_ci.workflow.create_chat_model")
@patch("duo_workflow_service.workflows.abstract_workflow.GitLabWorkflow", autospec=True)
@patch("duo_workflow_service.workflows.abstract_workflow.UserInterface", autospec=True)
async def test_workflow_creates_chat_model_with_vertex(
    mock_checkpoint_notifier,
    mock_gitlab_workflow,
    mock_create_chat_model,
    mock_fetch_workflow_config,
    mock_fetch_project_data_with_workflow_id,
    mock_tools_registry_cls,
):
    """Test workflow creates chat model with vertex configuration when VERTEX_PROJECT_ID is set."""
    # Set up the mocks based on the existing test pattern
    mock_checkpoint_notifier_instance = mock_checkpoint_notifier.return_value
    mock_tools_registry = MagicMock(spec=ToolsRegistry)
    mock_tools_registry_cls.configure = AsyncMock(return_value=mock_tools_registry)

    mock_fetch_project_data_with_workflow_id.return_value = {
        "id": 1,
        "name": "test-project",
        "description": "This is a test project",
        "http_url_to_repo": "https://example.com/project",
        "web_url": "https://example.com/project",
    }

    mock_git_lab_workflow_instance = mock_gitlab_workflow.return_value
    mock_git_lab_workflow_instance.__aenter__.return_value = (
        mock_git_lab_workflow_instance
    )
    mock_git_lab_workflow_instance.__aexit__.return_value = None
    mock_git_lab_workflow_instance._offline_mode = False
    mock_git_lab_workflow_instance.aget_tuple = AsyncMock(return_value=None)
    mock_git_lab_workflow_instance.alist = AsyncMock(return_value=[])
    mock_git_lab_workflow_instance.aput = AsyncMock(
        return_value={
            "configurable": {"thread_id": "123", "checkpoint_id": "checkpoint1"}
        }
    )
    mock_git_lab_workflow_instance.get_next_version = MagicMock(return_value=1)

    # Create a mock that will cause the run to exit early
    class AsyncIterator:
        def __init__(self):
            self.called = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.called:
                self.called = True
                raise StopAsyncIteration
            raise StopAsyncIteration

    workflow = Workflow(
        "123",
        {},
        workflow_type=CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT,
    )

    with patch(
        "duo_workflow_service.workflows.convert_to_gitlab_ci.workflow.StateGraph"
    ) as graph:
        compiled_graph = MagicMock()
        compiled_graph.aget_state = AsyncMock(return_value=None)
        compiled_graph.astream.return_value = AsyncIterator()
        instance = graph.return_value
        instance.compile.return_value = compiled_graph

        await workflow.run("Test goal")

    # Assert that create_chat_model was called with vertex configuration
    mock_create_chat_model.assert_called_with(
        max_tokens=8192,
        model="claude-3-7-sonnet@20250219",
        is_vertex=True,
    )
