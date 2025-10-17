import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

from ai_gateway.api.middleware.entitlements import EntitlementsMiddleware
from lib.internal_events.context import EventContext


@pytest.fixture(name="mock_event_context")
def mock_event_context_fixture():
    """Create a mock EventContext for testing."""
    context = MagicMock(spec=EventContext)
    context.realm = "saas"
    context.instance_id = "4398e2e6-012d-49d9-bada-d419458fe75f"
    context.root_namespace_id = 456
    context.project_id = 789
    context.global_user_id = "user-123"
    return context


@pytest.fixture(name="entitlements_middleware")
def entitlements_middleware_fixture(mock_app):
    """Create an EntitlementsMiddleware instance for testing."""
    middleware = EntitlementsMiddleware(
        app=mock_app,
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=["/health", "/metrics"],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )
    return middleware


@pytest.mark.asyncio
async def test_skips_endpoint_in_skip_list(entitlements_middleware, mock_event_context):
    """Test that middleware skips entitlement check for endpoints in skip_endpoints list."""
    request = Request(
        {
            "type": "http",
            "path": "/health",
            "method": "GET",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_skips_metrics_endpoint(entitlements_middleware, mock_event_context):
    """Test that /metrics endpoint is skipped."""
    request = Request(
        {
            "type": "http",
            "path": "/metrics",
            "method": "GET",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_authorized_request_passes_through(
    entitlements_middleware, mock_event_context
):
    """Test that an authorized request is allowed through."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_check = AsyncMock(return_value=True)

    with (
        patch(
            "ai_gateway.api.middleware.entitlements.current_event_context"
        ) as mock_context,
        patch.object(
            entitlements_middleware, "check_consumer_entitlements", mock_check
        ),
    ):
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_not_entitled_returns_402(entitlements_middleware, mock_event_context):
    """Test that a not entitled request returns 402 status code."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_check = AsyncMock(return_value=False)

    with (
        patch(
            "ai_gateway.api.middleware.entitlements.current_event_context"
        ) as mock_context,
        patch.object(
            entitlements_middleware, "check_consumer_entitlements", mock_check
        ),
    ):
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 402
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_not_entitled_response_format(
    entitlements_middleware, mock_event_context
):
    """Test that 402 error response has correct format."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_check = AsyncMock(return_value=False)

    with (
        patch(
            "ai_gateway.api.middleware.entitlements.current_event_context"
        ) as mock_context,
        patch.object(
            entitlements_middleware, "check_consumer_entitlements", mock_check
        ),
    ):
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 402

    content = json.loads(response.body.decode())
    assert content["error"] == "not_entitled"
    assert content["error_code"] == "ENTITLEMENT_NOT_ENTITLED"
    assert "sufficient credits" in content["message"]


@pytest.mark.asyncio
async def test_dispatch_fails_open_on_timeout(
    entitlements_middleware, mock_event_context
):
    """Test that dispatch allows request when check raises timeout exception."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_check = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with (
        patch(
            "ai_gateway.api.middleware.entitlements.current_event_context"
        ) as mock_context,
        patch.object(
            entitlements_middleware, "check_consumer_entitlements", mock_check
        ),
    ):
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_dispatch_fails_open_on_server_error(
    entitlements_middleware, mock_event_context
):
    """Test that dispatch allows request when check raises server error exception."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError(
        "Internal server error", request=MagicMock(), response=mock_response
    )
    mock_check = AsyncMock(side_effect=error)

    with (
        patch(
            "ai_gateway.api.middleware.entitlements.current_event_context"
        ) as mock_context,
        patch.object(
            entitlements_middleware, "check_consumer_entitlements", mock_check
        ),
    ):
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_dispatch_fails_open_on_unexpected_error(
    entitlements_middleware, mock_event_context
):
    """Test that dispatch allows request when check raises unexpected exception."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_check = AsyncMock(side_effect=RuntimeError("Unexpected error"))

    with (
        patch(
            "ai_gateway.api.middleware.entitlements.current_event_context"
        ) as mock_context,
        patch.object(
            entitlements_middleware, "check_consumer_entitlements", mock_check
        ),
    ):
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_customersdot_success_returns_true(mock_event_context):
    """Test that CustomersDot 200 response returns True."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch(
        "ai_gateway.api.middleware.entitlements.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = await middleware.check_consumer_entitlements(mock_event_context)

    assert result is True


@pytest.mark.asyncio
async def test_customersdot_402_returns_false(mock_event_context):
    """Test that CustomersDot 402 response returns False."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    mock_response = MagicMock()
    mock_response.status_code = 402

    with patch(
        "ai_gateway.api.middleware.entitlements.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = await middleware.check_consumer_entitlements(mock_event_context)

    assert result is False


@pytest.mark.asyncio
async def test_customersdot_timeout_raises_exception(mock_event_context):
    """Test that CustomersDot timeout raises exception (to prevent caching)."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    with patch(
        "ai_gateway.api.middleware.entitlements.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.side_effect = httpx.TimeoutException("Request timeout")
        mock_client_class.return_value = mock_client

        with pytest.raises(httpx.TimeoutException):
            await middleware.check_consumer_entitlements(mock_event_context)


@pytest.mark.asyncio
async def test_customersdot_server_error_raises_exception(mock_event_context):
    """Test that CustomersDot 500 error raises exception (to prevent caching)."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError(
        "Internal server error", request=MagicMock(), response=mock_response
    )

    with patch(
        "ai_gateway.api.middleware.entitlements.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.side_effect = error
        mock_client_class.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await middleware.check_consumer_entitlements(mock_event_context)


@pytest.mark.asyncio
async def test_customersdot_unexpected_error_raises_exception(mock_event_context):
    """Test that unexpected errors raise exception (to prevent caching)."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    with patch(
        "ai_gateway.api.middleware.entitlements.httpx.AsyncClient"
    ) as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.side_effect = RuntimeError("Unexpected error")
        mock_client_class.return_value = mock_client

        with pytest.raises(RuntimeError):
            await middleware.check_consumer_entitlements(mock_event_context)
