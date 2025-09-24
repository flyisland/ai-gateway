import asyncio

import pytest
from langchain_core.tools import ToolException

from contract import contract_pb2
from duo_workflow_service.executor.action import (
    HTTPConnectionError,
    _execute_action,
    _execute_action_and_get_action_response,
    _execute_action_and_get_http_response,
)


@pytest.fixture
def metadata():
    outbox = asyncio.Queue()
    inbox = asyncio.Queue()
    return {"outbox": outbox, "inbox": inbox}


@pytest.mark.asyncio
async def test_execute_action_success_http_response(metadata):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()

    # Set up HTTP response without error
    client_event.actionResponse.httpResponse.statusCode = 200
    client_event.actionResponse.httpResponse.body = '{"result": "success"}'
    client_event.actionResponse.httpResponse.error = ""

    await metadata["inbox"].put(client_event)

    response = await _execute_action(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert response == '{"result": "success"}'
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test_execute_action_success_plaintext_response(metadata):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()

    # Set up plaintext response without error
    client_event.actionResponse.plainTextResponse.response = "plaintext success"
    client_event.actionResponse.plainTextResponse.error = ""

    await metadata["inbox"].put(client_event)

    response = await _execute_action(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert response == "plaintext success"
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test__execute_action_and_get_action_response_http_error_raises_tool_exception(
    metadata,
):
    """Test that HTTP errors in _execute_action_and_get_action_response raise ToolException."""
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()

    # Set up HTTP response with error
    client_event.actionResponse.httpResponse.error = "Connection timeout"

    await metadata["inbox"].put(client_event)

    with pytest.raises(ToolException, match="HTTP action error: Connection timeout"):
        await _execute_action_and_get_action_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test__execute_action_and_get_action_response_plaintext_error_raises_tool_exception(
    metadata,
):
    """Test that plaintext errors in _execute_action_and_get_action_response raise ToolException."""
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()

    # Set up plaintext response with error
    client_event.actionResponse.plainTextResponse.error = "File not found"

    await metadata["inbox"].put(client_event)

    with pytest.raises(ToolException, match="Action error: File not found"):
        await _execute_action_and_get_action_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test_execute_action_empty_inbox(metadata):
    action = contract_pb2.Action()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_execute_action(metadata, action), timeout=1.0)


@pytest.mark.asyncio
async def test_execute_action_and_get_http_response_success(metadata):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = "success"

    # Create httpResponse with no error
    client_event.actionResponse.httpResponse.statusCode = 200
    client_event.actionResponse.httpResponse.body = '{"result": "ok"}'
    client_event.actionResponse.httpResponse.error = ""

    await metadata["inbox"].put(client_event)

    response = await _execute_action_and_get_http_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert response.response == "success"
    assert response.httpResponse.statusCode == 200
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test_execute_action_and_get_http_response_connection_error(metadata):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = "failed"

    # Create httpResponse with error
    client_event.actionResponse.httpResponse.error = "Connection refused"

    await metadata["inbox"].put(client_event)

    # This should raise ToolException from _execute_action_and_get_action_response first
    with pytest.raises(ToolException, match="HTTP action error: Connection refused"):
        await _execute_action_and_get_http_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test__execute_action_and_get_action_response_missing_legacy_response_from_http_success(
    metadata,
):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = ""

    client_event.actionResponse.httpResponse.statusCode = 200
    client_event.actionResponse.httpResponse.body = '{"result": "ok"}'
    client_event.actionResponse.httpResponse.error = ""

    await metadata["inbox"].put(client_event)

    response = await _execute_action_and_get_action_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()

    assert put_action == action
    assert response.response == '{"result": "ok"}'
    assert response.httpResponse.statusCode == 200
    assert response.httpResponse.body == '{"result": "ok"}'
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test__execute_action_and_get_action_response_missing_legacy_response_from_http_not_found(
    metadata,
):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = ""

    client_event.actionResponse.httpResponse.statusCode = 404
    client_event.actionResponse.httpResponse.body = ""
    client_event.actionResponse.httpResponse.error = ""

    await metadata["inbox"].put(client_event)

    response = await _execute_action_and_get_action_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()

    assert put_action == action
    assert response.response == "Error: unexpected status code: 404"
    assert response.httpResponse.statusCode == 404
    assert response.httpResponse.body == ""
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test__execute_action_and_get_action_response_missing_legacy_response_from_http_error(
    metadata,
):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = ""

    client_event.actionResponse.httpResponse.statusCode = 0
    client_event.actionResponse.httpResponse.body = ""
    client_event.actionResponse.httpResponse.error = "Some HTTP error"

    await metadata["inbox"].put(client_event)

    # This should now raise ToolException instead of returning a response
    with pytest.raises(ToolException, match="HTTP action error: Some HTTP error"):
        await _execute_action_and_get_action_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test__execute_action_and_get_action_response_missing_legacy_response_from_plaintext(
    metadata,
):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = ""

    client_event.actionResponse.plainTextResponse.response = "Response"
    client_event.actionResponse.plainTextResponse.error = ""

    await metadata["inbox"].put(client_event)

    response = await _execute_action_and_get_action_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()

    assert put_action == action
    assert response.response == "Response"
    assert response.plainTextResponse.response == "Response"
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test__execute_action_and_get_action_response_missing_legacy_response_from_plaintext_error(
    metadata,
):
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()
    client_event.actionResponse.response = ""

    client_event.actionResponse.plainTextResponse.response = ""
    client_event.actionResponse.plainTextResponse.error = "file not found"

    await metadata["inbox"].put(client_event)

    # This should now raise ToolException instead of returning a response
    with pytest.raises(ToolException, match="Action error: file not found"):
        await _execute_action_and_get_action_response(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert metadata["inbox"].empty()


@pytest.mark.asyncio
async def test_execute_action_unknown_response_type(metadata):
    """Test that _execute_action raises ValueError for unknown response_type."""
    action = contract_pb2.Action()
    client_event = contract_pb2.ClientEvent()

    # Set up an ActionResponse with no response_type set (neither plainTextResponse nor httpResponse)
    client_event.actionResponse.response = "some response"
    # Don't set either plainTextResponse or httpResponse, so WhichOneof("response_type") returns None

    await metadata["inbox"].put(client_event)

    with pytest.raises(ValueError, match="Unexpected response type: None"):
        await _execute_action(metadata, action)

    put_action = await metadata["outbox"].get()
    metadata["outbox"].task_done()
    assert put_action == action
    assert metadata["inbox"].empty()
