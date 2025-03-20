from datetime import datetime
from typing import Any, AsyncIterator, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import BaseCumulativeTransformOutputParser
from langchain_core.outputs import Generation as LCGeneration
from langchain_core.prompt_values import ChatPromptValue, PromptValue
from langchain_core.runnables import Runnable, RunnableConfig

from ai_gateway.feature_flags import FeatureFlag, is_feature_enabled
from ai_gateway.models.base_chat import Role
from ai_gateway.prompts import (
    Input,
    Output,
    Prompt,
    ServerSentEvent,
    ServerSentEventChunk,
    ServerSentEventEnd,
    ServerSentEventError,
    ServerSentEventStart,
    jinja2_formatter,
)
from ai_gateway.prompts.config import ModelClassProvider, ModelConfig
from ai_gateway.structured_logging import get_request_logger

__all__ = [
    "Generation",
]

request_log = get_request_logger("generation")


class OutputParser(BaseCumulativeTransformOutputParser):
    len_chunk: int = 0

    def _parse(self, text: str) -> ServerSentEvent:
        return ServerSentEventChunk(data={"text": text})

    def parse_result(
        self, result: list[LCGeneration], *, partial: bool = False
    ) -> Optional[ServerSentEvent]:
        event = None
        cumulative_output = result[0].text.strip()

        try:
            diff = cumulative_output[self.len_chunk :]
            self.len_chunk = len(cumulative_output)
            event = ServerSentEventChunk(data={"text": diff})
        except ValueError as e:
            if not partial:
                msg = f"Invalid output: {cumulative_output}"
                raise OutputParserException(msg, llm_output=cumulative_output) from e

        return event

    def parse(self, text: str) -> Optional[str]:
        return self.parse_result([LCGeneration(text=text)])


class PromptBuilder(Runnable[Input, PromptValue]):
    def __init__(self, prompt_template: dict[str, str], model_config: ModelConfig):
        self.prompt_template = prompt_template
        self.model_config = model_config

    def invoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> PromptValue:
        messages = []

        if "system" in self.prompt_template:
            content = jinja2_formatter(
                self.prompt_template["system"],
                current_date=datetime.now().strftime("%A, %B %d, %Y"),
            )
            if (
                is_feature_enabled(FeatureFlag.ENABLE_ANTHROPIC_PROMPT_CACHING)
                and self.model_config.params.model_class_provider
                == ModelClassProvider.ANTHROPIC
            ):
                content = [
                    {
                        "text": content,
                        "type": "text",
                        "cache_control": {"type": "ephemeral"},
                    }
                ]

            messages.append(SystemMessage(content=content))

        for m in input["messages"]:
            if m["role"] == Role.USER.value:
                messages.append(
                    HumanMessage(
                        jinja2_formatter(self.prompt_template["user"], message=m)
                    )
                )
            elif m["role"] == Role.ASSISTANT.value:
                messages.append(AIMessage(m.content))
            else:
                raise ValueError("Unsupported message")

        if not isinstance(messages[-1], HumanMessage):
            raise ValueError("Last message must be a human message")

        return ChatPromptValue(messages=messages)


class Generation(Prompt[Input, Output]):
    RETRYABLE_ERRORS: list[str] = ["overloaded_error"]

    @staticmethod
    def _build_chain(chain: Runnable[Input, Output]) -> Runnable[Input, Output]:
        return chain | OutputParser()

    @classmethod
    def _build_prompt_template(
        cls, prompt_template: dict[str, str], model_config: ModelConfig
    ) -> Runnable:
        return PromptBuilder(prompt_template, model_config)

    async def astream(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Optional[Any],
    ) -> AsyncIterator[ServerSentEvent]:
        astream = super().astream(input, config, **kwargs)

        yield ServerSentEventStart()
        try:
            async for event in astream:
                request_log.info(
                    "Response streaming", source=__name__, streamed_event=event
                )
                yield event
            yield ServerSentEventEnd()
        except Exception as e:
            error_message = str(e)
            retryable = any(err in error_message for err in self.RETRYABLE_ERRORS)

            yield ServerSentEventError(
                data={"message": error_message, "retryable": retryable}
            )
            raise
