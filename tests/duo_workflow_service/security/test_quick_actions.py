import pytest

from duo_workflow_service.security.quick_actions import validate_no_quick_actions


@pytest.mark.parametrize(
    "text,should_err",
    [
        (None, False),
        ("", False),
        ("regular text", False),
        ("inline /merge is fine", False),
        ("/merge", True),
        ("   /approve", True),
        ("first line\n/label bug", True),
        ("\n\n/close\n", True),
        ("```\n/close in code block\n```", True),
    ],
)
def test_validate_no_quick_actions(text, should_err):
    err = validate_no_quick_actions(text)
    assert (err is not None) == should_err


@pytest.mark.parametrize(
    "field,expected_prefix",
    [
        ("description", "Description contains GitLab quick actions"),
        ("body", "Body contains GitLab quick actions"),
    ],
)
def test_validate_no_quick_actions_message_field_prefix(field, expected_prefix):
    err = validate_no_quick_actions("/close", field=field)
    assert err is not None
    assert err.startswith(expected_prefix)
