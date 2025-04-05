from unittest.mock import AsyncMock, patch

import pytest
from gitlab_cloud_connector import X_GITLAB_DUO_SEAT_COUNT_HEADER
from starlette.requests import Request
from starlette_context import context, request_cycle_context

from ai_gateway.api.middleware import (
    X_GITLAB_CLIENT_NAME,
    X_GITLAB_CLIENT_TYPE,
    X_GITLAB_CLIENT_VERSION,
    X_GITLAB_FEATURE_ENABLED_BY_NAMESPACE_IDS_HEADER,
    X_GITLAB_FEATURE_ENABLEMENT_TYPE_HEADER,
    X_GITLAB_GLOBAL_USER_ID_HEADER,
    X_GITLAB_HOST_NAME_HEADER,
    X_GITLAB_INSTANCE_ID_HEADER,
    X_GITLAB_INTERFACE,
    X_GITLAB_REALM_HEADER,
    X_GITLAB_SAAS_DUO_PRO_NAMESPACE_IDS_HEADER,
    X_GITLAB_TEAM_MEMBER_HEADER,
    X_GITLAB_VERSION_HEADER,
    DistributedTraceMiddleware,
)
from ai_gateway.internal_events import EventContext


@pytest.fixture
def distributed_trace_middleware(mock_app):
    return DistributedTraceMiddleware(
        mock_app, skip_endpoints=["/health"], environment="development"
    )


@pytest.mark.asyncio
async def test_middleware_distributed_trace(distributed_trace_middleware):
    current_run_id = "20240808T090953171943Z18dfa1db-1dfc-4a48-aaf8-a139960955ce"
    request = Request(
        {
            "type": "http",
            "path": "/api/endpoint",
            "headers": [
                (b"langsmith-trace", current_run_id.encode()),
            ],
        }
    )
    scope = request.scope
    receive = AsyncMock()
    send = AsyncMock()

    with patch(
        "ai_gateway.api.middleware.base.tracing_context"
    ) as mock_tracing_context:
        await distributed_trace_middleware(scope, receive, send)

        mock_tracing_context.assert_called_once_with(parent=current_run_id)

    distributed_trace_middleware.app.assert_called_once_with(scope, receive, send)
