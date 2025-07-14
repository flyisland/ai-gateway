# pylint: disable=direct-environment-variable-reference

import os
from typing import Literal, Optional, Union

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_cerebras import ChatCerebras
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_vertexai.model_garden import ChatAnthropicVertex
from langsmith import tracing_context
from pydantic import BaseModel, Field, field_validator

from ai_gateway.models import KindAnthropicModel


class ModelConfig(BaseModel):
    max_retries: int = 6
    model_name: str
    provider: str


class AnthropicConfig(ModelConfig):
    provider: Literal["anthropic"] = "anthropic"

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate that model_name matches a value from KindAnthropicModel."""
        valid_models = [model.value for model in KindAnthropicModel]
        if v not in valid_models:
            raise ValueError(
                f"model_name '{v}' is not valid. Must be one of: {', '.join(valid_models)}"
            )
        return v


class VertexConfig(ModelConfig):
    provider: Literal["vertex"] = "vertex"

    @staticmethod
    def _get_model_name() -> str:
        return KindAnthropicModel.CLAUDE_SONNET_4_VERTEX.value

    @staticmethod
    def _get_project_id() -> str:
        project_id = os.environ.get("DUO_WORKFLOW__VERTEX_PROJECT_ID")
        if not project_id or len(project_id) < 1:
            raise RuntimeError("DUO_WORKFLOW__VERTEX_PROJECT_ID needs to be set")
        return project_id

    @staticmethod
    def _get_location() -> str:
        # This is where we'll need to add support for multi-region access to Anthropic
        # on Vertex.
        # Supported locations:
        # https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/use-claude#regions
        location = os.environ.get("DUO_WORKFLOW__VERTEX_LOCATION")
        if not location or len(location) < 1:
            raise RuntimeError("DUO_WORKFLOW__VERTEX_LOCATION needs to be set")
        return location

    model_name: str = Field(default_factory=_get_model_name)
    project_id: str = Field(default_factory=_get_project_id)
    location: str = Field(default_factory=_get_location)


class CerebrasConfig(ModelConfig):
    provider: Literal["cerebras"] = "cerebras"

    @staticmethod
    def _get_model_name() -> str:
        return "llama-3.3-70b"
    
    model_name: str = Field(default_factory=_get_model_name)


def create_chat_model(
    config: Union[AnthropicConfig, VertexConfig, CerebrasConfig],
    **kwargs,
) -> BaseChatModel:

    if isinstance(config, AnthropicConfig):
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_api_key and len(anthropic_api_key) > 1:
            return ChatAnthropic(
                model_name=config.model_name,
                **kwargs,
                max_retries=config.max_retries,
            )
        raise RuntimeError("ANTHROPIC_API_KEY needs to be set for Anthropic provider")

    if isinstance(config, VertexConfig):
        return ChatAnthropicVertex(
            model_name=config.model_name,
            project=config.project_id,
            location=config.location,
            max_retries=config.max_retries,
            **kwargs,
        )

    if isinstance(config, CerebrasConfig):
        cerebras_api_key = os.environ.get("CEREBRAS_API_KEY")
        if cerebras_api_key and len(cerebras_api_key) > 1:
            return ChatCerebras(
                model=config.model_name,
                api_key=cerebras_api_key,
                max_retries=config.max_retries,
                **kwargs,
            )
        raise RuntimeError("CEREBRAS_API_KEY needs to be set for Cerebras provider")

    raise ValueError(
        f"Unsupported config type: {type(config).__name__}. "
        "Must be either AnthropicConfig, VertexConfig, or CerebrasConfig"
    )


def validate_llm_access(config: Optional[Union[AnthropicConfig, VertexConfig, CerebrasConfig]] = None):
    if config is None:
        try:
            config = VertexConfig()
        except RuntimeError:
            config = AnthropicConfig(
                model_name=KindAnthropicModel.CLAUDE_SONNET_4.value
            )

    log = structlog.stdlib.get_logger("server")
    anthropic_client = create_chat_model(config=config)

    with tracing_context(enabled=False):
        anthropic_response = anthropic_client.invoke(
            "Answer in under 80 characters: What LLM am I talking to?"
        )

    content = anthropic_response.content
    # feature flags are not yet loaded, so logging the model name here could be misleading if the model name depends on
    # feature flags.
    log.info(str(content))
