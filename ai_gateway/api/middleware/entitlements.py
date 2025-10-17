import logging
from typing import override
from urllib.parse import urljoin

import httpx
from cachetools import TTLCache, cached
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from ai_gateway.api.middleware.base import _PathResolver
from lib.internal_events.context import EventContext, current_event_context

logger = logging.getLogger("entitlements")


class EntitlementsMiddleware(BaseHTTPMiddleware):
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

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self.path_resolver.skip_path(request.url.path):
            return await call_next(request)

        event_context = current_event_context.get()

        try:
            is_authorized = await self.check_consumer_entitlements(event_context)
        except Exception:
            is_authorized = True

        if is_authorized is False:
            return JSONResponse(
                status_code=402,
                content={
                    "error": "not_entitled",
                    "error_code": "ENTITLEMENT_NOT_ENTITLED",
                    "message": "Consumer does not have sufficient credits for this request",
                },
            )

        response = await call_next(request)

        return response

    @cached(cache=TTLCache(maxsize=10_000, ttl=60))
    async def check_consumer_entitlements(self, context: EventContext) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.request_timeout),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            ) as client:
                response = await client.head(
                    urljoin(self.customersdot_url, "api/v1/consumers/resolve"),
                    params=context.model_dump_json(),
                )

                return response.status_code == 200

        except httpx.TimeoutException as e:
            logger.warning(
                "CustomersDot timeout after %ss - allowing request (fail-open)",
                self.request_timeout,
            )
            raise e
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [402]:
                logger.info("Insufficient entitlements")
                return False

            logger.error(
                "CustomersDot HTTP error %s - allowing request (fail-open)",
                e.response.status_code,
            )
            raise e
        except Exception as e:
            logger.error(
                "Unexpected error calling CustomersDot - allowing request (fail-open): %s",
                e,
            )
            raise e
