import pytest

from ai_gateway.prompts.config import ModelConfig


@pytest.mark.parametrize(
    ("model_params", "expected_model_engine"),
    [
        ({"model_class_provider": "litellm"}, "litellm"),
        (
            {
                "model_class_provider": "litellm",
                "custom_llm_provider": "my_engine",
            },
            "my_engine",
        ),
        ({"model_class_provider": "anthropic"}, "anthropic"),
        ({"model_class_provider": "amazon_q"}, "amazon_q"),
        ({"model_class_provider": "openai"}, "openai"),
    ],
)
def test_model_engine(model_params, expected_model_engine):
    model_config = ModelConfig(params=model_params)
    assert model_config.params.model_engine == expected_model_engine
