# pylint: disable=direct-environment-variable-reference

import contextvars
import os
from typing import Callable, Dict, Optional

import grpc
import structlog
from fastapi import WebSocket
from gitlab_cloud_connector import (
    AuthProvider,
    CloudConnectorAuthError,
    CompositeProvider,
    GitLabOidcProvider,
    LocalAuthProvider,
    authenticate,
)
from grpc.aio import ServicerContext

from duo_workflow_service.interceptors.websocket_middleware import WebSocketMiddleware

current_user: contextvars.ContextVar = contextvars.ContextVar("current_user")

AUTH_ENABLED_ENV_VAR = "DUO_WORKFLOW_AUTH__ENABLED"
AUTH_OIDC_GITLAB_URL_ENV_VAR = "DUO_WORKFLOW_AUTH__OIDC_GITLAB_URL"
AUTH_OIDC_CUSTOMER_PORTAL_URL_ENV_VAR = "DUO_WORKFLOW_AUTH__OIDC_CUSTOMER_PORTAL_URL"
AUTH_SIGNING_KEY_ENV_VAR = "DUO_WORKFLOW_SELF_SIGNED_JWT__SIGNING_KEY"
AUTH_VALIDATION_KEY_ENV_VAR = "DUO_WORKFLOW_SELF_SIGNED_JWT__VALIDATION_KEY"


class AuthenticationError(Exception):
    pass


def _is_auth_enabled() -> bool:
    """Check if authentication is enabled based on environment variable."""
    return os.environ.get(AUTH_ENABLED_ENV_VAR, "true").lower() != "false"


def _skip_auth():
    structlog.get_logger().warning("Auth is disabled, all users allowed")
    cloud_connector_user, _ = authenticate({}, None, bypass_auth=True)
    current_user.set(cloud_connector_user)


def _oidc_auth_provider() -> AuthProvider:
    """Create and return an OIDC authentication provider."""
    gitlab_url: str = os.environ.get(AUTH_OIDC_GITLAB_URL_ENV_VAR, "https://gitlab.com")
    customer_portal_url: str = os.environ.get(
        AUTH_OIDC_CUSTOMER_PORTAL_URL_ENV_VAR,
        "https://customers.gitlab.com",
    )
    signing_key: str = os.environ.get(AUTH_SIGNING_KEY_ENV_VAR, "")
    validation_key: str = os.environ.get(AUTH_VALIDATION_KEY_ENV_VAR, "")

    return CompositeProvider(
        [
            LocalAuthProvider(structlog, signing_key, validation_key),
            GitLabOidcProvider(
                structlog,
                oidc_providers={
                    "Gitlab": gitlab_url,
                    "CustomersDot": customer_portal_url,
                },
            ),
        ],
        structlog,
    )


async def _authenticate_request(
    metadata: Dict[str, str],
) -> Optional[CloudConnectorAuthError]:
    cloud_connector_user, cloud_connector_error = authenticate(
        metadata, _oidc_auth_provider()
    )

    if cloud_connector_error:
        return cloud_connector_error

    current_user.set(cloud_connector_user)
    return None


class AuthenticationInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(
        self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails
    ) -> grpc.RpcMethodHandler:
        if not _is_auth_enabled():
            _skip_auth()
            return await continuation(handler_call_details)

        metadata = dict(handler_call_details.invocation_metadata)

        cloud_connector_error = await _authenticate_request(metadata)

        if cloud_connector_error:
            return self._abort_handler(
                grpc.StatusCode.UNAUTHENTICATED, cloud_connector_error.error_message
            )

        return await continuation(handler_call_details)

    def _abort_handler(
        self, code: grpc.StatusCode, details: str
    ) -> grpc.RpcMethodHandler:
        # pylint: disable=unused-argument
        async def handler(request: object, context: ServicerContext) -> object:
            await context.abort(code, details)
            return None

        return grpc.unary_unary_rpc_method_handler(handler)


class AuthenticationMiddleware(WebSocketMiddleware):
    async def __call__(self, websocket: WebSocket):
        if not _is_auth_enabled():
            _skip_auth()
            return

        headers = dict(websocket.headers)

        cloud_connector_error = await _authenticate_request(headers)

        if cloud_connector_error:
            # In WebSocket context, we can't use the abort_handler
            # Instead, we'll close the connection
            await websocket.close(
                code=1008,  # 1008 is Policy Violation
                reason=cloud_connector_error.error_message[
                    :123
                ],  # WebSocket close reason has a 123 byte limit
            )
            return
