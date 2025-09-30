import json
from typing import List

import structlog
import tiktoken
from langchain_anthropic.chat_models import _format_messages
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately

logger = structlog.stdlib.get_logger("approximate_token_counter")

_DEFAULT_TOOL_TOKENS = 40300


def _calculate_tool_tokens() -> int:
    try:
        # avoid circular imports
        from langchain_anthropic import convert_to_anthropic_tool

        from duo_workflow_service.components.tools_registry import get_all_op_tools

        encoding = tiktoken.encoding_for_model("gpt-4o")
        tools_data = json.dumps(
            [convert_to_anthropic_tool(tool=tool()) for tool in get_all_op_tools()]
        )
        return len(encoding.encode(tools_data))
    except Exception as e:
        logger.error(f"Failed to calculate tool tokens: {e}")
        # when hit error, assigned an estimated number
        return _DEFAULT_TOOL_TOKENS


class ApproximateTokenCounter:
    _encoding = tiktoken.encoding_for_model("gpt-4o")

    def __init__(self):
        self._tool_tokens = None

    def get_tool_tokens(self) -> int:
        if self._tool_tokens is None:
            self._tool_tokens = _calculate_tool_tokens()
        return self._tool_tokens

    def count_str_tokens(self, data: str, include_tool_specs: bool) -> int:
        token_size = self.get_tool_tokens() if include_tool_specs else 0
        token_size += len(ApproximateTokenCounter._encoding.encode(data))
        return token_size

    def count_messages_tokens(
        self, messages: List[BaseMessage], include_tool_specs: bool = False
    ) -> int:
        try:
            system_message, rest_messages = _format_messages(messages)
        except Exception as e:
            logger.error(
                f"Fallback to use langgraph token estimator due to hitting unexpected error: {e}"
            )
            # count_tokens_approximately only counts message tokens, not tool tokens
            token_size = count_tokens_approximately(messages)
            if include_tool_specs:
                token_size += self.get_tool_tokens()
            return token_size
        return self.count_str_tokens(
            json.dumps((system_message, rest_messages)),
            include_tool_specs=include_tool_specs,
        )
