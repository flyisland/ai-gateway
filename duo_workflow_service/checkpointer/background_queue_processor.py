import asyncio
import json
import time
from typing import Dict, Any

import structlog
from fastapi import BackgroundTasks

from contract import contract_pb2
from duo_workflow_service.gitlab.http_client import GitlabHttpClient


class BackgroundQueueProcessor:
    """
    FastAPI-style background task processor for handling async queue operations.
    
    This processor ensures:
    - All queued operations are processed in FIFO order
    - No blocking of the main workflow execution
    - Proper error handling and retry logic
    - Metrics and logging for monitoring
    
    Similar to FastAPI's BackgroundTasks but optimized for workflow state operations.
    """

    def __init__(self, http_client: GitlabHttpClient, max_retries: int = 3):
        self.http_client = http_client
        self.max_retries = max_retries
        self.processing_queue: asyncio.Queue = asyncio.Queue()
        self.is_processing = False
        self._logger = structlog.stdlib.get_logger("background_queue_processor")
        self._processed_count = 0
        self._error_count = 0
        
        self._logger.debug(
            "BackgroundQueueProcessor initialized",
            max_retries=max_retries,
            http_client_type=type(http_client).__name__
        )

    async def start_processing(self, outbox: asyncio.Queue) -> None:
        """
        Start background processing of the outbox queue.
        
        This method runs in the background and processes all queued operations
        in FIFO order without blocking the main workflow.
        """
        self._logger.debug(
            "start_processing called",
            is_processing=self.is_processing,
            outbox_qsize=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
        )
        
        if self.is_processing:
            self._logger.warning("Background processor already running")
            return

        self.is_processing = True
        self._logger.info(
            "Starting background queue processor",
            outbox_qsize=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
        )
        
        # Start the processing loop as a background task
        background_tasks = BackgroundTasks()
        background_tasks.add_task(self._process_queue_loop, outbox)
        
        # Process immediately in a non-blocking way
        task = asyncio.create_task(self._process_queue_loop(outbox))
        self._logger.debug(
            "Background processing task created",
            task_id=id(task),
            outbox_id=id(outbox)
        )

    async def _process_queue_loop(self, outbox: asyncio.Queue) -> None:
        """
        Main processing loop that runs in the background.
        
        Continuously processes queued operations in FIFO order.
        """
        self._logger.info(
            "Background queue processor loop started",
            outbox_id=id(outbox),
            initial_qsize=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
        )
        
        loop_iterations = 0
        
        while self.is_processing:
            try:
                loop_iterations += 1
                if loop_iterations % 100 == 0:  # Log every 100 iterations to avoid spam
                    self._logger.debug(
                        "Background processor loop iteration",
                        iterations=loop_iterations,
                        queue_size=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown",
                        processed_count=self._processed_count,
                        error_count=self._error_count
                    )
                
                # Wait for operations with a timeout to allow graceful shutdown
                self._logger.debug(
                    "Waiting for next operation from queue",
                    queue_size=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
                )
                
                operation = await asyncio.wait_for(outbox.get(), timeout=1.0)
                
                self._logger.debug(
                    "Received operation from queue",
                    operation_type=type(operation).__name__,
                    has_http_request=operation.HasField("runHTTPRequest") if hasattr(operation, 'HasField') else "unknown",
                    queue_size_after_get=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
                )
                
                # Process the operation in FIFO order
                await self._process_operation(operation)
                
                # Mark the task as done
                outbox.task_done()
                self._logger.debug(
                    "Marked queue task as done",
                    queue_size=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
                )
                
            except asyncio.TimeoutError:
                # No operations in queue, continue checking
                self._logger.debug(
                    "No operations in queue (timeout)",
                    queue_size=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
                )
                continue
            except Exception as e:
                self._error_count += 1
                self._logger.error(
                    "Error in background queue processor loop",
                    error=str(e),
                    error_type=type(e).__name__,
                    error_count=self._error_count,
                    loop_iterations=loop_iterations
                )
                # Continue processing other operations

        self._logger.info(
            "Background queue processor loop ended",
            total_iterations=loop_iterations,
            final_processed_count=self._processed_count,
            final_error_count=self._error_count
        )

    async def _process_operation(self, action: contract_pb2.Action) -> None:
        """
        Process a single queued operation with retry logic.
        
        Args:
            action: The action from the queue to process
        """
        self._logger.debug(
            "Entering _process_operation",
            action_type=type(action).__name__,
            has_http_request=action.HasField("runHTTPRequest") if hasattr(action, 'HasField') else "unknown"
        )
        
        if not action.HasField("runHTTPRequest"):
            self._logger.warning(
                "Unsupported action type in queue",
                action_type=type(action).__name__,
                available_fields=[field.name for field in action.DESCRIPTOR.fields] if hasattr(action, 'DESCRIPTOR') else "unknown"
            )
            return

        http_request = action.runHTTPRequest
        
        self._logger.debug(
            "Processing HTTP request action",
            method=http_request.method,
            path=http_request.path,
            body_size=len(http_request.body) if http_request.body else 0,
            body_preview=http_request.body[:100] + "..." if http_request.body and len(http_request.body) > 100 else http_request.body
        )
        
        # Extract sequence number for FIFO verification
        body_data: Dict[str, Any] = {}
        try:
            body_data = json.loads(http_request.body) if http_request.body else {}
            self._logger.debug(
                "Parsed request body",
                body_keys=list(body_data.keys()),
                body_types={k: type(v).__name__ for k, v in body_data.items()}
            )
        except json.JSONDecodeError as e:
            self._logger.warning(
                "Failed to parse request body as JSON",
                error=str(e),
                body_preview=http_request.body[:100] if http_request.body else None
            )

        sequence_number = body_data.get("sequence_number", "unknown")
        
        start_time = time.time()
        retry_count = 0
        
        self._logger.debug(
            "Starting HTTP request processing",
            method=http_request.method,
            path=http_request.path,
            sequence_number=sequence_number,
            max_retries=self.max_retries
        )
        
        while retry_count <= self.max_retries:
            try:
                self._logger.debug(
                    "Attempting HTTP request",
                    method=http_request.method,
                    path=http_request.path,
                    retry_count=retry_count,
                    sequence_number=sequence_number
                )
                
                # Execute the HTTP request
                if http_request.method == "POST":
                    result = await self.http_client.apost(
                        path=http_request.path,
                        body=http_request.body,
                    )
                elif http_request.method == "PUT":
                    result = await self.http_client.aput(
                        path=http_request.path,
                        body=http_request.body,
                    )
                elif http_request.method == "GET":
                    result = await self.http_client.aget(path=http_request.path)
                else:
                    self._logger.warning(
                        "Unsupported HTTP method",
                        method=http_request.method,
                        path=http_request.path,
                        sequence_number=sequence_number
                    )
                    return

                # Success
                duration = time.time() - start_time
                self._processed_count += 1
                
                self._logger.info(
                    "Successfully processed background operation",
                    method=http_request.method,
                    path=http_request.path,
                    sequence_number=sequence_number,
                    retry_count=retry_count,
                    duration_ms=round(duration * 1000, 2),
                    processed_count=self._processed_count,
                    result_type=type(result).__name__ if result else "None",
                    result_preview=str(result)[:100] if result else None
                )
                return

            except Exception as e:
                retry_count += 1
                if retry_count <= self.max_retries:
                    # Exponential backoff for retries
                    wait_time = min(2 ** retry_count, 10)
                    self._logger.warning(
                        "Retrying background operation",
                        method=http_request.method,
                        path=http_request.path,
                        sequence_number=sequence_number,
                        retry_count=retry_count,
                        max_retries=self.max_retries,
                        error=str(e),
                        error_type=type(e).__name__,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Max retries exceeded
                    duration = time.time() - start_time
                    self._error_count += 1
                    self._logger.error(
                        "Failed to process background operation after max retries",
                        method=http_request.method,
                        path=http_request.path,
                        sequence_number=sequence_number,
                        retry_count=retry_count,
                        max_retries=self.max_retries,
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=round(duration * 1000, 2),
                        error_count=self._error_count,
                    )
                    return

    async def stop_processing(self) -> None:
        """
        Gracefully stop the background processor.
        
        Waits for current operations to complete before stopping.
        """
        if not self.is_processing:
            self._logger.debug("Background processor already stopped")
            return

        self._logger.info(
            "Stopping background queue processor",
            processed_count=self._processed_count,
            error_count=self._error_count,
        )
        
        self.is_processing = False
        
        # Give current operations time to complete
        await asyncio.sleep(0.5)
        
        self._logger.debug(
            "Background queue processor stopped",
            final_processed_count=self._processed_count,
            final_error_count=self._error_count
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics for monitoring.
        
        Returns:
            Dict containing processing metrics
        """
        stats = {
            "is_processing": self.is_processing,
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "success_rate": (
                (self._processed_count / (self._processed_count + self._error_count))
                if (self._processed_count + self._error_count) > 0
                else 1.0
            ),
        }
        
        self._logger.debug(
            "Generated processor stats",
            stats=stats
        )
        
        return stats 