from typing import FrozenSet, override
from urllib.parse import urljoin

import httpx
from cachetools import TTLCache, cached
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from ai_gateway.api.middleware.base import _PathResolver
from ai_gateway.instrumentators.usage_quota import (
    USAGE_QUOTA_CHECK_TOTAL,
    USAGE_QUOTA_CUSTOMERSDOT_LATENCY_SECONDS,
    USAGE_QUOTA_CUSTOMERSDOT_REQUESTS_TOTAL,
)
from lib.feature_flags import FeatureFlag, is_feature_enabled
from lib.internal_events.context import EventContext, current_event_context


class UsageQuotaMiddleware(BaseHTTPMiddleware):
    CDOT_RESOLVE_PARAM_KEYS: FrozenSet[str] = frozenset(
        {
            "environment",
            "source",
            "realm",
            "instance_id",
            "unique_instance_id",
            "feature_enablement_type",
            "host_name",
            "instance_version",
            "global_user_id",
            "user_id",
            "project_id",
            "namespace_id",
        }
    )

    def __init__(
        self,
        app: ASGIApp,
        customersdot_url: str,
        skip_endpoints: list[str],
        enabled: bool,
        environment: str,
        # The API call to CustomersDot must be completed in under 1 sec
        # to avoid increasing latency for any AI requests.
        request_timeout: float = 1.0,
    ):
        super().__init__(app)

        self.customersdot_url: str = customersdot_url
        self.enabled: bool = enabled
        self.environment: str = environment
        self.path_resolver = _PathResolver.from_optional_list(skip_endpoints)
        self.request_timeout: float = request_timeout

    def is_active(self) -> bool:
        return self.enabled and is_feature_enabled(FeatureFlag.USAGE_QUOTA_LEFT_CHECK)

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self.is_active():
            return await call_next(request)

        if self.path_resolver.skip_path(request.url.path):
            return await call_next(request)

        event_context = current_event_context.get()
        realm = getattr(event_context, "realm", "unknown")

        try:
            is_authorized = await self.has_usage_quota_left(event_context)
        except Exception:
            is_authorized = True
            USAGE_QUOTA_CHECK_TOTAL.labels(result="fail_open", realm=realm).inc()

        if is_authorized is False:
            USAGE_QUOTA_CHECK_TOTAL.labels(result="deny", realm=realm).inc()
            return JSONResponse(
                status_code=402,
                content={
                    "error": "insufficient_credits",
                    "error_code": "USAGE_QUOTA_EXCEEDED",
                    "message": "Consumer does not have sufficient credits for this request",
                },
            )

        response = await call_next(request)
        USAGE_QUOTA_CHECK_TOTAL.labels(result="allow", realm=realm).inc()

        return response

    @cached(cache=TTLCache(maxsize=10_000, ttl=3600))
    async def has_usage_quota_left(self, context: EventContext) -> bool:
        realm = getattr(context, "realm", "unknown")
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.request_timeout),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            ) as client:
                url = urljoin(self.customersdot_url, "api/v1/consumers/resolve")
                params = context.model_dump(
                    include=set(self.CDOT_RESOLVE_PARAM_KEYS),
                    exclude_none=True,
                    exclude_unset=True,
                )
                with USAGE_QUOTA_CUSTOMERSDOT_LATENCY_SECONDS.labels(
                    realm=realm
                ).time():
                    response = await client.head(url, params=params)

                status = response.status_code
                if status == 200:
                    USAGE_QUOTA_CUSTOMERSDOT_REQUESTS_TOTAL.labels(
                        outcome="success", status="200"
                    ).inc()
                    return True
                if status in (401, 402, 403):
                    USAGE_QUOTA_CUSTOMERSDOT_REQUESTS_TOTAL.labels(
                        outcome="denied", status=str(status)
                    ).inc()
                    return False

                response.raise_for_status()

        except httpx.TimeoutException:
            USAGE_QUOTA_CUSTOMERSDOT_REQUESTS_TOTAL.labels(
                outcome="timeout", status="timeout"
            ).inc()
            raise
        except httpx.HTTPStatusError:
            USAGE_QUOTA_CUSTOMERSDOT_REQUESTS_TOTAL.labels(
                outcome="http_error", status=str(status)
            ).inc()
            raise
        except Exception:
            USAGE_QUOTA_CUSTOMERSDOT_REQUESTS_TOTAL.labels(
                outcome="unexpected", status="client_error"
            ).inc()
            raise

        return False
