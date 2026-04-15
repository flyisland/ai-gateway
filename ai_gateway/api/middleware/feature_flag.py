from starlette.middleware.base import Request
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette_context import context as starlette_context

from lib.feature_flags import current_feature_flag_context

from .headers import X_GITLAB_ENABLED_FEATURE_FLAGS, X_GITLAB_REALM_HEADER

# Maps GitLab realm (e.g. "saas", "self-managed") to feature flag names that
# must not be forwarded for that realm.
type DisallowedFlags = dict[str, set[str]]


class FeatureFlagMiddleware:
    """Middleware for feature flags."""

    def __init__(self, app: ASGIApp, disallowed_flags: DisallowedFlags | None = None):
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
            disallowed_flags: Feature flags to suppress per GitLab realm.
                Any flag in the incoming X-Gitlab-Enabled-Feature-Flags
                header that also appears in the set for the request's realm
                is stripped before processing.

        Example:
            FeatureFlagMiddleware(
                app,
                disallowed_flags={
                    "saas": {"flag_a", "flag_b"},
                    "self-managed": {"flag_c"},
                },
            )
        """
        self.app = app
        self.disallowed_flags = disallowed_flags

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        if X_GITLAB_ENABLED_FEATURE_FLAGS not in request.headers:
            await self.app(scope, receive, send)
            return

        enabled_feature_flags = set(
            request.headers.get(X_GITLAB_ENABLED_FEATURE_FLAGS, "").split(",")
        )

        if self.disallowed_flags:
            # Remove feature flags that are not supported in the specific realm.
            gitlab_realm = request.headers.get(X_GITLAB_REALM_HEADER, "")
            disallowed_flags = self.disallowed_flags.get(gitlab_realm, set())
            enabled_feature_flags = enabled_feature_flags.difference(disallowed_flags)

        current_feature_flag_context.set(enabled_feature_flags)
        starlette_context["enabled_feature_flags"] = ",".join(
            list(enabled_feature_flags)
        )

        await self.app(scope, receive, send)
