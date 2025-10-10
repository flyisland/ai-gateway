import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ai_gateway.api.middleware.entitlements import (
    CachedEntitlementDecision,
    EntitlementCheckResult,
    EntitlementDecision,
    EntitlementsMiddleware,
)
from lib.internal_events.context import EventContext


@pytest.fixture(name="mock_event_context")
def mock_event_context_fixture():
    """Create a mock EventContext with a to_cache_key method."""
    context = MagicMock(spec=EventContext)
    context.realm = "saas"
    context.instance_id = "4398e2e6-012d-49d9-bada-d419458fe75f"
    context.namespace_id = 456
    context.project_id = 789
    context.global_user_id = "user-123"
    context.to_cache_key.return_value = "test-cache-key-123"
    context.model_dump.return_value = {
        "realm": "saas",
        "instance_id": "4398e2e6-012d-49d9-bada-d419458fe75f",
        "namespace_id": 456,
        "project_id": 789,
        "global_user_id": "user-123",
    }
    return context


@pytest.fixture(name="entitlements_middleware")
def entitlements_middleware_fixture():
    """Create an EntitlementsMiddleware instance for testing."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=["/health", "/metrics"],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )
    return middleware


@pytest.fixture(name="mock_http_client")
def mock_http_client_fixture():
    """Create a mock httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


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
    mock_event_context.to_cache_key.assert_not_called()


@pytest.mark.asyncio
async def test_cache_hit_authorized(entitlements_middleware, mock_event_context):
    """Test that cached authorized decision allows request through."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    entitlements_middleware.entitlements_cache.set(
        "test-cache-key-123", CachedEntitlementDecision(authorized=True)
    )

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)
    mock_event_context.to_cache_key.assert_called_once()


@pytest.mark.asyncio
async def test_cache_hit_not_entitled(entitlements_middleware, mock_event_context):
    """Test that cached not_entitled decision returns 402."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    entitlements_middleware.entitlements_cache.set(
        "test-cache-key-123", CachedEntitlementDecision(authorized=False)
    )

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 402
    assert isinstance(response, JSONResponse)
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_customersdot_returns_200(
    entitlements_middleware, mock_event_context, mock_http_client
):
    """Test that CustomersDot 200 response caches authorized decision and allows request."""
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
    mock_response.status_code = 200
    mock_http_client.head.return_value = mock_response
    entitlements_middleware.http_client = mock_http_client

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)

    mock_http_client.head.assert_called_once_with(
        "https://customers.gitlab.local/api/v1/consumers/resolve",
        params=mock_event_context.model_dump.return_value,
    )

    cached_decision = entitlements_middleware.entitlements_cache.get(
        "test-cache-key-123"
    )
    assert cached_decision is not None
    assert cached_decision.authorized is True


@pytest.mark.asyncio
async def test_cache_miss_customersdot_returns_non_200(
    entitlements_middleware, mock_event_context, mock_http_client
):
    """Test that CustomersDot non-200 response caches not_entitled decision and returns 402."""
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
    mock_response.status_code = 402
    mock_http_client.head.return_value = mock_response
    entitlements_middleware.http_client = mock_http_client

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 402
    call_next.assert_not_called()

    cached_decision = entitlements_middleware.entitlements_cache.get(
        "test-cache-key-123"
    )
    assert cached_decision is not None
    assert cached_decision.authorized is False


