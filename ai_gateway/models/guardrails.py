from typing import Optional

from ai_gateway.config import ConfigBedrockGuardrail

BEDROCK_GUARDRAIL_PROVIDERS = frozenset({"bedrock", "bedrock_converse"})


def bedrock_guardrail_params(
    custom_llm_provider: Optional[str],
    bedrock_guardrail_config: Optional[ConfigBedrockGuardrail],
) -> dict[str, dict]:
    """Build LiteLLM guardrail parameters for Bedrock providers.

    Args:
        custom_llm_provider: The LiteLLM custom provider string (e.g. "bedrock", "bedrock_converse").
        bedrock_guardrail_config: The guardrail configuration, or None to disable guardrails.

    Returns:
        A dict with a "guardrailConfig" key when guardrails should be applied, or an empty dict otherwise.
    """
    if not bedrock_guardrail_config:
        return {}
    if custom_llm_provider not in BEDROCK_GUARDRAIL_PROVIDERS:
        return {}
    return {"guardrailConfig": bedrock_guardrail_config.model_dump(exclude_none=True)}
