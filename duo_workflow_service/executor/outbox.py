import asyncio
from enum import StrEnum
from uuid import uuid4

import structlog

from contract import contract_pb2
from duo_workflow_service.tracking import log_exception

log = structlog.stdlib.get_logger("outbox")

type ActionRequestID = str

MAX_MESSAGE_LENGTH = 200


class OutboxSignal(StrEnum):
    NO_MORE_OUTBOUND_REQUESTS = "no_more_outbound_requests"


class UnknownResponseIDException(Exception):
    pass


class Outbox:
    """Class to manage outbound requests to clients."""

    def __init__(self):
        self._queue: asyncio.Queue[contract_pb2.Action | OutboxSignal] = asyncio.Queue()
        self._action_response: dict[
            ActionRequestID, asyncio.Future[contract_pb2.ClientEvent] | None
        ] = {}

    def put_action(
        self,
        action: contract_pb2.Action,
        result: asyncio.Future[contract_pb2.ClientEvent] | None = None,
    ) -> ActionRequestID:
        """Put an item into the outbox queue."""

        action.requestID = str(uuid4())
        self._action_response[action.requestID] = result
        self._queue.put_nowait(action)
        return action.requestID

    async def put_action_and_wait_for_response(
        self, action: contract_pb2.Action
    ) -> contract_pb2.ClientEvent:
        """Put an action request into the queue and wait for the client response."""

        result = asyncio.get_event_loop().create_future()
        self.put_action(action, result=result)
        return await result

    async def get(self) -> contract_pb2.Action | OutboxSignal:
        """Get an item from the outbox."""

        return await self._queue.get()

    def set_action_response(self, event: contract_pb2.ClientEvent):
        """Set action response to the future object which is awaited by the caller."""

        if event.actionResponse.requestID in self._action_response:
            future = self._action_response[event.actionResponse.requestID]

            if future:
                future.set_result(event)

            del self._action_response[event.actionResponse.requestID]
        else:
            requestID, future = next(((k, v) for k, v in self._action_response.items() if v is not None), (None, None))

            if future and requestID:
                event.actionResponse.requestID = requestID
                future.set_result(event)

            del self._action_response[event.actionResponse.requestID]

    def close(self) -> None:
        """Close the outbox for exiting send events loop."""

        self._queue.put_nowait(OutboxSignal.NO_MORE_OUTBOUND_REQUESTS)

    def check_empty(self) -> None:
        try:
            while True:
                try:
                    item: contract_pb2.Action | OutboxSignal = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    # Queue is empty, exit loop
                    break

                content = str(item)

                if len(content) > MAX_MESSAGE_LENGTH:
                    content = f"{content[:MAX_MESSAGE_LENGTH]}..."

                log.error(
                    "Found unsent items in outbox",
                    content=content,
                )
        except Exception as e:
            log_exception(
                e,
                extra={
                    "context": "Error draining outbox queue",
                },
            )
            raise
