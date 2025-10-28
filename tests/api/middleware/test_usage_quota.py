import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

from ai_gateway.api.middleware.usage_quota import UsageQuotaMiddleware
from lib.feature_flags import FeatureFlag
from lib.internal_events.context import EventContext


@pytest.fixture(name="mock_event_context")
def mock_event_context_fixture():
    """Create a mock EventContext using CDOT_RESOLVE_PARAM_KEYS and default values."""
    ctx = MagicMock(spec=EventContext)

    ctx.environment = "test"
    ctx.source = "duo_chat"
    ctx.realm = "saas"
    ctx.instance_id = "4398e2e6-012d-49d9-bada-d419458fe75f"
    ctx.unique_instance_id = None
    ctx.feature_enablement_type = "duo_pro"
    ctx.host_name = "gitlab.local"
    ctx.instance_version = "17.5.0"
    ctx.global_user_id = "user-123"
    ctx.user_id = None
    ctx.project_id = 789
    ctx.namespace_id = 456

    # Dynamically build model_dump return value based on CDOT_RESOLVE_PARAM_KEYS
    ctx.model_dump.return_value = {
        k: getattr(ctx, k) for k in UsageQuotaMiddleware.CDOT_RESOLVE_PARAM_KEYS
    }

    return ctx


@pytest.fixture(name="usage_quota_middleware")
def usage_quota_middleware_fixture(mock_app):
    """Create an UsageQuotaMiddleware instance for testing."""
    middleware = UsageQuotaMiddleware(
        app=mock_app,
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=["/health", "/metrics"],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )
    return middleware


@pytest.mark.asyncio
async def test_skips_endpoint_in_skip_list(usage_quota_middleware, mock_event_context):
    """Test that middleware skips usage quota check for endpoints in skip_endpoints list."""
    request = Request(
        {
            "type": "http",
            "path": "/health",
            "method": "GET",
            "headers": [],
        }
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
    ):
        mock_ff.return_value = True
        mock_ctx.get.return_value = mock_event_context
        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_skips_metrics_endpoint(usage_quota_middleware, mock_event_context):
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

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
    ):
        mock_ff.return_value = True
        mock_ctx.get.return_value = mock_event_context
        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_feature_flag_disabled_skips_usage_quota_check(
    usage_quota_middleware, mock_event_context
):
    """Test that middleware skips usage quota check when feature flag is disabled."""
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
        patch.object(
            usage_quota_middleware,
            "has_usage_quota_left",
            new_callable=AsyncMock,
        ) as mock_check,
    ):
        mock_ctx.get.return_value = mock_event_context
        mock_ff.return_value = False

        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)
    mock_check.assert_not_called()
    mock_ff.assert_called_once_with(FeatureFlag.USAGE_QUOTA_LEFT_CHECK)


@pytest.mark.asyncio
async def test_feature_flag_enabled_performs_usage_quota_check(
    usage_quota_middleware, mock_event_context
):
    """Test that middleware performs usage quota check when feature flag is enabled."""
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))
    mock_check = AsyncMock(return_value=True)

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
        patch.object(usage_quota_middleware, "has_usage_quota_left", mock_check),
    ):
        mock_ctx.get.return_value = mock_event_context
        mock_ff.return_value = True

        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)
    mock_check.assert_called_once_with(mock_event_context)
    mock_ff.assert_called_once_with(FeatureFlag.USAGE_QUOTA_LEFT_CHECK)


@pytest.mark.asyncio
async def test_middleware_disabled_skips_usage_quota_check(
    mock_event_context, mock_app
):
    """Test that middleware skips usage quota check when middleware is disabled."""
    middleware = UsageQuotaMiddleware(
        app=mock_app,
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=False,  # disabled
        environment="test",
        request_timeout=1.0,
    )
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
    ):
        mock_ctx.get.return_value = mock_event_context
        mock_ff.return_value = True  # even if FF is on, middleware disabled → skip
        response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_authorized_request_passes_through(
    usage_quota_middleware, mock_event_context
):
    """Test that an authorized request is allowed through."""
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))
    mock_check = AsyncMock(return_value=True)

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
        patch.object(usage_quota_middleware, "has_usage_quota_left", mock_check),
    ):
        mock_ff.return_value = True
        mock_ctx.get.return_value = mock_event_context
        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_no_usage_quota_left_returns_402(
    usage_quota_middleware, mock_event_context
):
    """Test that a usage_quota left request returns 402 status code."""
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))
    mock_check = AsyncMock(return_value=False)

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
        patch.object(usage_quota_middleware, "has_usage_quota_left", mock_check),
    ):
        mock_ff.return_value = True
        mock_ctx.get.return_value = mock_event_context
        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 402
    call_next.assert_not_called()


