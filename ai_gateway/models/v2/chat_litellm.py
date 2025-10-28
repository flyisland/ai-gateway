from typing import Any, AsyncIterator, List, Optional

from langchain_community.chat_models.litellm import ChatLiteLLM as _LChatLiteLLM
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
import structlog

__all__ = ["ChatLiteLLM"]

log = structlog.stdlib.get_logger("chatlitellm")

class ChatLiteLLM(_LChatLiteLLM):
    """A wrapper around `langchain_community.chat_models.litellm.ChatLiteLLM` that adds custom stream_options and
    Fireworks-specific functionality."""

    def _setup_fireworks_kwargs(self, kwargs: dict[str, Any]) -> None:
        """Setup Fireworks-specific kwargs including prompt caching, session affinity headers, and logprobs."""
        # Apply prompt caching control
        if kwargs.pop("using_cache", "True").lower() == "false":
            kwargs["prompt_cache_max_len"] = 0

        # Add session affinity header if conditions are met
        session_id = kwargs.pop("session_id", None)
        if session_id:
            if "extra_headers" not in kwargs:
                kwargs["extra_headers"] = {}
            kwargs["extra_headers"]["x-session-affinity"] = session_id

        # Add logprobs for Fireworks (matching LiteLlmTextGenModel behavior)
        kwargs["logprobs"] = 1

    def _apply_fireworks_setup_if_needed(self, kwargs: dict[str, Any]) -> None:
        """Apply Fireworks-specific setup if using Fireworks provider."""
        if self.custom_llm_provider == "fireworks_ai":
            self._setup_fireworks_kwargs(kwargs)

    def _extract_logprob_score(self, generation_info: dict) -> None:
        """Extract logprobs as score from generation info (matching LiteLlmTextGenModel behavior)."""
        if not generation_info:
            return

        response_metadata = generation_info.get('response_metadata', {})
        logprobs = response_metadata.get('logprobs')
        log.debug(f"RESPONSE METADATA {response_metadata}")
        if logprobs and hasattr(logprobs, 'token_logprobs') and logprobs.token_logprobs:
            # Use logprob of first token as score (matching LiteLlmTextGenModel behavior)
            score = logprobs.token_logprobs[0]
            log.debug(f"SCORE {score}")
            # Update the generation info with the score
            if 'score' not in generation_info:
                generation_info['score'] = score

    def _extract_fireworks_score(self, result: ChatResult) -> ChatResult:
        """Extract logprobs as score for Fireworks responses (matching LiteLlmTextGenModel behavior)."""
        if not result.generations:
            return result
        log.debug(f"RESULT {result}")
        # Get the first generation
        generation = result.generations[0]
        log.debug(f"GENERATION INFO {generation.generation_info}")
        # Extract logprobs as score if generation info exists
        if hasattr(generation, 'generation_info') and generation.generation_info:
            self._extract_logprob_score(generation.generation_info)

        return result

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

        # Apply Fireworks-specific setup if using Fireworks provider
        self._apply_fireworks_setup_if_needed(kwargs)

        async for chunk in super()._astream(
            messages=messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            # Extract logprobs as score for Fireworks streaming chunks if available
            if self.custom_llm_provider == "fireworks_ai":
                chunk = self._extract_fireworks_chunk_score(chunk)
            yield chunk

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        stream: Optional[bool] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Apply Fireworks-specific setup if using Fireworks provider
        self._apply_fireworks_setup_if_needed(kwargs)
        log.debug(f"IS FIREWORKS {self.custom_llm_provider == "fireworks_ai"} KWARGS {kwargs.keys()}")
        result = await super()._agenerate(
            messages=messages,
            stop=stop,
            run_manager=run_manager,
            stream=stream,
            **kwargs,
        )

        # Extract logprobs as score for Fireworks (matching LiteLlmTextGenModel behavior)
        if self.custom_llm_provider == "fireworks_ai":
            result = self._extract_fireworks_score(result)

        return result

    def _extract_fireworks_chunk_score(self, chunk: ChatGenerationChunk) -> ChatGenerationChunk:
        """Extract logprobs as score for Fireworks streaming chunks (matching LiteLlmTextGenModel behavior)."""
        # Extract logprobs as score if generation info exists
        if hasattr(chunk, 'generation_info') and chunk.generation_info:
            self._extract_logprob_score(chunk.generation_info)

        return chunk
