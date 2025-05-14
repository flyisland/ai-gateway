import uuid
from contextvars import ContextVar

import grpc
from fastapi import WebSocket

from duo_workflow_service.interceptors.websocket_middleware import WebSocketMiddleware

# Context variables to store correlation ID and user ID
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="undefined")
gitlab_global_user_id: ContextVar[str] = ContextVar(
    "gitlab_global_user_id", default="undefined"
)

CORRELATION_ID_KEY = "x-request-id"
X_GITLAB_GLOBAL_USER_ID_HEADER = "x-gitlab-global-user-id"


class CorrelationIdInterceptor(grpc.aio.ServerInterceptor):
    """Interceptor that handles correlation ID injection and propagation."""

    CORRELATION_ID_KEY = "x-request-id"
    X_GITLAB_GLOBAL_USER_ID_HEADER = "x-gitlab-global-user-id"

    def __init__(self):
        pass

    async def intercept_service(
        self,
        continuation,
        handler_call_details,
    ):
        """Intercept incoming requests to inject correlation ID."""
        metadata = dict(handler_call_details.invocation_metadata)

        # Extract correlation ID from metadata or generate new one
        request_id = metadata.get(CORRELATION_ID_KEY, str(uuid.uuid4()))

        # Set correlation ID in context
        correlation_id.set(request_id)
        gitlab_global_user_id.set(
            metadata.get(X_GITLAB_GLOBAL_USER_ID_HEADER, "undefined")
        )

        return await continuation(handler_call_details)


class CorrelationIdMiddleware(WebSocketMiddleware):
    """Middleware for handling correlation IDs."""

    async def __call__(
        self,
        websocket: WebSocket,
    ):
        request_id = websocket.headers.get(CORRELATION_ID_KEY)
        user_id = websocket.headers.get(X_GITLAB_GLOBAL_USER_ID_HEADER)

        if request_id is None:
            request_id = str(uuid.uuid4())

        if user_id is None:
            user_id = "undefined"

        # Set correlation ID in context
        correlation_id.set(request_id)
        gitlab_global_user_id.set(user_id)
