# pylint: disable=direct-environment-variable-reference

import os
from typing import Literal, Optional, Union

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_vertexai.model_garden import ChatAnthropicVertex
from langsmith import tracing_context
from pydantic import BaseModel, field_validator

from ai_gateway.models import KindAnthropicModel
from duo_workflow_service.interceptors.feature_flag_interceptor import (
    current_feature_flag_context,
)


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
    location: str = ""
    project_id: str = ""
    model_name: str = ""

    def __init__(self, **data):
        # Set defaults before calling parent init
        if "model_name" not in data:
            data["model_name"] = self._get_model_name()
        if "project_id" not in data:
            data["project_id"] = self._get_project_id()
        if "location" not in data:
            data["location"] = self._get_location()
        super().__init__(**data)

    @staticmethod
    def _get_model_name() -> str:
        feature_flags = current_feature_flag_context.get()
        if "duo_workflow_claude_sonnet_4" in feature_flags:
            return "claude-sonnet-4@20250514"
        if "duo_workflow_claude_3_7" in feature_flags:
            return "claude-3-7-sonnet@20250219"
        return "claude-3-5-sonnet-v2@20241022"

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


def create_chat_model(
    config: Union[AnthropicConfig, VertexConfig],
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

    raise ValueError(
        f"Unsupported config type: {type(config).__name__}. "
        "Must be either AnthropicConfig or VertexConfig"
    )


def validate_llm_access(config: Optional[Union[AnthropicConfig, VertexConfig]] = None):
    if config is None:
        try:
            config = VertexConfig()
        except RuntimeError:
            config = AnthropicConfig(model_name=KindAnthropicModel.CLAUDE_3_7_SONNET.value) 

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
