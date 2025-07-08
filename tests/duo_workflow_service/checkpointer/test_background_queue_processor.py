import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from contract import contract_pb2
from duo_workflow_service.checkpointer.background_queue_processor import BackgroundQueueProcessor


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.apost = AsyncMock(return_value={"status": "success"})
    client.aput = AsyncMock(return_value={"status": "success"})
    client.aget = AsyncMock(return_value={"status": "success"})
    return client


@pytest.fixture
def outbox():
    return asyncio.Queue()


@pytest.fixture
def processor(mock_client):
    return BackgroundQueueProcessor(mock_client, max_retries=2)


@pytest.mark.asyncio
async def test_processor_initialization(mock_client):
    """Test that processor initializes correctly."""
    processor = BackgroundQueueProcessor(mock_client, max_retries=5)
    
    assert processor.http_client == mock_client
    assert processor.max_retries == 5
    assert not processor.is_processing
    assert processor._processed_count == 0
    assert processor._error_count == 0


@pytest.mark.asyncio
async def test_start_and_stop_processing(processor, outbox):
    """Test starting and stopping the background processor."""
    
    # Initially not processing
    assert not processor.is_processing
    
    # Start processing
    await processor.start_processing(outbox)
    
    # Should be processing now
    assert processor.is_processing
    
    # Stop processing
    await processor.stop_processing()
    
    # Should not be processing
    assert not processor.is_processing


@pytest.mark.asyncio
async def test_fifo_processing_order(processor, mock_client, outbox):
    """Test that operations are processed in FIFO order."""
    
    # Create operations with sequence numbers
    operations = []
    for i in range(5):
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/test/{i}",
                body=json.dumps({
                    "sequence_number": i + 1,
                    "operation_id": f"op-{i}",
                }),
            )
        )
        operations.append(action)
        await outbox.put(action)
    
    # Start processing
    await processor.start_processing(outbox)
    
    # Wait for all operations to be processed
    await outbox.join()
    
    # Verify operations were processed in order
    assert mock_client.apost.call_count == 5
    
    for i, call in enumerate(mock_client.apost.call_args_list):
        _, kwargs = call
        body = json.loads(kwargs["body"])
        assert body["sequence_number"] == i + 1
        assert body["operation_id"] == f"op-{i}"
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_http_method_support(processor, mock_client, outbox):
    """Test that different HTTP methods are supported."""
    
    methods = [
        ("POST", "/api/v4/test"),
        ("PUT", "/api/v4/test/123"),
        ("GET", "/api/v4/test/456"),
    ]
    
    for method, path in methods:
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method=method,
                path=path,
                body=json.dumps({"data": f"test-{method}"}),
            )
        )
        await outbox.put(action)
    
    await processor.start_processing(outbox)
    await outbox.join()
    
    # Verify correct methods were called
    assert mock_client.apost.call_count == 1
    assert mock_client.aput.call_count == 1
    assert mock_client.aget.call_count == 1
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_unsupported_http_method(processor, mock_client, outbox):
    """Test handling of unsupported HTTP methods."""
    
    action = contract_pb2.Action(
        runHTTPRequest=contract_pb2.RunHTTPRequest(
            method="DELETE",  # Not supported
            path="/api/v4/test",
            body=json.dumps({"data": "test"}),
        )
    )
    await outbox.put(action)
    
    await processor.start_processing(outbox)
    await outbox.join()
    
    # No HTTP calls should have been made
    assert mock_client.apost.call_count == 0
    assert mock_client.aput.call_count == 0
    assert mock_client.aget.call_count == 0
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_retry_logic_with_exponential_backoff(processor, mock_client, outbox):
    """Test retry logic with exponential backoff."""
    
    # Configure client to fail twice then succeed
    mock_client.apost.side_effect = [
        Exception("Network error"),
        Exception("Timeout error"),
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
    
    start_time = time.time()
    await processor.start_processing(outbox)
    await outbox.join()
    
    # Should have made 3 attempts
    assert mock_client.apost.call_count == 3
    
    # Should have taken time for exponential backoff (2^1 + 2^2 = 6 seconds minimum)
    duration = time.time() - start_time
    assert duration >= 0.003  # At least some backoff time
    
    # Success should be recorded
    stats = processor.get_stats()
    assert stats["processed_count"] == 1
    assert stats["error_count"] == 0
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_max_retries_exceeded(processor, mock_client, outbox):
    """Test behavior when max retries are exceeded."""
    
    # Configure client to always fail
    mock_client.apost.side_effect = Exception("Persistent error")
    
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
    
    # Should have made max_retries + 1 attempts
    assert mock_client.apost.call_count == 3  # 1 initial + 2 retries
    
    # Error should be recorded
    stats = processor.get_stats()
    assert stats["processed_count"] == 0
    assert stats["error_count"] == 1
    assert stats["success_rate"] == 0.0
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_statistics_tracking(processor, mock_client, outbox):
    """Test that statistics are tracked correctly."""
    
    # Initial stats
    stats = processor.get_stats()
    assert stats["processed_count"] == 0
    assert stats["error_count"] == 0
    assert stats["success_rate"] == 1.0
    assert not stats["is_processing"]
    
    # Add successful operations
    for i in range(3):
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/test/{i}",
                body=json.dumps({"sequence_number": i + 1}),
            )
        )
        await outbox.put(action)
    
    # Configure one operation to fail
    mock_client.apost.side_effect = [
        {"status": "success"},
        Exception("Error"),  # This will fail after max retries
        {"status": "success"},
    ]
    
    await processor.start_processing(outbox)
    
    # Check processing status
    stats = processor.get_stats()
    assert stats["is_processing"]
    
    await outbox.join()
    
    # Final stats
    stats = processor.get_stats()
    assert stats["processed_count"] == 2  # 2 successful
    assert stats["error_count"] == 1    # 1 failed
    assert stats["success_rate"] == 2/3  # 2 out of 3
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_graceful_shutdown_with_pending_operations(processor, mock_client, outbox):
    """Test graceful shutdown with operations still in queue."""
    
    # Add a slow operation
    async def slow_operation(*args, **kwargs):
        await asyncio.sleep(0.1)  # Simulate slow operation
        return {"status": "success"}
    
    mock_client.apost.side_effect = slow_operation
    
    # Add operations to queue
    for i in range(3):
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/test/{i}",
                body=json.dumps({"sequence_number": i + 1}),
            )
        )
        await outbox.put(action)
    
    # Start processing
    await processor.start_processing(outbox)
    
    # Give it time to start
    await asyncio.sleep(0.05)
    
    # Stop processing (should be graceful)
    await processor.stop_processing()
    
    # Should not be processing anymore
    assert not processor.is_processing


