import pytest
from langchain_core.messages import HumanMessage

from duo_workflow_service.token_counter.approximate_token_counter import (
    ApproximateTokenCounter,
)


def test_approximat_token_counter():
    messages = [
        HumanMessage(content="This is a single message"),
        HumanMessage(content="This is another single message"),
    ]

    token_counter = ApproximateTokenCounter()
    assert token_counter.get_tool_tokens() == pytest.approx(40283, abs=300)

    assert token_counter.count_messages_tokens(
        messages, include_tool_specs=False
    ) == pytest.approx(44, abs=5)

    assert token_counter.count_messages_tokens(
        messages, include_tool_specs=True
    ) == pytest.approx(40327, abs=300)

    sample_text = """Many words map to one token, but some don't: indivisible.

Unicode characters like emojis may be split into many tokens containing the underlying bytes: 🤚🏾

Sequences of characters commonly found next to each other may be grouped together: 1234567890"""
    assert token_counter.count_str_tokens(
        sample_text, include_tool_specs=False
    ) == pytest.approx(53, abs=5)
    assert token_counter.count_str_tokens(
        sample_text, include_tool_specs=True
    ) == pytest.approx(40336, abs=300)
