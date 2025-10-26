from enum import StrEnum
from typing import Annotated, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ModelClassProvider",
    "TypeModelParams",
    "BaseModelParams",
    "ChatLiteLLMParams",
    "ChatAnthropicParams",
    "ChatAmazonQParams",
    "ChatOpenAIParams",
]


class ModelClassProvider(StrEnum):
    LITE_LLM = "litellm"
    ANTHROPIC = "anthropic"
    AMAZON_Q = "amazon_q"
    OPENAI = "openai"
    CORTEX = "cortex"


class BaseModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
    max_retries: int | None = 1
    model_class_provider: str | None = None
    custom_llm_provider: str | None = None


class ChatLiteLLMParams(BaseModelParams):
    model_class_provider: Literal[ModelClassProvider.LITE_LLM]
    custom_llm_provider: str | None = None
    """Easily switch to huggingface, replicate, together ai, sagemaker, etc.
    Example - https://litellm.vercel.app/docs/providers/vllm#batch-completion"""


class ChatAnthropicParams(BaseModelParams):
    model_class_provider: Literal[ModelClassProvider.ANTHROPIC]
    default_headers: Mapping[str, str] | None = None


class ChatAmazonQParams(BaseModelParams):
    model_class_provider: Literal[ModelClassProvider.AMAZON_Q]
    default_headers: Mapping[str, str] | None = None


class ChatOpenAIParams(BaseModelParams):
    model_class_provider: Literal[ModelClassProvider.OPENAI]

class ChatCortexParams(BaseModelParams):
    model_class_provider: Literal[ModelClassProvider.CORTEX]

    database: str | None = None
    cortex_schema: str | None = None
    agent_name: str | None = None
    api_token: str | None = None
    base_url: str | None = None


TypeModelParams = Annotated[
    ChatLiteLLMParams | ChatAnthropicParams | ChatAmazonQParams | ChatOpenAIParams | ChatCortexParams,
    Field(discriminator="model_class_provider"),
]
