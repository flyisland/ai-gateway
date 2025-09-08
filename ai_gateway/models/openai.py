from enum import StrEnum
from typing import Any, AsyncIterator, Callable, Optional, Union

import httpx
import structlog
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AsyncStream,
)
from openai.types import Completion
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from ai_gateway.models.base import (
    KindModelProvider,
    ModelAPICallError,
    ModelAPIError,
    ModelMetadata,
)
from ai_gateway.models.base_chat import ChatModelBase, Message
from ai_gateway.models.base_text import (
    TextGenModelBase,
    TextGenModelChunk,
    TextGenModelOutput,
)
from ai_gateway.safety_attributes import SafetyAttributes

__all__ = [
    "OpenAIAPIConnectionError",
    "OpenAIAPIStatusError",
    "OpenAIAPITimeoutError",
    "OpenAIModel",
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
        wrapper = cls(ex.message, errors=(ex,))
        return wrapper


class OpenAIAPITimeoutError(ModelAPIError):
    @classmethod
    def from_exception(cls, ex: APITimeoutError):
        wrapper = cls(str(ex), errors=(ex,))
        return wrapper


class KindOpenAIModel(StrEnum):
    GPT_5 = "gpt-5"


class OpenAIModel(TextGenModelBase):
    """This class uses the legacy Completions API from OpenAI. Modern GPT models should use OpenAIChatModel."""

    OPTS_CLIENT = {
        "max_retries": 1,
    }

    OPTS_MODEL = {
        "timeout": httpx.Timeout(30.0, connect=5.0),
        "max_tokens": 2048,
        "temperature": 0.2,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "stop": None,
    }

    def __init__(
        self,
        client: AsyncOpenAI,
        model_name: str = KindOpenAIModel.GPT_5.value,
        **kwargs: Any,
    ):
        client_opts = self._obtain_client_opts(**kwargs)
        self.client = client.with_options(**client_opts)
        self.model_opts = self._obtain_model_opts(**kwargs)

        self._metadata = ModelMetadata(
            name=model_name,
            engine=KindModelProvider.OPENAI.value,
        )

    @staticmethod
    def _obtain_model_opts(**kwargs: Any):
        return _obtain_opts(OpenAIModel.OPTS_MODEL, **kwargs)

    @staticmethod
    def _obtain_client_opts(**kwargs: Any):
        return _obtain_opts(OpenAIModel.OPTS_CLIENT, **kwargs)

    @property
    def metadata(self) -> ModelMetadata:
        return self._metadata

    @property
    def input_token_limit(self) -> int:
        # Default token limit for most OpenAI models
        return 4096

    async def generate(
        self,
        prefix: str,
        suffix: Optional[str] = "",
        stream: bool = False,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        **kwargs: Any,
    ) -> Union[
        TextGenModelOutput, list[TextGenModelOutput], AsyncIterator[TextGenModelChunk]
    ]:
        default_values = {
            **{
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_output_tokens,
            },
            **kwargs,
        }
        opts = _obtain_opts(self.model_opts, **default_values)

        log.debug("codegen openai call:", **opts)

        with self.instrumentator.watch(stream=stream) as watcher:
            try:
                suggestion = await self.client.completions.create(
                    model=self.metadata.name,
                    prompt=prefix,
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
                return self._handle_stream(suggestion, watcher.finish)

        completion_text = (
            getattr(suggestion.choices[0], "text", "") if suggestion.choices else ""
        )
        return TextGenModelOutput(
            text=completion_text,
            score=10**5,
            safety_attributes=SafetyAttributes(),
        )

    async def _handle_stream(
        self, response, after_callback: Callable
    ) -> AsyncIterator[TextGenModelChunk]:
        try:
            async for event in response:
                if isinstance(event, AsyncStream):
                    async for comp in event:
                        text = (
                            getattr(comp.choices[0], "text", "") if comp.choices else ""
                        )
                        yield TextGenModelChunk(text=text)
                elif isinstance(event, Completion):
                    text = (
                        getattr(event.choices[0], "text", "") if event.choices else ""
                    )
                    yield TextGenModelChunk(text=text)
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


class OpenAIChatModel(ChatModelBase):
    OPTS_CLIENT = {
        "max_retries": 1,
    }

    OPTS_MODEL = {
        "timeout": httpx.Timeout(30.0, connect=5.0),
        "max_tokens": 4096,
        "temperature": 0.2,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "stop": None,
    }

    def __init__(
        self,
        client: AsyncOpenAI,
        model_name: str = KindOpenAIModel.GPT_5.value,
        **kwargs: Any,
    ):
        client_opts = self._obtain_client_opts(**kwargs)
        self.client = client.with_options(**client_opts)
        self.model_opts = self._obtain_model_opts(**kwargs)

        self._metadata = ModelMetadata(
            name=model_name,
            engine=KindModelProvider.OPENAI.value,
        )

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
        # Token limit for modern OpenAI chat models
        return 128_000

    async def generate(
        self,
        messages: list[Message],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        **kwargs: Any,
    ) -> Union[TextGenModelOutput, AsyncIterator[TextGenModelChunk]]:

        default_values = {
            **{
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_output_tokens,
            },
            **kwargs,
        }
        opts = _obtain_opts(self.model_opts, **default_values)
        log.debug("codegen openai chat call:", **opts)

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

        text = (
            getattr(suggestion.choices[0].message, "content", "")
            if hasattr(suggestion, "choices") and suggestion.choices
            else ""
        )
        return TextGenModelOutput(
            text=text,
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
            async for event in response:
                if isinstance(event, ChatCompletion):
                    text = (
                        getattr(event.choices[0].message, "content", "")
                        if event.choices
                        else ""
                    )
                elif isinstance(event, ChatCompletionChunk):
                    delta = event.choices[0].delta if event.choices else None
                    text = getattr(delta, "content", "") if delta else ""
                else:
                    continue
                yield TextGenModelChunk(text=text or "")
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


def _build_model_messages(messages: list[Message]) -> list[dict]:
    model_messages = []

    for message in messages:
        model_messages.append(
            {
                "role": message.role.value,
                "content": message.content,
            }
        )

    return model_messages


def _obtain_opts(default_opts: dict, **kwargs: Any) -> dict:
    return {
        opt_name: kwargs.pop(opt_name, opt_value) or opt_value
        for opt_name, opt_value in default_opts.items()
    }
