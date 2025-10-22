from typing import cast

import structlog

from langchain_core.prompt_values import PromptValue
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langchain_core.runnables import Runnable

from ai_gateway.prompts import Prompt, Input, Output
from ai_gateway.prompts.config.base import PromptConfig

log = structlog.stdlib.get_logger("agent_v2")


class AgentWithContext(Prompt[Input, Output]):

    @classmethod
    def _build_prompt_template(
            cls, config: PromptConfig
    ) -> Runnable[Input, PromptValue]:
        messages = list(cls._prompt_template_to_messages(config.prompt_template))

        # We could have more control on what we want to inject and when
        messages.append(MessagesPlaceholder("agents_md", optional=True))
        messages.append(MessagesPlaceholder("some_other_context", optional=True))

        # History should always be the last message
        messages.append(MessagesPlaceholder("history", optional=True))

        return cast(
            Runnable[Input, PromptValue],
            ChatPromptTemplate.from_messages(messages, template_format="jinja2"),
        )
