import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import pytest_asyncio

from duo_workflow_service.gitlab.direct_http_client import DirectGitLabHttpClient


def setup_mock_response(data, status=200, content_type="application/json"):
    """
    Create a mock response object that mimics aiohttp.ClientResponse.

    Args:
        data: The response data (can be a dict or string)
        status: HTTP status code
        content_type: Response content type

    Returns:
        A MagicMock configured to behave like an aiohttp.ClientResponse
    """
    mock_response = MagicMock(spec=aiohttp.ClientResponse)
    mock_response.status = status
    mock_response.content_type = content_type

    # Set up async json method
    async def mock_json(loads=json.loads):
        if isinstance(data, str):
            return loads(data)
        return data

    mock_response.json = AsyncMock(side_effect=mock_json)

    # Set up async text method
    async def mock_text():
        if isinstance(data, str):
            return data
        return json.dumps(data)

    mock_response.text = AsyncMock(side_effect=mock_text)

    # Set up raise_for_status method
    def mock_raise_for_status():
        if status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=status
            )

    mock_response.raise_for_status = MagicMock(side_effect=mock_raise_for_status)

    # Make it work as an async context manager
    mock_response.__aenter__.return_value = mock_response
    mock_response.__aexit__.return_value = None

    return mock_response


def setup_request_mock(session_mock, response):
    """
    Replace session_mock.request with a mock that returns an async context manager
    wrapping the response.
    """
    # Create a mock for the async context manager
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = response
    mock_cm.__aexit__.return_value = None

    # Create a mock for the request method
    mock_request = MagicMock()
    mock_request.return_value = mock_cm

    # Replace the session's request method
    session_mock.request = mock_request


@pytest.fixture
def mock_session():
    with patch.object(
        DirectGitLabHttpClient, "_session", new_callable=AsyncMock
    ) as mock_session:
        mock_session.request = AsyncMock()
        yield mock_session


@pytest_asyncio.fixture
async def client():
    # Patching to avoid actual network connections during tests
    with patch.object(DirectGitLabHttpClient, "_session", None):
        # Create an instance of client with a mock URL
        client = DirectGitLabHttpClient(
            base_url="https://gitlab.example.com/api/v4", gitlab_token="test_token"
        )

        # Patch the initialize_pool method to avoid real network connections
        with patch(
            "aiohttp.ClientSession", new_callable=AsyncMock
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session.close = AsyncMock()
            mock_session.request = AsyncMock()
            mock_session_class.return_value = mock_session

            # Initialize pool but use our mock session
            await DirectGitLabHttpClient.initialize_pool()
            DirectGitLabHttpClient._session = mock_session

            yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path, body, params, parse_json, response_data, expected_result",
    [
        ("GET", "projects/1", None, None, True, {"key": "value"}, {"key": "value"}),
        (
            "GET",
            "projects/1/jobs/102/trace",
            None,
            None,
            False,
            "Non-JSON response",
            "Non-JSON response",
        ),
        (
            "GET",
            "projects",
            None,
            {"per_page": 100},
            True,
            {"projects": []},
            {"projects": []},
        ),
        (
            "POST",
            "test",
            '{ "test": 1 }',
            None,
            True,
            {"key": "value"},
            {"key": "value"},
        ),
        (
            "PUT",
            "test",
            '{ "test": 1 }',
            None,
            True,
            {"key": "value"},
            {"key": "value"},
        ),
        (
            "PATCH",
            "test",
            '{ "test": 1 }',
            None,
            True,
            {"key": "value"},
            {"key": "value"},
        ),
    ],
)
async def test_direct_gitlab_http_client(
    client,
    method,
    path,
    body,
    params,
    parse_json,
    response_data,
    expected_result,
):
    # Get the internal mock session
    mock_session = client._session

    # Setup the mock response
    mock_response = setup_mock_response(response_data)
    setup_request_mock(mock_session, mock_response)

    # Make the API call
    if method == "GET":
        result = await client.aget(path, params=params, parse_json=parse_json)
    elif method == "POST":
        result = await client.apost(path, body, parse_json=parse_json)
    elif method == "PUT":
        result = await client.aput(path, body, parse_json=parse_json)
    elif method == "PATCH":
        result = await client.apatch(path, body, parse_json=parse_json)
    else:
        pytest.fail(f"Unexpected HTTP method: {method}")
        result = None

    # Check that the session was called with the correct parameters
    expected_url = f"{client.base_url}/{path}"
    expected_headers = {
        "Authorization": f"Bearer {client.gitlab_token}",
        "Content-Type": "application/json",
    }

    expected_kwargs = {}
    if params:
        expected_kwargs["params"] = params
    if body:
        expected_kwargs["data"] = body

    mock_session.request.assert_called_once_with(
        method, expected_url, headers=expected_headers, **expected_kwargs
    )

    # Check the result
    assert result == expected_result


@pytest.mark.asyncio
async def test_direct_gitlab_http_client_with_object_hook(client):
    # Create a test JSON response
    json_response = '{"nested": {"id": 1}}'

    # Get the internal mock session
    mock_session = client._session

    # Setup the mock response
    mock_response = setup_mock_response(json_response)
    setup_request_mock(mock_session, mock_response)

    # Define a custom object hook function
    def custom_hook(obj):
        if "id" in obj:
            obj["id"] = f"custom-{obj['id']}"
        return obj

    # Make the API call with the object hook
    result = await client.aget("test", parse_json=True, object_hook=custom_hook)

    # Verify the object hook was applied
    assert result["nested"]["id"] == "custom-1"


@pytest.mark.asyncio
async def test_direct_gitlab_http_client_initialize_close_pool():
    DirectGitLabHttpClient._session = None

    # Patch ClientSession to avoid real network connections
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session_class.return_value = mock_session

        # Initialize the pool
        await DirectGitLabHttpClient.initialize_pool(pool_size=50)

        # Check that the session was created
        assert DirectGitLabHttpClient._session is not None
        mock_session_class.assert_called_once()

        # Close the pool
        await DirectGitLabHttpClient.close_pool()

        # Check that the session was closed
        mock_session.close.assert_called_once()
        assert DirectGitLabHttpClient._session is None


@pytest.mark.asyncio
async def test_direct_gitlab_http_client_uninitialized_pool():
    # Start with no session
    DirectGitLabHttpClient._session = None

    # Create a client
    client = DirectGitLabHttpClient(
        base_url="https://gitlab.example.com/api/v4", gitlab_token="test_token"
    )

    # Try to make a request without initializing the pool
    with pytest.raises(
        RuntimeError, match="HTTP client connection pool is not initialized"
    ):
        await client.aget("test")


@pytest.mark.asyncio
async def test_direct_gitlab_http_client_invalid_json():
    DirectGitLabHttpClient._session = None

    # Create a client
    client = DirectGitLabHttpClient(
        base_url="https://gitlab.example.com/api/v4", gitlab_token="test_token"
    )

    # Create an invalid JSON response
    invalid_json_response = "Invalid JSON {not valid}"

    # Get the internal mock session
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_response = setup_mock_response(
            invalid_json_response, content_type="application/json"
        )
        setup_request_mock(mock_session, mock_response)
        mock_session_class.return_value = mock_session

        # Initialize the pool properly
        await DirectGitLabHttpClient.initialize_pool()
        DirectGitLabHttpClient._session = mock_session

        try:
            # Make the request - it should return the raw text instead of raising an error
            result = await client.aget("test", parse_json=True)

            # Verify we got back the raw text
            assert result == invalid_json_response
        finally:
            # Clean up
            await DirectGitLabHttpClient.close_pool()
