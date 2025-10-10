import asyncio
from enum import StrEnum
from typing import Optional, override
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from contract import contract_pb2

type ActionRequestID = str


class OutboxSignal(StrEnum):
    NO_MORE_OUTBOUND_REQUESTS = "no_more_outbound_requests"


class ActionRequest(BaseModel):
    """Outbound request to clients from Duo Workflow Service."""

    action: contract_pb2.Action
    result: Optional[asyncio.Future[contract_pb2.ClientEvent]] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data):
        data["action"].requestID = str(uuid4())

        super().__init__(**data)


class UnknownResponseIDException(Exception):
    pass


class OutboxQueue(asyncio.Queue[ActionRequest | OutboxSignal]):
    _action_response: dict[
        ActionRequestID, asyncio.Future[contract_pb2.ClientEvent] | None
    ] = {}

    @override
    async def put(self, item):
        self._prepare_action_response(item)

        return await super().put(item)

    @override
    def put_nowait(self, item):
        self._prepare_action_response(item)

        return super().put_nowait(item)

    def set_action_response(self, event: contract_pb2.ClientEvent):
        """Set action response to the future object which is awaited by the caller."""

        if event.actionResponse.requestID in self._action_response:
            future = self._action_response[event.actionResponse.requestID]

            if future:
                future.set_result(event)

            del self._action_response[event.actionResponse.requestID]
        else:
            raise UnknownResponseIDException(
                f"Response ID {event.actionResponse.requestID} is not found"
            )

    def _prepare_action_response(self, item):
        if isinstance(item, ActionRequest):
            self._action_response[item.action.requestID] = item.result
