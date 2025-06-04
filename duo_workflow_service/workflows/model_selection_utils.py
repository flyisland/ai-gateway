# model_config_utils.py
import os
from typing import Union

from ai_gateway.models import KindAnthropicModel
from duo_workflow_service.interceptors.feature_flag_interceptor import (
    current_feature_flag_context,
)
from duo_workflow_service.llm_factory import AnthropicConfig, VertexConfig


def get_sonnet_4_config_with_feature_flag(
    parent_get_model_config_method,
) -> Union[AnthropicConfig, VertexConfig]:
    """Get model configuration with Sonnet 4 feature flag check.

    This utility function encapsulates the common logic for determining
    which Sonnet 4 model configuration to use based on feature flags
    and deployment environment.

    Args:
        parent_get_model_config_method: The parent class's _get_model_config
            method to fall back to if feature flag is not set.

    Returns:
        Union[AnthropicConfig, VertexConfig]: The appropriate model configuration.
    """
    feature_flags = current_feature_flag_context.get()
    _vertex_project_id = os.getenv("DUO_WORKFLOW__VERTEX_PROJECT_ID")

    # Check if Sonnet 4 is enabled for software development graph
    if "duo_workflow_claude_sonnet_4" in feature_flags:
        if bool(_vertex_project_id and len(_vertex_project_id) > 1):
            # Use Sonnet 4 on Vertex
            return VertexConfig(
                model_name=KindAnthropicModel.CLAUDE_SONNET_4_VERTEX.value
            )
        else:
            # Use Sonnet 4 on Anthropic API
            return AnthropicConfig(model_name=KindAnthropicModel.CLAUDE_SONNET_4.value)

    # Fall back to parent implementation if flag not set
    return parent_get_model_config_method()
