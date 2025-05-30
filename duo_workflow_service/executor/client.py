import asyncio
from asyncio import Future
from typing import AsyncIterable, AsyncIterator
from uuid import uuid4

import structlog

from contract import contract_pb2

log = structlog.stdlib.get_logger("server")


# TODO: Needs unit tests
class ExecutorClient:
    """Manages all communication with the Executor."""

    incoming_iterator: AsyncIterable[contract_pb2.ClientEvent]
    outbound_requests: asyncio.Queue[contract_pb2.Action]
    request_responses_by_id: dict[str, Future[contract_pb2.ClientEvent]] = {}

    def __init__(
        self,
        incoming_iterator: AsyncIterable[contract_pb2.ClientEvent],
    ):
        self.incoming_iterator = incoming_iterator
        self.outbound_requests = asyncio.Queue()
        self.request_responses_by_id = {}

    async def request(self, action: contract_pb2.Action) -> contract_pb2.ClientEvent:
        """Sends request to the Executor and receives response."""

        loop = asyncio.get_event_loop()
        future = loop.create_future()

        action.requestID = str(uuid4())

        # TODO: Should we add a timeout in case we don't get the response in time?
        self.request_responses_by_id[action.requestID] = future

        await self.outbound_requests.put(action)

        return await future

    async def send(self, action: contract_pb2.Action):
        """Sends request to the Executor and does not expect a response."""

        action.requestID = str(uuid4())
        await self.outbound_requests.put(action)

    async def process_incoming(self):
        async for event in self.incoming_iterator:
            requestID = event.actionResponse.requestID
            future = self.request_responses_by_id.get(requestID)
            if future:
                future.set_result(event)
                del self.request_responses_by_id[requestID]
            else:
                log.info(
                    "Received response for unknown requestID: %s. Could be a response to an action sent via 'send' instead of 'request'.",
                    requestID,
                )

    async def execute_stream(self) -> AsyncIterator[contract_pb2.Action]:
        """Handles the interaction between outgoing and incoming iterators.

        It provides continuous action sending and waiting for responses.
        """

        asyncio.create_task(self.process_incoming())

        while True:
            yield await self.outbound_requests.get()
