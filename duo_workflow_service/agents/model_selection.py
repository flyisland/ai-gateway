"""
Temporary approach: model selection doesn't support feature flags and doesn't work for the agentic features
"""

from typing import Optional

from ai_gateway.model_metadata import (
    ModelSelectionMetadata,
    TypeModelMetadata,
    current_model_metadata_context,
)
from lib.feature_flags import FeatureFlag, is_feature_enabled
from lib.internal_events.event_enum import CategoryEnum

__all__ = ["resolve_model_from_prompt_registry"]


def resolve_model_from_prompt_registry(
    workflow_type: CategoryEnum,
) -> Optional[TypeModelMetadata]:
    model_metadata = current_model_metadata_context.get()
    if model_metadata:
        return model_metadata

    model_metadata = None
    if (
        workflow_type == CategoryEnum.WORKFLOW_SOFTWARE_DEVELOPMENT
        and is_feature_enabled(FeatureFlag.FLOW_SOFTWARE_DEVELOPMENT_OPENAI_GPT_5)
    ):
        model_metadata = ModelSelectionMetadata(name="gpt_5")

    elif workflow_type == CategoryEnum.WORKFLOW_CHAT and is_feature_enabled(
        FeatureFlag.DUO_AGENTIC_CHAT_OPENAI_GPT_5
    ):
        model_metadata = ModelSelectionMetadata(name="gpt_5")

    return model_metadata
