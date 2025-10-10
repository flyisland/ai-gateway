import logging
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Generic, Optional, TypeVar, override
from urllib.parse import urljoin

import httpx
from cachetools import TTLCache
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from ai_gateway.api.middleware.base import _PathResolver
from lib.internal_events.context import EventContext, current_event_context

logger = logging.getLogger("entitlements")

V = TypeVar("V")


class ThreadSafeTTLCache(Generic[V]):
    def __init__(self, maxsize: int, ttl: int) -> None:
        self._cache: TTLCache[str, V] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock: Lock = Lock()

    def get(self, key: str) -> Optional[V]:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: V) -> None:
        with self._lock:
            self._cache[key] = value

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


class EntitlementDecision(Enum):
    AUTHORIZED = "authorized"
    NOT_ENTITLED = "not_entitled"
    ERROR_FALLBACK = "error_fallback"


@dataclass
class CachedEntitlementDecision:
    authorized: bool


@dataclass
class EntitlementCheckResult:
    decision: EntitlementDecision
    error_message: str | None = None
    should_cache: bool = True


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
        self.cache_duration: int = 60  # We process usage data hourly
        self.request_timeout: float = request_timeout
        self.entitlements_cache: ThreadSafeTTLCache[CachedEntitlementDecision] = (
            ThreadSafeTTLCache(maxsize=10_000, ttl=self.cache_duration)
        )

        self.http_client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=httpx.Timeout(self.request_timeout),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self.path_resolver.skip_path(request.url.path):
            return await call_next(request)

        event_context = current_event_context.get()
        entitlement_result = await self.check_consumer_entitlements(event_context)

        if entitlement_result.decision == EntitlementDecision.NOT_ENTITLED:
            return JSONResponse(
                status_code=402,
                content={
                    "error": "not_entitled",
                    "error_code": "ENTITLEMENT_NOT_ENTITLED",
                    "message": "Consumer does not have sufficient credits for this request",
                },
            )
        elif entitlement_result.decision == EntitlementDecision.ERROR_FALLBACK:
            logger.error(
                f"Entitlement check failed, allowing request (fail-open): {entitlement_result.error_message}"
            )

        response = await call_next(request)

        return response

    async def check_consumer_entitlements(
        self, context: EventContext
    ) -> EntitlementCheckResult:
        cache_key = context.to_cache_key()

        cached_decision = self.entitlements_cache.get(cache_key)
        if cached_decision:
            logger.debug(f"Cache hit for key {cache_key[:50]}")
            decision = (
                EntitlementDecision.AUTHORIZED
                if cached_decision.authorized
                else EntitlementDecision.NOT_ENTITLED
            )
            return EntitlementCheckResult(decision=decision, should_cache=False)

        logger.debug(f"Cache miss for key {cache_key[:50]}")
        return await self.fetch_entitlements_from_customersdot(cache_key, context)

    async def fetch_entitlements_from_customersdot(
        self, cache_key: str, context: EventContext
    ) -> EntitlementCheckResult:
        try:
            query_params = context.model_dump()
            response = await self.http_client.head(
                urljoin(self.customersdot_url, "api/v1/consumers/resolve"),
                params=query_params,
            )

            authorized = response.status_code == 200

            cached_decision = CachedEntitlementDecision(
                authorized=authorized,
            )

            self.entitlements_cache.set(cache_key, cached_decision)
            decision = (
                EntitlementDecision.AUTHORIZED
                if authorized
                else EntitlementDecision.NOT_ENTITLED
            )

            if not authorized:
                logger.info(f"CustomersDot denied entitlement: {response.status_code}")

            return EntitlementCheckResult(decision=decision, should_cache=True)

        except httpx.TimeoutException:
            logger.warning(
                f"CustomersDot timeout after {self.request_timeout}s - allowing request (fail-open)"
            )
            return EntitlementCheckResult(
                decision=EntitlementDecision.ERROR_FALLBACK,
                error_message="Entitlement service timeout",
                should_cache=False,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [402]:
                logger.info("Insufficient entitlements")
                cached_decision = CachedEntitlementDecision(authorized=False)
                self.entitlements_cache.set(cache_key, cached_decision)
                return EntitlementCheckResult(
                    decision=EntitlementDecision.NOT_ENTITLED,
                    error_message=f"HTTP {e.response.status_code}",
                    should_cache=True,
                )
            else:
                logger.error(
                    f"CustomersDot HTTP error {e.response.status_code} - allowing request (fail-open)"
                )
                return EntitlementCheckResult(
                    decision=EntitlementDecision.AUTHORIZED,
                    error_message=f"HTTP error: {e.response.status_code}",
                    should_cache=False,
                )
        except Exception as e:
            logger.error(
                f"Unexpected error calling CustomersDot - allowing request (fail-open): {e}"
            )
            return EntitlementCheckResult(
                decision=EntitlementDecision.AUTHORIZED,
                error_message=f"Unexpected error: {e}",
                should_cache=False,
            )

    async def cleanup(self):
        await self.http_client.aclose()
