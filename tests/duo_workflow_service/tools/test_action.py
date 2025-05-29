import pytest

from unittest.mock import AsyncMock, MagicMock
from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action


@pytest.mark.asyncio
async def test_execute_action_success():
    executor_client = MagicMock()
    executor_client.request = AsyncMock(
        return_value=contract_pb2.ClientEvent(
            actionResponse=contract_pb2.ActionResponse(response="expected_response")
        )
    )
    metadata = {"executor_client": executor_client}

    action = contract_pb2.Action()
    expected_response = "expected_response"
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = expected_response

    response = await _execute_action(metadata, action)

    assert response == expected_response
