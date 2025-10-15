# Test file for FireworksModelMetadata functionality
from unittest.mock import patch

import pytest

from ai_gateway.model_metadata import FireworksModelMetadata, create_model_metadata
from ai_gateway.model_selection import LLMDefinition, ModelSelectionConfig


class TestFireworksModelMetadata:
    def test_fireworks_to_params_with_all_fields(self):
        """Test that to_params includes all fields when provided."""
        metadata = FireworksModelMetadata(
            provider="fireworks_ai",
            name="test_model",
            endpoint="https://api.fireworks.ai/v1",
            api_key="test_key",
            model_identifier="test_identifier",
            using_cache=True,
            session_id="test_session_id",
        )
        params = metadata.to_params()
        assert params["model"] == "test_identifier"
        assert params["api_key"] == "test_key"
        assert params["api_base"] == "https://api.fireworks.ai/v1"
        assert params["using_cache"] is True
        assert params["session_id"] == "test_session_id"
