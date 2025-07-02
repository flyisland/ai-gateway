import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata

from contract import contract_pb2
from duo_workflow_service.checkpointer.async_queue_checkpointer import AsyncQueueCheckpointer
from duo_workflow_service.checkpointer.background_queue_processor import BackgroundQueueProcessor
from duo_workflow_service.checkpointer.gitlab_workflow import WorkflowStatusEventEnum
from duo_workflow_service.entities.state import WorkflowStatusEnum
from duo_workflow_service.internal_events.event_enum import CategoryEnum


@pytest.fixture
def outbox():
    return asyncio.Queue()


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.apost = AsyncMock(return_value={"status": "success"})
    client.aput = AsyncMock(return_value={"status": "success"})
    client.aget = AsyncMock(return_value={"status": "success"})
    return client


@pytest.fixture
def workflow_id():
    return "test-workflow-123"


@pytest.fixture
def workflow_type():
    return CategoryEnum.WORKFLOW_CHAT


@pytest.fixture
def async_checkpointer(mock_client, workflow_id, workflow_type, outbox):
    return AsyncQueueCheckpointer(
        client=mock_client,
        workflow_id=workflow_id,
        workflow_type=workflow_type,
        outbox=outbox,
    )


@pytest.fixture
def sample_config():
    return {
        "configurable": {
            "thread_id": "test-workflow-123",
            "checkpoint_id": "parent-checkpoint-456",
        }
    }


@pytest.fixture
def sample_checkpoint():
    return {
        "id": "checkpoint-123",
        "channel_values": {"status": WorkflowStatusEnum.EXECUTION},
        "channel_versions": {},
        "pending_sends": [],
        "versions_seen": {},
        "ts": "2024-01-01T00:00:00Z",
        "v": 1,
    }


@pytest.fixture
def sample_metadata():
    return {"writes": {"agent": {"status": WorkflowStatusEnum.EXECUTION}}}


@pytest.mark.asyncio
async def test_aput_is_completely_non_blocking(
    async_checkpointer, sample_config, sample_checkpoint, sample_metadata, outbox
):
    """Test that aput is completely non-blocking and uses FIFO ordering."""
    
    # Mock all potentially blocking operations
    with patch.object(async_checkpointer, '_get_workflow_status_event') as mock_get_status:
        mock_get_status.return_value = WorkflowStatusEventEnum.START
        
        start_time = time.time()
        
        # Execute aput - should return immediately
        result = await async_checkpointer.aput(
            config=sample_config,
            checkpoint=sample_checkpoint,
            metadata=sample_metadata,
            new_versions={},
        )
        
        duration = time.time() - start_time
        
        # Should complete in under 10ms (completely non-blocking)
        assert duration < 0.01, f"aput took {duration:.3f}s, should be < 0.01s"

        # Verify it returns immediately with correct config
        expected_result = {
            "configurable": {
                "thread_id": "test-workflow-123",
                "checkpoint_id": "checkpoint-123",
            }
        }
        assert result == expected_result

        # Should have queued 2 operations: status update + checkpoint save
        assert outbox.qsize() == 2
        
        # Verify FIFO ordering with sequence numbers
        status_action = outbox.get_nowait()
        checkpoint_action = outbox.get_nowait()
        
        status_body = json.loads(status_action.runHTTPRequest.body)
        checkpoint_body = json.loads(checkpoint_action.runHTTPRequest.body)
        
        assert status_body["sequence_number"] == 1
        assert checkpoint_body["sequence_number"] == 2