@pytest.mark.asyncio
async def test_customersdot_timeout_falls_back_to_error_fallback(
    entitlements_middleware, mock_event_context, mock_http_client
):
    """Test that CustomersDot timeout results in ERROR_FALLBACK (fail-open)."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_http_client.head.side_effect = httpx.TimeoutException("Request timeout")
    entitlements_middleware.http_client = mock_http_client

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)

    cached_decision = entitlements_middleware.entitlements_cache.get(
        "test-cache-key-123"
    )
    assert cached_decision is None


@pytest.mark.asyncio
async def test_customersdot_http_status_error_402_returns_not_entitled(
    entitlements_middleware, mock_event_context, mock_http_client
):
    """Test that CustomersDot 402 HTTPStatusError returns NOT_ENTITLED and caches decision."""
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
    mock_response.status_code = 402
    error = httpx.HTTPStatusError(
        "Payment required", request=MagicMock(), response=mock_response
    )
    mock_http_client.head.side_effect = error
    entitlements_middleware.http_client = mock_http_client

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 402
    call_next.assert_not_called()

    cached_decision = entitlements_middleware.entitlements_cache.get(
        "test-cache-key-123"
    )
    assert cached_decision is not None
    assert cached_decision.authorized is False


@pytest.mark.asyncio
async def test_customersdot_http_status_error_500_falls_back_to_authorized(
    entitlements_middleware, mock_event_context, mock_http_client
):
    """Test that CustomersDot 500 HTTPStatusError falls back to AUTHORIZED (fail-open)."""
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
    mock_http_client.head.side_effect = error
    entitlements_middleware.http_client = mock_http_client

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)

    cached_decision = entitlements_middleware.entitlements_cache.get(
        "test-cache-key-123"
    )
    assert cached_decision is None


@pytest.mark.asyncio
async def test_customersdot_unexpected_error_falls_back_to_authorized(
    entitlements_middleware, mock_event_context, mock_http_client
):
    """Test that unexpected errors fall back to AUTHORIZED (fail-open)."""
    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_http_client.head.side_effect = Exception("Unexpected error")
    entitlements_middleware.http_client = mock_http_client

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context:
        mock_context.get.return_value = mock_event_context
        response = await entitlements_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)

    cached_decision = entitlements_middleware.entitlements_cache.get(
        "test-cache-key-123"
    )
    assert cached_decision is None


@pytest.mark.asyncio
async def test_not_entitled_response_content_format():
    """Test that 402 error response has correct format."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
    )

    request = Request(
        {
            "type": "http",
            "path": "/api/v1/chat",
            "method": "POST",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    mock_context = MagicMock(spec=EventContext)
    mock_context.to_cache_key.return_value = "test-key"

    middleware.entitlements_cache.set(
        "test-key", CachedEntitlementDecision(authorized=False)
    )

    with patch(
        "ai_gateway.api.middleware.entitlements.current_event_context"
    ) as mock_context_var:
        mock_context_var.get.return_value = mock_context
        response = await middleware.dispatch(request, call_next)

    assert response.status_code == 402
    assert isinstance(response, JSONResponse)

    content = json.loads(response.body.decode())

    assert content["error"] == "not_entitled"
    assert content["error_code"] == "ENTITLEMENT_NOT_ENTITLED"
    assert "sufficient credits" in content["message"]


@pytest.mark.asyncio
async def test_cache_stores_multiple_decisions():
    """Test that cache can store multiple independent decisions."""
    middleware = EntitlementsMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
    )

    authorized_context = MagicMock(spec=EventContext)
    authorized_context.to_cache_key.return_value = "key1"
    authorized_context.model_dump.return_value = {"namespace_id": 1}

    not_entitled_context = MagicMock(spec=EventContext)
    not_entitled_context.to_cache_key.return_value = "key2"
    not_entitled_context.model_dump.return_value = {"namespace_id": 2}

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response_authorized = MagicMock()
    mock_response_authorized.status_code = 200
    mock_response_not_entitled = MagicMock()
    mock_response_not_entitled.status_code = 402

    middleware.http_client = mock_http_client

    mock_http_client.head.return_value = mock_response_authorized
    authorized_request = await middleware.check_consumer_entitlements(
        authorized_context
    )
    assert authorized_request.decision == EntitlementDecision.AUTHORIZED

    mock_http_client.head.return_value = mock_response_not_entitled
    not_entitled_request = await middleware.check_consumer_entitlements(
        not_entitled_context
    )
    assert not_entitled_request.decision == EntitlementDecision.NOT_ENTITLED

    cached_response_for_request_one = middleware.entitlements_cache.get("key1")
    cached_response_for_request_two = middleware.entitlements_cache.get("key2")

    assert cached_response_for_request_one is not None
    assert cached_response_for_request_one.authorized is True

    assert cached_response_for_request_two is not None
    assert cached_response_for_request_two.authorized is False