@pytest.mark.asyncio
async def test_no_usage_quota_left_response_format(
    usage_quota_middleware, mock_event_context
):
    """Test that 402 error response has correct JSON format."""
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))
    mock_check = AsyncMock(return_value=False)

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
        patch.object(usage_quota_middleware, "has_usage_quota_left", mock_check),
    ):
        mock_ff.return_value = True
        mock_ctx.get.return_value = mock_event_context
        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 402
    content = json.loads(response.body.decode())
    assert content["error"] == "insufficient_credits"
    assert content["error_code"] == "USAGE_QUOTA_EXCEEDED"
    assert "sufficient credits" in content["message"]


@pytest.mark.asyncio
async def test_dispatch_fails_open_on_timeout(
    usage_quota_middleware, mock_event_context
):
    """Test that dispatch allows request when timeout occurs (fail-open)."""
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))
    mock_check = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
        patch.object(usage_quota_middleware, "has_usage_quota_left", mock_check),
    ):
        mock_ff.return_value = True
        mock_ctx.get.return_value = mock_event_context
        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_dispatch_fails_open_on_unexpected_error(
    usage_quota_middleware, mock_event_context
):
    """Test that dispatch allows request when unexpected exception occurs."""
    request = Request(
        {"type": "http", "path": "/api/v1/chat", "method": "POST", "headers": []}
    )
    call_next = AsyncMock(return_value=Response(status_code=200))
    mock_check = AsyncMock(side_effect=RuntimeError("Unexpected error"))

    with (
        patch(
            "ai_gateway.api.middleware.usage_quota.current_event_context"
        ) as mock_ctx,
        patch("ai_gateway.api.middleware.usage_quota.is_feature_enabled") as mock_ff,
        patch.object(usage_quota_middleware, "has_usage_quota_left", mock_check),
    ):
        mock_ff.return_value = True
        mock_ctx.get.return_value = mock_event_context
        response = await usage_quota_middleware.dispatch(request, call_next)

    assert response.status_code == 200
    call_next.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_customersdot_success_returns_true(mock_event_context):
    """Test that CustomersDot 200 response returns True (entitled)."""
    middleware = UsageQuotaMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    mock_response = MagicMock(status_code=200)
    with patch(
        "ai_gateway.api.middleware.usage_quota.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = await middleware.has_usage_quota_left(mock_event_context)

    assert result is True


@pytest.mark.parametrize("status", [401, 402, 403])
@pytest.mark.asyncio
async def test_customersdot_denied_status_returns_false(mock_event_context, status):
    """Test that CustomersDot 401/402/403 responses return False (not entitled)."""
    UsageQuotaMiddleware.has_usage_quota_left.cache.clear()

    middleware = UsageQuotaMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    mock_response = MagicMock(status_code=status)

    with patch(
        "ai_gateway.api.middleware.usage_quota.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = await middleware.has_usage_quota_left(mock_event_context)
        assert result is False

    UsageQuotaMiddleware.has_usage_quota_left.cache.clear()


@pytest.mark.asyncio
async def test_customersdot_timeout_raises_exception(mock_event_context):
    """Test that CustomersDot timeout raises TimeoutException (prevent caching)."""
    middleware = UsageQuotaMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    with patch(
        "ai_gateway.api.middleware.usage_quota.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.side_effect = httpx.TimeoutException("timeout")
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.TimeoutException):
            await middleware.has_usage_quota_left(mock_event_context)


@pytest.mark.asyncio
async def test_customersdot_unexpected_error_raises_exception(mock_event_context):
    """Test that unexpected error in CustomersDot call raises Exception."""
    middleware = UsageQuotaMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    with patch(
        "ai_gateway.api.middleware.usage_quota.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.side_effect = RuntimeError("Unexpected error")
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError):
            await middleware.has_usage_quota_left(mock_event_context)


@pytest.mark.asyncio
async def test_customersdot_sends_params_as_dict(mock_event_context):
    middleware = UsageQuotaMiddleware(
        app=AsyncMock(),
        customersdot_url="https://customers.gitlab.local",
        skip_endpoints=[],
        enabled=True,
        environment="test",
        request_timeout=1.0,
    )

    with patch(
        "ai_gateway.api.middleware.usage_quota.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.head.return_value = MagicMock(status_code=200)
        mock_client_cls.return_value = mock_client

        await middleware.has_usage_quota_left(mock_event_context)

        _, kwargs = mock_client.head.call_args
        params = kwargs.get("params")

        assert isinstance(params, dict)
        missing = UsageQuotaMiddleware.CDOT_RESOLVE_PARAM_KEYS - params.keys()
        assert not missing, f"Missing expected params: {missing}"
