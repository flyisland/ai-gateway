import json
from typing import List

import structlog
import tiktoken
from langchain_anthropic.chat_models import _format_messages
from langchain_core.messages.base import BaseMessage


class ApproximateTokenCounter:

    _encoding = tiktoken.encoding_for_model("gpt-4o")
    _tool_tokens = 0
    _tool_tokens_calculated = False

    def __init__(self):
        self._logger = structlog.stdlib.get_logger("approximate_token_counter")

        if ApproximateTokenCounter._tool_tokens_calculated is False:
            try:
                # avoid circular imports
                from langchain_anthropic import convert_to_anthropic_tool

                from duo_workflow_service.components.tools_registry import (
                    get_all_op_tools,
                )

                tools_data = json.dumps(
                    [
                        convert_to_anthropic_tool(tool=tool())
                        for tool in get_all_op_tools()
                    ]
                )
                ApproximateTokenCounter._tool_tokens = len(
                    ApproximateTokenCounter._encoding.encode(tools_data)
                )
                ApproximateTokenCounter._tool_tokens_calculated = True
                self._logger.info(
                    f"Calculated tool specs token size: {ApproximateTokenCounter._tool_tokens}"
                )
            except Exception as e:
                self._logger.error(f"Failed to calculate tool tokens: {e}")
                ApproximateTokenCounter._tool_tokens = 0
                ApproximateTokenCounter._tool_tokens_calculated = True

        self._tool_tokens = ApproximateTokenCounter._tool_tokens

    def count_tokens(self, data: str, include_tool_specs: bool = False) -> int:
        token_size = self._tool_tokens if include_tool_specs else 0
        token_size += len(ApproximateTokenCounter._encoding.encode(data))
        return token_size

    def count_messages_tokens(self, messages: List[BaseMessage]) -> int:
        system_message, rest_messages = _format_messages(messages)
        return self.count_tokens(json.dumps((system_message, rest_messages)))
