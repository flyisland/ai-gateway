from langsmith.run_helpers import tracing_context
from starlette.middleware.base import Request
from starlette_context import context as starlette_context

from .base import _PathResolver


class DistributedTraceMiddleware:
    """Middleware for distributed tracing."""

    def __init__(self, app, skip_endpoints, environment):
        self.app = app
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

        if self.environment == "development" and "langsmith-trace" in request.headers:
            # Set the distrubted tracing LangSmith header to the tracing context, which is sent from Langsmith::RunHelpers of GitLab-Rails/Sidekiq.
            # See https://docs.gitlab.com/ee/development/ai_features/duo_chat.html#tracing-with-langsmith
            # and https://docs.smith.langchain.com/how_to_guides/tracing/distributed_tracing
            with tracing_context(parent=request.headers["langsmith-trace"]):
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)
