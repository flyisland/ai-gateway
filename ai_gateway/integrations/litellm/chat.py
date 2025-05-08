from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from langchain_community.chat_models.litellm import ChatLiteLLM
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult


class CustomChatLiteLLM(ChatLiteLLM):
    """Custom class to add stream_options conditionally to stream."""

    default_stream_options: Dict[str, Any] = {"include_usage": True}

    def _manage_stream_options(self, stream: bool | None, kwargs) -> None:
        should_stream = stream if stream is not None else self.streaming
        if should_stream:
            kwargs["stream_options"] = {
                **kwargs.get("stream_options", {}),
                **self.default_stream_options,
            }
        else:
            if "stream_options" in kwargs:
                del kwargs["stream_options"]

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        stream: Optional[bool] = None,
        **kwargs: Any,
    ) -> ChatResult:

        self._manage_stream_options(stream, kwargs)
        return super()._generate(
            messages=messages,
            stop=stop,
            run_manager=run_manager,
            stream=stream,
            **kwargs,
        )

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        stream: Optional[bool] = None,
        **kwargs: Any,
    ) -> ChatResult:

        self._manage_stream_options(stream, kwargs)
        return await super()._agenerate(
            messages=messages,
            stop=stop,
            run_manager=run_manager,
            stream=stream,
            **kwargs,
        )

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:

        self._manage_stream_options(True, kwargs)
        for chunk in super()._stream(
            messages=messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            yield chunk

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:

        self._manage_stream_options(True, kwargs)
        async for chunk in super()._astream(
            messages=messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            yield chunk