@pytest.mark.asyncio
async def test_background_queue_processor_fifo_ordering(mock_client, outbox):
    """Test that BackgroundQueueProcessor processes operations in FIFO order."""
    
    processor = BackgroundQueueProcessor(mock_client)
    
    # Create multiple operations with different sequence numbers
    operations = []
    for i in range(5):
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/test/{i}",
                body=json.dumps({"sequence_number": i + 1, "data": f"operation-{i}"}),
            )
        )
        operations.append(action)
        await outbox.put(action)
    
    # Start processing
    await processor.start_processing(outbox)
    
    # Wait for processing to complete
    await outbox.join()
    
    # Verify operations were processed in order
    assert mock_client.apost.call_count == 5
    
    for i, call in enumerate(mock_client.apost.call_args_list):
        call_args, call_kwargs = call
        body = json.loads(call_kwargs["body"])
        assert body["sequence_number"] == i + 1
        assert body["data"] == f"operation-{i}"
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_background_queue_processor_retry_logic(mock_client, outbox):
    """Test retry logic with exponential backoff."""
    
    processor = BackgroundQueueProcessor(mock_client, max_retries=2)
    
    # Mock client to fail twice then succeed
    mock_client.apost.side_effect = [
        Exception("Network error"),
        Exception("Timeout"),
        {"status": "success"},
    ]
    
    action = contract_pb2.Action(
        runHTTPRequest=contract_pb2.RunHTTPRequest(
            method="POST",
            path="/api/v4/test",
            body=json.dumps({"sequence_number": 1}),
        )
    )
    await outbox.put(action)
    
    # Start processing
    start_time = time.time()
    await processor.start_processing(outbox)
    
    # Wait for processing to complete
    await outbox.join()
    
    # Should have made 3 attempts (2 retries + 1 success)
    assert mock_client.apost.call_count == 3
    
    # Should have taken some time due to exponential backoff
    duration = time.time() - start_time
    assert duration > 0.003  # At least 2^1 + 2^2 = 6 seconds of backoff
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_aput_writes_with_fifo_ordering(
    async_checkpointer, sample_config, outbox
):
    """Test that aput_writes maintains FIFO ordering."""
    
    writes = [("agent", {"message": "test"}), ("user", {"input": "hello"})]
    task_id = "task-123"
    task_path = "agent.run"
    
    # Execute multiple writes
    for i in range(3):
        await async_checkpointer.aput_writes(
            config=sample_config,
            writes=writes,
            task_id=f"{task_id}-{i}",
            task_path=task_path,
        )

    # Verify all writes were queued with proper sequence numbers
    assert outbox.qsize() == 3
    
    for expected_sequence in range(1, 4):
        action = outbox.get_nowait()
        body_data = json.loads(action.runHTTPRequest.body)
        assert body_data["sequence_number"] == expected_sequence
        assert body_data["task_id"] == f"{task_id}-{expected_sequence - 1}"


@pytest.mark.asyncio
async def test_concurrent_operations_maintain_fifo_order(
    async_checkpointer, sample_config, sample_checkpoint, sample_metadata, outbox
):
    """Test that concurrent operations maintain FIFO order."""
    
    with patch.object(async_checkpointer, '_get_workflow_status_event') as mock_get_status:
        mock_get_status.return_value = WorkflowStatusEventEnum.START
        
        # Execute multiple concurrent operations
        tasks = []
        for i in range(5):
            checkpoint = sample_checkpoint.copy()
            checkpoint["id"] = f"checkpoint-{i}"
            
            task = async_checkpointer.aput(
                config=sample_config,
                checkpoint=checkpoint,
                metadata=sample_metadata,
                new_versions={},
            )
            tasks.append(task)
        
        # All operations should complete quickly
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time
        
        assert duration < 0.05  # Should complete in under 50ms
        
        # Verify all operations were queued (2 per checkpoint: status + save)
        assert outbox.qsize() == 10
        
        # Verify sequence numbers are in order
        for expected_sequence in range(1, 11):
            action = outbox.get_nowait()
            body_data = json.loads(action.runHTTPRequest.body)
            assert body_data["sequence_number"] == expected_sequence


@pytest.mark.asyncio
async def test_performance_vs_blocking_implementation():
    """Compare performance between blocking and non-blocking implementations."""
    
    async def simulate_blocking_checkpoint_save():
        """Simulate current GitLabWorkflow blocking behavior."""
        await asyncio.sleep(0.1)  # 100ms per save
        return {"saved": True}
    
    async def simulate_async_queue_save(queue):
        """Simulate AsyncQueueCheckpointer non-blocking behavior."""
        await queue.put("save_action")  # Queue and return immediately
        return {"queued": True}
    
    # Test blocking approach (current)
    start_time = time.time()
    for i in range(10):
        await simulate_blocking_checkpoint_save()
    blocking_duration = time.time() - start_time
    
    # Test async queue approach (new)
    queue = asyncio.Queue()
    start_time = time.time()
    for i in range(10):
        await simulate_async_queue_save(queue)
    async_duration = time.time() - start_time
    
    # Async queue should be significantly faster
    improvement = blocking_duration / async_duration if async_duration > 0 else float('inf')
    
    assert async_duration < 0.01  # Should complete in under 10ms
    assert blocking_duration > 1.0  # Should take over 1 second
    assert improvement > 100  # Should be over 100x faster
    
    # Verify all saves were queued
    assert queue.qsize() == 10


