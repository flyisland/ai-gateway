import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import pytest_asyncio

from duo_workflow_service.gitlab.direct_http_client import DirectGitLabHttpClient


class MockRequestContextManager:
    def __init__(self, response):
        self._response = response

    def __await__(self):
        async def _coro():
            return self._response

        return _coro().__await__()

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def setup_request_mock(session_mock, response):
    """
    Replace session_mock.request with a MagicMock that, when called,
    returns a MockRequestContextManager wrapping *response*.
    """
    from unittest.mock import MagicMock

    session_mock.request = MagicMock(
        side_effect=lambda *a, **kw: MockRequestContextManager(response)
    )


class MockResponse:
    def __init__(self, data, status=200, content_type="application/json"):
        self.data = data
        self.status = status
        self.content_type = content_type
        self._body = None

    async def json(self, loads=json.loads):
        if isinstance(self.data, str):
            return loads(self.data)
        return self.data

    async def text(self):
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=self.status
            )


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
    mock_response = MockResponse(response_data)
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
    mock_response = MockResponse(json_response)
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
async def test_direct_gitlab_http_client_http_error():
    DirectGitLabHttpClient._session = None

    # Create a client
    client = DirectGitLabHttpClient(
        base_url="https://gitlab.example.com/api/v4", gitlab_token="test_token"
    )

    # Patch ClientSession to avoid network connections
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session.request = AsyncMock()

        # Setup a response with an error status
        error_response = MockResponse({"error": "Not found"}, status=404)
        mock_session.request.return_value = error_response
        mock_session_class.return_value = mock_session
        setup_request_mock(mock_session, error_response)

        # Initialize the pool manually to use our mock
        DirectGitLabHttpClient._session = mock_session

        # Make a request that will cause an error
        with pytest.raises(aiohttp.ClientResponseError) as excinfo:
            await client.aget("nonexistent")

        # Verify the error status
        assert excinfo.value.status == 404

        # Clean up
        await DirectGitLabHttpClient.close_pool()
