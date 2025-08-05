from typing import Any, AsyncIterator, List, Optional

from langchain_community.chat_models import litellm
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from litellm.utils import acreate

__all__ = ["ChatLiteLLM"]


async def acompletion_with_retry(
    llm: litellm.ChatLiteLLM,
    run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
    **kwargs: Any,
) -> Any:
    """Use tenacity to retry the async completion call."""
    retry_decorator = litellm._create_retry_decorator(llm, run_manager=run_manager)

    @retry_decorator
    async def _completion_with_retry(**kwargs: Any) -> Any:
        # Use OpenAI's async api https://github.com/openai/openai-python#async-api
        return await acreate(**kwargs)

    return await _completion_with_retry(**kwargs)


litellm.acompletion_with_retry = acompletion_with_retry


class ChatLiteLLM(litellm.ChatLiteLLM):
    """A wrapper around `langchain_community.chat_models.litellm.ChatLiteLLM` that adds custom stream_options."""

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        # Always include usage metrics when streaming. See https://docs.litellm.ai/docs/completion/usage#streaming-usage
        # Respect other possible values that may have been passed.
        kwargs["stream_options"] = {
            **kwargs.get("stream_options", {}),
            "include_usage": True,
        }

        async for chunk in super()._astream(
            messages=messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            yield chunk
