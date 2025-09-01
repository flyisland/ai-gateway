import asyncio
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from contract import contract_pb2
from duo_workflow_service.executor.outbox import (
    MAX_MESSAGE_LENGTH,
    Outbox,
    OutboxSignal,
    UnknownResponseIDException,
)


class TestOutbox:
    @pytest.fixture
    def outbox(self) -> Outbox:
        return Outbox()

    @pytest.mark.parametrize(
        ("action", "future"),
        [
            (contract_pb2.Action(), None),
            (contract_pb2.Action(), asyncio.Future()),
        ],
    )
    def test_put_action(self, outbox: Outbox, action, future):
        assert action.requestID == ""

        request_id = outbox.put_action(action, result=future)

        assert action.requestID == request_id
        assert UUID(request_id)
        assert request_id in outbox._action_response

        if future:
            assert outbox._action_response[request_id] is future
        else:
            assert outbox._action_response[request_id] is None

    @pytest.mark.asyncio
    async def test_put_action_and_wait_for_response(self, outbox: Outbox):
        action = contract_pb2.Action()
        client_response: contract_pb2.ClientEvent | None = None

        async def set_result():
            nonlocal client_response

            item = await outbox.get()

            client_response = contract_pb2.ClientEvent(
                actionResponse=contract_pb2.ActionResponse(
                    requestID=item.requestID,
                ),
            )

            outbox.set_action_response(client_response)

        asyncio.create_task(set_result())

        response = await outbox.put_action_and_wait_for_response(action)

        assert response is client_response
        assert action.requestID == client_response.actionResponse.requestID

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("result", "response_id_override", "expected_exception"),
        [
            (None, None, None),
            (asyncio.Future(), None, None),
            (None, "unknown-id", UnknownResponseIDException),
        ],
    )
    async def test_set_action_response(
        self,
        outbox: Outbox,
        result,
        response_id_override: str | None,
        expected_exception: type[Exception] | None,
    ):
        action = contract_pb2.Action()

        outbox.put_action(action, result=result)

        assert action.requestID in outbox._action_response

        response = contract_pb2.ClientEvent(
            actionResponse=contract_pb2.ActionResponse(requestID=action.requestID)
        )

        if response_id_override:
            response.actionResponse.requestID = response_id_override

        if expected_exception:
            with pytest.raises(expected_exception):
                outbox.set_action_response(response)
            return

        outbox.set_action_response(response)

        if result:
            assert result.result() is response

        assert action.requestID not in outbox._action_response

    @pytest.mark.asyncio
    async def test_close(self, outbox: Outbox):
        assert outbox._queue.empty()

        outbox.close()

        item = await outbox.get()

        assert item == OutboxSignal.NO_MORE_OUTBOUND_REQUESTS

    @pytest.mark.asyncio
    async def test_check_empty(self, outbox: Outbox):
        outbox.put_action(contract_pb2.Action())

        assert not outbox._queue.empty()

        with capture_logs() as cap_logs:
            outbox.check_empty()

        assert outbox._queue.empty()
        assert len(cap_logs) == 1
        assert cap_logs[0]["event"] == "Found unsent items in outbox"
