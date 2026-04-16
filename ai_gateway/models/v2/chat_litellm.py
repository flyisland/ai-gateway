from collections.abc import Callable, Sequence
from typing import Any, Literal, Optional, Union, override

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from litellm import add_known_models, register_model
from pydantic import BaseModel

from ai_gateway.models.base import validate_custom_endpoint
from ai_gateway.vendor.langchain_litellm.litellm import ChatLiteLLM as _LChatLiteLLM

__all__ = ["ChatLiteLLM"]

# Workaround until LitelLM updates their model list
register_model(
    {
        "anthropic.claude-opus-4-7": {
            "cache_creation_input_token_cost": 6.25e-06,
            "cache_read_input_token_cost": 5e-07,
            "input_cost_per_token": 5e-06,
            "litellm_provider": "bedrock_converse",
            "max_input_tokens": 1000000,
            "max_output_tokens": 128000,
            "max_tokens": 128000,
            "mode": "chat",
            "output_cost_per_token": 2.5e-05,
            "search_context_cost_per_query": {
                "search_context_size_high": 0.01,
                "search_context_size_low": 0.01,
                "search_context_size_medium": 0.01,
            },
            "supports_assistant_prefill": False,
            "supports_computer_use": True,
            "supports_function_calling": True,
            "supports_pdf_input": True,
            "supports_prompt_caching": True,
            "supports_reasoning": True,
            "supports_response_schema": True,
            "supports_tool_choice": True,
            "supports_vision": True,
            "tool_use_system_prompt_tokens": 346,
            "supports_native_structured_output": True,
        },
        "global.anthropic.claude-opus-4-7": {
            "cache_creation_input_token_cost": 6.25e-06,
            "cache_read_input_token_cost": 5e-07,
            "input_cost_per_token": 5e-06,
            "litellm_provider": "bedrock_converse",
            "max_input_tokens": 1000000,
            "max_output_tokens": 128000,
            "max_tokens": 128000,
            "mode": "chat",
            "output_cost_per_token": 2.5e-05,
            "search_context_cost_per_query": {
                "search_context_size_high": 0.01,
                "search_context_size_low": 0.01,
                "search_context_size_medium": 0.01,
            },
            "supports_assistant_prefill": False,
            "supports_computer_use": True,
            "supports_function_calling": True,
            "supports_pdf_input": True,
            "supports_prompt_caching": True,
            "supports_reasoning": True,
            "supports_response_schema": True,
            "supports_tool_choice": True,
            "supports_vision": True,
            "tool_use_system_prompt_tokens": 346,
            "supports_native_structured_output": True,
        },
        "us.anthropic.claude-opus-4-7": {
            "cache_creation_input_token_cost": 6.875e-06,
            "cache_read_input_token_cost": 5.5e-07,
            "input_cost_per_token": 5.5e-06,
            "litellm_provider": "bedrock_converse",
            "max_input_tokens": 1000000,
            "max_output_tokens": 128000,
            "max_tokens": 128000,
            "mode": "chat",
            "output_cost_per_token": 2.75e-05,
            "search_context_cost_per_query": {
                "search_context_size_high": 0.01,
                "search_context_size_low": 0.01,
                "search_context_size_medium": 0.01,
            },
            "supports_assistant_prefill": False,
            "supports_computer_use": True,
            "supports_function_calling": True,
            "supports_pdf_input": True,
            "supports_prompt_caching": True,
            "supports_reasoning": True,
            "supports_response_schema": True,
            "supports_tool_choice": True,
            "supports_vision": True,
            "tool_use_system_prompt_tokens": 346,
            "supports_native_structured_output": True,
        },
        "eu.anthropic.claude-opus-4-7": {
            "cache_creation_input_token_cost": 6.875e-06,
            "cache_read_input_token_cost": 5.5e-07,
            "input_cost_per_token": 5.5e-06,
            "litellm_provider": "bedrock_converse",
            "max_input_tokens": 1000000,
            "max_output_tokens": 128000,
            "max_tokens": 128000,
            "mode": "chat",
            "output_cost_per_token": 2.75e-05,
            "search_context_cost_per_query": {
                "search_context_size_high": 0.01,
                "search_context_size_low": 0.01,
                "search_context_size_medium": 0.01,
            },
            "supports_assistant_prefill": False,
            "supports_computer_use": True,
            "supports_function_calling": True,
            "supports_pdf_input": True,
            "supports_prompt_caching": True,
            "supports_reasoning": True,
            "supports_response_schema": True,
            "supports_tool_choice": True,
            "supports_vision": True,
            "tool_use_system_prompt_tokens": 346,
            "supports_native_structured_output": True,
        },
        "au.anthropic.claude-opus-4-7": {
            "cache_creation_input_token_cost": 6.875e-06,
            "cache_read_input_token_cost": 5.5e-07,
            "input_cost_per_token": 5.5e-06,
            "litellm_provider": "bedrock_converse",
            "max_input_tokens": 1000000,
            "max_output_tokens": 128000,
            "max_tokens": 128000,
            "mode": "chat",
            "output_cost_per_token": 2.75e-05,
            "search_context_cost_per_query": {
                "search_context_size_high": 0.01,
                "search_context_size_low": 0.01,
                "search_context_size_medium": 0.01,
            },
            "supports_assistant_prefill": False,
            "supports_computer_use": True,
            "supports_function_calling": True,
            "supports_pdf_input": True,
            "supports_prompt_caching": True,
            "supports_reasoning": True,
            "supports_response_schema": True,
            "supports_tool_choice": True,
            "supports_vision": True,
            "tool_use_system_prompt_tokens": 346,
            "supports_native_structured_output": True,
        },
    }
)

add_known_models()


class ChatLiteLLM(_LChatLiteLLM):
    custom_models_enabled: bool = False

    @override
    def bind(self, **kwargs: Any) -> Runnable[LanguageModelInput, AIMessage]:
        validate_custom_endpoint(
            self.custom_models_enabled,
            api_base=kwargs.get("api_base"),
            api_key=kwargs.get("api_key"),
        )
        return super().bind(**kwargs)

    @override
    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type[BaseModel] | Callable | BaseTool],
        tool_choice: Optional[
            Union[dict, str, Literal["auto", "none", "required", "any"], bool]
        ] = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        kwargs.pop("web_search_options", None)  # Not yet supported for LiteLLM

        return super().bind_tools(tools, tool_choice=tool_choice, **kwargs)
