import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

import structlog
from asgi_correlation_id.context import correlation_id
from fastapi import status
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import Request
from starlette_context import context as starlette_context
from uvicorn.protocols.utils import get_path_with_query_string

from ai_gateway.tracking.errors import log_exception
from lib.internal_events.context import current_event_context

from .headers import (
    X_GITLAB_FEATURE_ENABLED_BY_NAMESPACE_IDS_HEADER,
    X_GITLAB_FEATURE_ENABLEMENT_TYPE_HEADER,
    X_GITLAB_GLOBAL_USER_ID_HEADER,
    X_GITLAB_HOST_NAME_HEADER,
    X_GITLAB_INSTANCE_ID_HEADER,
    X_GITLAB_LANGUAGE_SERVER_VERSION,
    X_GITLAB_MODEL_GATEWAY_REQUEST_SENT_AT,
    X_GITLAB_REALM_HEADER,
    X_GITLAB_SAAS_DUO_PRO_NAMESPACE_IDS_HEADER,
    X_GITLAB_VERSION_HEADER,
)

log = logging.getLogger("codesuggestions")
access_logger = structlog.stdlib.get_logger("api.access")


class _PathResolver:
    def __init__(self, endpoints: list[str]):
        self.endpoints = set(endpoints)

    @classmethod
    def from_optional_list(cls, endpoints: Optional[list] = None) -> "_PathResolver":
        if endpoints is None:
            endpoints = []
        return cls(endpoints)

    def skip_path(self, path: str) -> bool:
        return path in self.endpoints


class AccessLogMiddleware:
    """Middleware for access logging."""

    def __init__(self, app, skip_endpoints):
        self.app = app
        self.path_resolver = _PathResolver.from_optional_list(skip_endpoints)

    def _add_event_context_fields(self, fields: dict) -> None:
        """Add event context attributes to log fields if available."""
        event_context = current_event_context.get()
        if event_context is not None:
            # Only add fields that have non-None values
            if event_context.instance_id is not None:
                fields["event_context_instance_id"] = str(event_context.instance_id)
            if event_context.host_name is not None:
                fields["event_context_host_name"] = str(event_context.host_name)
            if event_context.realm is not None:
                fields["event_context_realm"] = str(event_context.realm)
            if event_context.is_gitlab_team_member is not None:
                fields["is_gitlab_team_member"] = str(
                    event_context.is_gitlab_team_member
                )
            if event_context.global_user_id is not None:
                fields["event_context_global_user_id"] = str(
                    event_context.global_user_id
                )
            if event_context.correlation_id is not None:
                fields["event_context_correlation_id"] = str(
                    event_context.correlation_id
                )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        if self.path_resolver.skip_path(request.url.path):
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        # These context vars will be added to all log entries emitted during the request
        request_id = correlation_id.get()
        structlog.contextvars.bind_contextvars(correlation_id=request_id)

        start_time_total = time.perf_counter()
        start_time_cpu = time.process_time()
        response_start_duration_s = 0.0
        first_chunk_duration_s = 0.0
        request_arrived_at = datetime.now(timezone.utc)
        # duration_request represents latency added by sending request from Rails to AI gateway
        try:
            wait_duration = time.time() - float(
                request.headers.get(X_GITLAB_MODEL_GATEWAY_REQUEST_SENT_AT)
            )
        except (ValueError, TypeError):
            wait_duration = -1

        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        content_type = "unknown"

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                nonlocal status_code, response_start_duration_s, first_chunk_duration_s, content_type
                status_code = message["status"]

                headers = MutableHeaders(scope=message)

                if "content-type" in headers:
                    content_type = headers["content-type"]

                response_start_duration_s = time.perf_counter() - start_time_total
                headers.append("X-Process-Time", str(response_start_duration_s))

            if message["type"] == "http.response.body":
                if first_chunk_duration_s == 0.0:
                    first_chunk_duration_s = time.perf_counter() - start_time_total

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            if isinstance(e, BaseExceptionGroup):
                e = e.exceptions[0]
            starlette_context.data["exception_message"] = str(e)
            starlette_context.data["exception_class"] = type(e).__name__
            starlette_context.data["exception_backtrace"] = traceback.format_exc()
            log_exception(e)
            raise e
        finally:
            elapsed_time = time.perf_counter() - start_time_total
            cpu_time = time.process_time() - start_time_cpu
            url = get_path_with_query_string(request.scope)
            client_host = request.client.host
            client_port = request.client.port
            http_method = request.method
            http_version = request.scope["http_version"]

            fields = {
                "url": str(request.url),
                "path": url,
                "status_code": status_code,
                "method": http_method,
                "correlation_id": request_id,
                "http_version": http_version,
                "client_ip": client_host,
                "client_port": client_port,
                "duration_s": elapsed_time,
                "duration_request": wait_duration,
                "request_arrived_at": request_arrived_at.isoformat(),
                "response_start_duration_s": response_start_duration_s,
                "first_chunk_duration_s": first_chunk_duration_s,
                "cpu_s": cpu_time,
                "content_type": content_type,
                "user_agent": request.headers.get("User-Agent"),
                "gitlab_language_server_version": request.headers.get(
                    X_GITLAB_LANGUAGE_SERVER_VERSION
                ),
                "gitlab_instance_id": request.headers.get(X_GITLAB_INSTANCE_ID_HEADER),
                "gitlab_global_user_id": request.headers.get(
                    X_GITLAB_GLOBAL_USER_ID_HEADER
                ),
                "gitlab_host_name": request.headers.get(X_GITLAB_HOST_NAME_HEADER),
                "gitlab_version": request.headers.get(X_GITLAB_VERSION_HEADER),
                "gitlab_saas_duo_pro_namespace_ids": request.headers.get(
                    X_GITLAB_SAAS_DUO_PRO_NAMESPACE_IDS_HEADER
                ),
                "gitlab_feature_enabled_by_namespace_ids": request.headers.get(
                    X_GITLAB_FEATURE_ENABLED_BY_NAMESPACE_IDS_HEADER
                ),
                "gitlab_feature_enablement_type": request.headers.get(
                    X_GITLAB_FEATURE_ENABLEMENT_TYPE_HEADER
                ),
                "gitlab_realm": request.headers.get(X_GITLAB_REALM_HEADER),
            }

            # Add event context attributes
            self._add_event_context_fields(fields)

            # Safely update with starlette context data
            try:
                fields.update(starlette_context.data)
            except Exception:
                # Handle case where starlette context is not available (e.g., in tests)
                pass

            # Recreate the Uvicorn access log format, but add all parameters as structured information
            access_logger.info(
                f"""{client_host}:{client_port} - "{http_method} {url} HTTP/{http_version}" {status_code}""",
                **fields,
            )


class InternalEventMiddleware:
    def __init__(self, app, skip_endpoints, enabled, environment):
        self.app = app
        self.enabled = enabled
        self.environment = environment
        self.path_resolver = _PathResolver.from_optional_list(skip_endpoints)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        if self.path_resolver.skip_path(request.url.path):
            await self.app(scope, receive, send)
            return

        # Set the distributed tracing LangSmith header to the tracing context, which is sent from
        # Langsmith::RunHelpers of GitLab-Rails/Sidekiq.
        # See https://docs.gitlab.com/ee/development/ai_features/duo_chat.html#tracing-with-langsmith
        # and https://docs.smith.langchain.com/how_to_guides/tracing/distributed_tracing
        await self.app(scope, receive, send)
