from typing import Any, AsyncIterator, List, Optional

import structlog
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk

from ai_gateway.tracking import SnowplowEventContext

from .chat_litellm import ChatLiteLLM

__all__ = ["ChatFireworks"]

logger = structlog.stdlib.get_logger("fireworks")


class ChatFireworks(ChatLiteLLM):
    """A Fireworks-specific wrapper that implements prompt caching control similar to LiteLlmTextGenModel."""

    def _setup_fireworks_kwargs(self, kwargs: dict[str, Any]) -> None:
        """Setup Fireworks-specific kwargs including prompt caching and session affinity headers."""
        # Apply prompt caching control
        if not kwargs.pop("using_cache", True):
            kwargs["prompt_cache_max_len"] = 0

        # Add session affinity header if conditions are met
        session_id = kwargs.pop("session_id", None)
        if session_id:
            if "extra_headers" not in kwargs:
                kwargs["extra_headers"] = {}
            kwargs["extra_headers"]["x-session-affinity"] = session_id

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        self._setup_fireworks_kwargs(kwargs)

        async for chunk in super()._astream(
            messages=messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            yield chunk

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ):
        self._setup_fireworks_kwargs(kwargs)

        return await super()._agenerate(
            messages=messages, stop=stop, run_manager=run_manager, **kwargs
        )