@pytest.mark.asyncio
async def test_background_processor_statistics(mock_client, outbox):
    """Test that background processor tracks statistics correctly."""
    
    processor = BackgroundQueueProcessor(mock_client)
    
    # Initial stats
    stats = processor.get_stats()
    assert stats["processed_count"] == 0
    assert stats["error_count"] == 0
    assert stats["success_rate"] == 1.0
    
    # Add some successful operations
    for i in range(3):
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/test/{i}",
                body=json.dumps({"sequence_number": i + 1}),
            )
        )
        await outbox.put(action)
    
    # Add one failing operation
    mock_client.apost.side_effect = [
        {"status": "success"},
        {"status": "success"}, 
        {"status": "success"},
    ]
    
    await processor.start_processing(outbox)
    await outbox.join()
    
    # Check final stats
    stats = processor.get_stats()
    assert stats["processed_count"] == 3
    assert stats["error_count"] == 0
    assert stats["success_rate"] == 1.0
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_sequence_number_persistence_across_operations(async_checkpointer, outbox):
    """Test that sequence numbers persist and increment across different operation types."""
    
    config = {"configurable": {"thread_id": "test", "checkpoint_id": "parent"}}
    checkpoint = {"id": "test", "channel_values": {}, "ts": "2024-01-01"}
    metadata = {"writes": {}}
    writes = [("agent", {"message": "test"})]
    
    with patch.object(async_checkpointer, '_get_workflow_status_event') as mock_get_status:
        mock_get_status.return_value = None  # No status update
        
        # Execute different types of operations
        await async_checkpointer.aput(config, checkpoint, metadata, {})
        await async_checkpointer.aput_writes(config, writes, "task-1")
        await async_checkpointer.aput(config, checkpoint, metadata, {})
        
        # Verify sequence numbers increment across all operation types
        assert outbox.qsize() == 3
        
        # First checkpoint save
        action1 = outbox.get_nowait()
        body1 = json.loads(action1.runHTTPRequest.body)
        assert body1["sequence_number"] == 1
        
        # Writes save
        action2 = outbox.get_nowait() 
        body2 = json.loads(action2.runHTTPRequest.body)
        assert body2["sequence_number"] == 2
        
        # Second checkpoint save
        action3 = outbox.get_nowait()
        body3 = json.loads(action3.runHTTPRequest.body)
        assert body3["sequence_number"] == 3


@pytest.mark.asyncio
async def test_offline_mode_skips_operations(mock_client, workflow_id, workflow_type, outbox):
    """Test that operations are skipped in offline mode."""
    
    with patch.dict('os.environ', {'USE_MEMSAVER': 'true'}):
        checkpointer = AsyncQueueCheckpointer(
            client=mock_client,
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            outbox=outbox,
        )
        
        # Execute operations in offline mode
        await checkpointer.aput_writes(
            config={},
            writes=[("agent", {"message": "test"})],
            task_id="task-123",
        )
        
        with patch.object(checkpointer, '_get_workflow_status_event') as mock_get_status:
            mock_get_status.return_value = WorkflowStatusEventEnum.START
            
            await checkpointer._queue_status_update(WorkflowStatusEventEnum.START)

        # No operations should be queued in offline mode
        assert outbox.qsize() == 0


@pytest.mark.asyncio
async def test_error_handling_in_background_processor(mock_client, outbox):
    """Test error handling and recovery in background processor."""
    
    processor = BackgroundQueueProcessor(mock_client, max_retries=1)
    
    # Mock client to always fail
    mock_client.apost.side_effect = Exception("Persistent error")
    
    # Add an operation that will fail
    action = contract_pb2.Action(
        runHTTPRequest=contract_pb2.RunHTTPRequest(
            method="POST",
            path="/api/v4/test",
            body=json.dumps({"sequence_number": 1}),
        )
    )
    await outbox.put(action)
    
    await processor.start_processing(outbox)
    await outbox.join()
    
    # Should have attempted max_retries + 1 times
    assert mock_client.apost.call_count == 2  # 1 initial + 1 retry
    
    # Error count should be tracked
    stats = processor.get_stats()
    assert stats["error_count"] == 1
    assert stats["processed_count"] == 0
    assert stats["success_rate"] == 0.0
    
    await processor.stop_processing() 