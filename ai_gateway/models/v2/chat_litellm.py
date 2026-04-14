from collections.abc import Callable, Sequence
from typing import Any, Literal, Optional, Union, override

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from ai_gateway.models.base import validate_custom_endpoint
from ai_gateway.vendor.langchain_litellm.litellm import ChatLiteLLM as _LChatLiteLLM

__all__ = ["ChatLiteLLM"]


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