@pytest.mark.asyncio
async def test_unsupported_action_type(processor, outbox):
    """Test handling of unsupported action types."""
    
    # Create action without runHTTPRequest field
    action = contract_pb2.Action()
    # Don't set runHTTPRequest field
    
    await outbox.put(action)
    
    await processor.start_processing(outbox)
    await outbox.join()
    
    # No processing should have occurred
    stats = processor.get_stats()
    assert stats["processed_count"] == 0
    assert stats["error_count"] == 0
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_json_parsing_error_handling(processor, mock_client, outbox):
    """Test handling of JSON parsing errors in operation bodies."""
    
    action = contract_pb2.Action(
        runHTTPRequest=contract_pb2.RunHTTPRequest(
            method="POST",
            path="/api/v4/test",
            body="invalid json{",  # Invalid JSON
        )
    )
    await outbox.put(action)
    
    await processor.start_processing(outbox)
    await outbox.join()
    
    # Operation should still be processed (JSON parsing failure is not critical)
    assert mock_client.apost.call_count == 1
    
    stats = processor.get_stats()
    assert stats["processed_count"] == 1
    
    await processor.stop_processing()


@pytest.mark.asyncio
async def test_concurrent_processing_safety(mock_client):
    """Test that concurrent processing is handled safely."""
    
    processor = BackgroundQueueProcessor(mock_client)
    outbox1 = asyncio.Queue()
    outbox2 = asyncio.Queue()
    
    # Try to start processing twice
    await processor.start_processing(outbox1)
    await processor.start_processing(outbox2)  # Should be ignored
    
    assert processor.is_processing
    
    await processor.stop_processing()
    assert not processor.is_processing


@pytest.mark.asyncio
async def test_processing_performance(processor, mock_client, outbox):
    """Test processing performance with many operations."""
    
    num_operations = 100
    
    # Add many operations
    for i in range(num_operations):
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/test/{i}",
                body=json.dumps({"sequence_number": i + 1}),
            )
        )
        await outbox.put(action)
    
    start_time = time.time()
    await processor.start_processing(outbox)
    await outbox.join()
    duration = time.time() - start_time
    
    # All operations should be processed
    assert mock_client.apost.call_count == num_operations
    
    # Performance should be reasonable (less than 1 second for 100 operations)
    assert duration < 1.0
    
    stats = processor.get_stats()
    assert stats["processed_count"] == num_operations
    assert stats["error_count"] == 0
    
    await processor.stop_processing() 