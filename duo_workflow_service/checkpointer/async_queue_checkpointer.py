import asyncio
import base64
import json
import time
from typing import Any, Optional

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
)

from contract import contract_pb2
from duo_workflow_service.checkpointer.gitlab_workflow import GitLabWorkflow
from duo_workflow_service.json_encoder.encoder import CustomEncoder


class QueuedOperation:
    """Represents a queued operation with FIFO ordering."""
    
    def __init__(self, operation_type: str, data: dict, sequence_number: int):
        self.operation_type = operation_type
        self.data = data
        self.sequence_number = sequence_number
        self.timestamp = time.time()


class AsyncQueueCheckpointer(GitLabWorkflow):
    """
    Completely non-blocking async queue-based checkpointer that extends GitLabWorkflow.
    
    This checkpointer sends ALL operations (checkpoint saves, status updates, writes) 
    to a background queue instead of blocking on any HTTP calls to GitLab Rails. 
    This allows LangGraph execution to continue immediately while all state operations 
    happen asynchronously in FIFO order.
    
    Similar to FastAPI's BackgroundTasks, this ensures:
    - No HTTP calls block workflow execution
    - All operations are processed in FIFO order
    - Workflow responsiveness is maximized
    """

    def __init__(
        self,
        client,
        workflow_id: str,
        workflow_type,
        outbox: asyncio.Queue,
    ):
        self._logger = structlog.stdlib.get_logger("async_queue_checkpointer")
        self._logger.debug(
            "Initializing AsyncQueueCheckpointer",
            workflow_id=workflow_id,
            workflow_type=workflow_type.value,
            outbox_qsize=outbox.qsize() if hasattr(outbox, 'qsize') else "unknown"
        )
        
        super().__init__(client, workflow_id, workflow_type)
        self.outbox = outbox
        
        self._logger.info(
            "AsyncQueueCheckpointer initialized successfully",
            workflow_id=self._workflow_id,
            offline_mode=self._offline_mode
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """
        Queue checkpoint save operation and return immediately (completely non-blocking).
        
        This method:
        1. Queues workflow status updates (non-blocking)
        2. Queues the checkpoint save operation (non-blocking)
        3. Returns immediately without waiting for ANY Rails operations
        """
        self._logger.debug(
            "aput method called",
            checkpoint_id=checkpoint["id"],
            metadata_keys=list(metadata.keys()) if metadata else [],
            config_keys=list(config.keys()) if config else []
        )
        
        configurable = config.get("configurable", {})
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = configurable.get("checkpoint_id")

        self._logger.debug(
            "Extracted checkpoint identifiers",
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            configurable_keys=list(configurable.keys())
        )

        # Queue workflow status updates (non-blocking, FIFO ordered)
        status = self._get_workflow_status_event(checkpoint, metadata)
        if status:
            self._logger.debug(
                "Status event detected, queuing status update",
                status=status.value,
                checkpoint_id=checkpoint_id
            )
            await self._queue_status_update(status)
        else:
            self._logger.debug(
                "No status event required",
                checkpoint_id=checkpoint_id
            )

        # Queue the checkpoint save operation asynchronously (FIFO ordered)
        self._logger.debug(
            "Queuing checkpoint save operation",
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id
        )
        
        await self._queue_checkpoint_save(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            checkpoint=checkpoint,
            metadata=metadata,
        )

        self._logger.info(
            "Checkpoint and status updates queued for async processing",
            thread_ts=checkpoint_id,
            parent_ts=parent_checkpoint_id,
        )

        result_config = {
            "configurable": {
                "thread_id": self._workflow_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        
        self._logger.debug(
            "aput method returning config",
            result_config=result_config
        )

        # Return immediately - don't wait for any operations to complete
        return result_config

    async def _queue_status_update(self, status) -> None:
        """
        Queue a workflow status update operation (non-blocking).
        
        This replaces the blocking _update_workflow_status call.
        """
        self._logger.debug(
            "Entering _queue_status_update",
            status=status.value,
            offline_mode=self._offline_mode
        )
        
        if self._offline_mode:
            self._logger.debug("Skipping status update due to offline mode")
            return

        # Create status update action with FIFO ordering
        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST", 
                path=f"/api/v4/ai/duo_workflows/workflows/{self._workflow_id}/status",
                body=json.dumps({
                    "status": status.value,
                }),
            )
        )

        self._logger.debug(
            "Created status update action",
            method="POST",
            path=f"/api/v4/ai/duo_workflows/workflows/{self._workflow_id}/status",
            body_status=status.value,
            outbox_qsize_before=self.outbox.qsize() if hasattr(self.outbox, 'qsize') else "unknown"
        )

        # Queue the action - this returns immediately
        await self.outbox.put(action)
        
        self._logger.debug(
            "Status update queued for async processing",
            status=status.value,
            workflow_id=self._workflow_id,
            outbox_qsize_after=self.outbox.qsize() if hasattr(self.outbox, 'qsize') else "unknown"
        )

    async def _queue_checkpoint_save(
        self,
        checkpoint_id: str,
        parent_checkpoint_id: Optional[str],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
    ) -> None:
        """
        Queue a checkpoint save operation using FIFO ordering.
        """
        self._logger.debug(
            "Entering _queue_checkpoint_save",
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            checkpoint_keys=list(checkpoint.keys()) if checkpoint else [],
            metadata_keys=list(metadata.keys()) if metadata else []
        )
        
        # Create the checkpoint save action with sequence number for FIFO
        try:
            body_data = {
                "thread_ts": checkpoint_id,
                "parent_ts": parent_checkpoint_id,
                "checkpoint": checkpoint,
                "metadata": metadata,
            }
            
            serialized_body = json.dumps(body_data, cls=CustomEncoder)
            
            self._logger.debug(
                "Serialized checkpoint data",
                checkpoint_id=checkpoint_id,
                body_size=len(serialized_body),
                body_preview=serialized_body[:200] + "..." if len(serialized_body) > 200 else serialized_body
            )
            
        except Exception as e:
            self._logger.error(
                "Failed to serialize checkpoint data",
                checkpoint_id=checkpoint_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/ai/duo_workflows/workflows/{self._workflow_id}/checkpoints",
                body=serialized_body,
            )
        )

        self._logger.debug(
            "Created checkpoint save action",
            method="POST",
            path=f"/api/v4/ai/duo_workflows/workflows/{self._workflow_id}/checkpoints",
            checkpoint_id=checkpoint_id,
            outbox_qsize_before=self.outbox.qsize() if hasattr(self.outbox, 'qsize') else "unknown"
        )

        # Queue the action - this returns immediately
        await self.outbox.put(action)

        self._logger.debug(
            "Checkpoint save action queued for async processing",
            checkpoint_id=checkpoint_id,
            workflow_id=self._workflow_id,
            outbox_qsize_after=self.outbox.qsize() if hasattr(self.outbox, 'qsize') else "unknown"
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes,
        task_id: str,
        task_path: str = "",
    ) -> None:
        """
        Queue writes save operation asynchronously (completely non-blocking).
        
        Similar to aput, this queues the writes save and returns immediately.
        """
        self._logger.debug(
            "aput_writes method called",
            task_id=task_id,
            task_path=task_path,
            writes_count=len(writes) if writes else 0,
            writes_preview=writes[:2] if writes else [],
            offline_mode=self._offline_mode
        )
        
        if self._offline_mode:
            self._logger.debug("Skipping writes save due to offline mode")
            return

        configurable = config.get("configurable", {})
        checkpoint_id = configurable.get("checkpoint_id")

        self._logger.debug(
            "Extracted writes configuration",
            checkpoint_id=checkpoint_id,
            configurable_keys=list(configurable.keys())
        )

        if not writes or writes[0][0] != "__interrupt__":
            self._logger.debug(
                "No interrupt writes to save",
                writes_empty=not writes,
                first_write_channel=writes[0][0] if writes else None
            )
            return None

        self._logger.debug(
            "Processing interrupt writes",
            writes_count=len(writes),
            first_write_details={"channel": writes[0][0], "data_type": type(writes[0][1]).__name__} if writes else {}
        )

        encoded_writes = []
        for idx, (channel, val) in enumerate(writes):
            try:
                t, bval = self.serde.dumps_typed(val)
                encoded_data = base64.b64encode(bval).decode("utf-8")
                
                encoded_write = {
                    "task": task_id,
                    "channel": channel,
                    "data": encoded_data,
                    "write_type": t,
                    "idx": idx,
                }
                encoded_writes.append(encoded_write)
                
                self._logger.debug(
                    "Encoded write",
                    idx=idx,
                    channel=channel,
                    write_type=t,
                    data_size=len(encoded_data)
                )
                
            except Exception as e:
                self._logger.error(
                    "Failed to encode write",
                    idx=idx,
                    channel=channel,
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise

        # Queue the writes save operation with FIFO ordering
        try:
            body_data = {
                "thread_ts": checkpoint_id,
                "checkpoint_writes": encoded_writes,
            }
            
            serialized_body = json.dumps(body_data, cls=CustomEncoder)
            
            self._logger.debug(
                "Serialized writes data",
                checkpoint_id=checkpoint_id,
                encoded_writes_count=len(encoded_writes),
                body_size=len(serialized_body)
            )
            
        except Exception as e:
            self._logger.error(
                "Failed to serialize writes data",
                checkpoint_id=checkpoint_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

        action = contract_pb2.Action(
            runHTTPRequest=contract_pb2.RunHTTPRequest(
                method="POST",
                path=f"/api/v4/ai/duo_workflows/workflows/{self._workflow_id}/checkpoint_writes_batch",
                body=serialized_body,
            )
        )

        self._logger.debug(
            "Created writes save action",
            method="POST",
            path=f"/api/v4/ai/duo_workflows/workflows/{self._workflow_id}/checkpoint_writes_batch",
            task_id=task_id,
            outbox_qsize_before=self.outbox.qsize() if hasattr(self.outbox, 'qsize') else "unknown"
        )

        await self.outbox.put(action)
        
        self._logger.debug(
            "Writes save action queued for async processing",
            task_id=task_id,
            workflow_id=self._workflow_id,
            outbox_qsize_after=self.outbox.qsize() if hasattr(self.outbox, 'qsize') else "unknown"
        )

    async def _update_workflow_status(self, status) -> None:
        """
        Override parent method to make it non-blocking.
        
        Instead of directly calling the HTTP client, queue the status update.
        This ensures no workflow blocking while maintaining the same interface.
        """
        self._logger.debug(
            "_update_workflow_status called (delegating to queue)",
            status=status.value if hasattr(status, 'value') else str(status)
        )
        await self._queue_status_update(status) 