from enum import StrEnum
from typing import Any, AsyncIterator, Callable, Union

import httpx
import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from ai_gateway.models.base import (
    KindModelProvider,
    ModelAPICallError,
    ModelAPIError,
    ModelMetadata,
)
from ai_gateway.models.base_chat import ChatModelBase, Message
from ai_gateway.models.base_text import TextGenModelChunk, TextGenModelOutput
from ai_gateway.safety_attributes import SafetyAttributes

__all__ = [
    "OpenAIAPIConnectionError",
    "OpenAIAPIStatusError",
    "OpenAIAPITimeoutError",
    "OpenAIChatModel",
    "KindOpenAIModel",
]

log = structlog.stdlib.get_logger("codesuggestions")


class OpenAIAPIConnectionError(ModelAPIError):
    @classmethod
    def from_exception(cls, ex: APIConnectionError):
        wrapper = cls(str(ex), errors=(ex,))
        return wrapper


class OpenAIAPIStatusError(ModelAPICallError):
    @classmethod
    def from_exception(cls, ex: APIStatusError):
        cls.code = ex.status_code
        wrapper = cls(str(ex), errors=(ex,))
        return wrapper


class OpenAIAPITimeoutError(ModelAPIError):
    @classmethod
    def from_exception(cls, ex: APITimeoutError):
        wrapper = cls(str(ex), errors=(ex,))
        return wrapper


class KindOpenAIModel(StrEnum):
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_1 = "gpt-4.1"


class OpenAIChatModel(ChatModelBase):
    OPTS_CLIENT = {
        "default_headers": {},
        "max_retries": 1,
    }

    OPTS_MODEL = {
        "timeout": httpx.Timeout(30.0, connect=5.0),
        "max_tokens": 4096,
        "temperature": 0.2,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    }

    def __init__(
        self,
        client: AsyncOpenAI,
        model_name: str = KindOpenAIModel.GPT_4_1.value,
        **kwargs: Any,
    ):
        client_opts = self._obtain_client_opts(**kwargs)
        self.client = client.with_options(**client_opts)
        self.model_opts = self._obtain_model_opts(**kwargs)

        self._metadata = ModelMetadata(
            name=model_name,
            engine=KindModelProvider.OPENAI.value,
        )

        # Initialize the instrumentator from the base class
        super().__init__()

    @staticmethod
    def _obtain_model_opts(**kwargs: Any):
        return _obtain_opts(OpenAIChatModel.OPTS_MODEL, **kwargs)

    @staticmethod
    def _obtain_client_opts(**kwargs: Any):
        return _obtain_opts(OpenAIChatModel.OPTS_CLIENT, **kwargs)

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    @property
    def input_token_limit(self) -> int:
        # Most OpenAI models have a 128k context window
        return 128_000

    async def generate(
        self,
        messages: list[Message],
        stream: bool = False,
        temperature: float = 0.2,
        max_output_tokens: int = 16,
        top_p: float = 0.95,
        top_k: int = 40,
    ) -> Union[TextGenModelOutput, AsyncIterator[TextGenModelChunk]]:

        default_values = {
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_output_tokens,
        }
        opts = _obtain_opts(self.model_opts, **default_values)
        log.debug("codegen openai call:", **opts)

        model_messages = _build_model_messages(messages)

        with self.instrumentator.watch(stream=stream) as watcher:
            try:
                suggestion = await self.client.chat.completions.create(
                    model=self.metadata.name,
                    messages=model_messages,
                    stream=stream,
                    **opts,
                )
            except APIStatusError as ex:
                raise OpenAIAPIStatusError.from_exception(ex)
            except APITimeoutError as ex:
                raise OpenAIAPITimeoutError.from_exception(ex)
            except APIConnectionError as ex:
                raise OpenAIAPIConnectionError.from_exception(ex)

            if stream:
                return self._handle_stream(
                    suggestion,
                    watcher.finish,
                    watcher.register_error,
                )
            # Handle non-stream response - suggestion is ChatCompletion here
            if isinstance(suggestion, ChatCompletion):
                text = (
                    suggestion.choices[0].message.content
                    if suggestion.choices and suggestion.choices[0].message.content
                    else ""
                )
                return TextGenModelOutput(
                    text=text,
                    # Give a high value, the model doesn't return scores.
                    score=10**5,
                    safety_attributes=SafetyAttributes(),
                )
            # This shouldn't happen in non-stream mode, but handle it gracefully
            # pylint: disable=no-else-return
            return TextGenModelOutput(
                text="",
                score=10**5,
                safety_attributes=SafetyAttributes(),
            )

    async def _handle_stream(
        self,
        response,
        after_callback: Callable,
        error_callback: Callable,
    ) -> AsyncIterator[TextGenModelChunk]:
        try:
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    yield TextGenModelChunk(text=text)
        except Exception:
            error_callback()
            raise
        finally:
            after_callback()

    @classmethod
    def from_model_name(
        cls,
        name: Union[str, KindOpenAIModel],
        client: AsyncOpenAI,
        **kwargs: Any,
    ):
        try:
            kind_model = KindOpenAIModel(name)
        except ValueError:
            raise ValueError(f"no model found by the name '{name}'")

        return cls(client, model_name=kind_model.value, **kwargs)


def _build_model_messages(messages: list[Message]) -> list[ChatCompletionMessageParam]:
    model_messages: list[ChatCompletionMessageParam] = []
    for message in messages:
        model_messages.append(
            {
                "role": message.role.value,  # type: ignore
                "content": message.content,
            }
        )
    return model_messages


def _obtain_opts(default_opts: dict, **kwargs: Any) -> dict:
    return {
        opt_name: kwargs.pop(opt_name, opt_value) or opt_value
        for opt_name, opt_value in default_opts.items()
    }
