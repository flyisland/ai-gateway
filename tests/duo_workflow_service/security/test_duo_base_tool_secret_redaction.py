"""These tests live in the security test directory intentionally: the tool test
directory's conftest replaces ``_arun`` with a stripped version that skips
security processing, which would make these tests meaningless.  The security
directory has no such fixture so the real ``_arun`` pipeline is exercised.
"""

from typing import Any

import pytest

from duo_workflow_service.security.secret_redaction import REDACTED_PLACEHOLDER
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class SecretReturningTool(DuoBaseTool):
    """Minimal tool whose ``_execute`` returns a caller-controlled value."""

    name: str = "secret_returning_tool"
    description: str = "Tool that returns a pre-set response for testing"
    _response: Any = None

    def set_response(self, response: Any) -> None:
        self._response = response  # pylint: disable=attribute-defined-outside-init

    async def _execute(self, *args: Any, **kwargs: Any) -> Any:
        return self._response


@pytest.mark.asyncio
async def test_arun_redacts_gitlab_token_in_string_response():
    """_arun must redact a GitLab PAT embedded in a plain string response."""
    token = "glpat-AAAAABBBBCCCCDDDDEEEE"
    tool = SecretReturningTool(metadata={})
    tool.set_response(f"see {token} for access")

    result = await tool._arun()

    assert token not in result
    assert REDACTED_PLACEHOLDER in result


@pytest.mark.asyncio
async def test_arun_does_not_modify_normal_string_response():
    """_arun must leave non-secret string responses untouched."""
    tool = SecretReturningTool(metadata={})
    tool.set_response("the project has 3 issues")

    result = await tool._arun()

    assert result == "the project has 3 issues"


@pytest.mark.asyncio
async def test_arun_redacts_secret_in_dict_response():
    """_arun must redact secrets nested inside a dict response."""
    token = "glpat-AAAAABBBBCCCCDDDDEEEE"
    tool = SecretReturningTool(metadata={})
    tool.set_response({"body": f"token: {token}", "id": 1})

    result = await tool._arun()

    assert isinstance(result, dict)
    assert token not in result["body"]
    assert REDACTED_PLACEHOLDER in result["body"]
    assert result["id"] == 1


@pytest.mark.asyncio
async def test_arun_redacts_secret_in_list_response():
    """_arun must redact secrets inside list entries."""
    token = "glpat-AAAAABBBBCCCCDDDDEEEE"
    tool = SecretReturningTool(metadata={})
    tool.set_response(["normal", f"token: {token}"])

    result = await tool._arun()

    assert isinstance(result, list)
    assert result[0] == "normal"
    assert token not in result[1]
    assert REDACTED_PLACEHOLDER in result[1]


@pytest.mark.asyncio
async def test_arun_redacts_aws_key_in_response():
    """_arun must redact AWS access keys."""
    tool = SecretReturningTool(metadata={})
    tool.set_response("key=AKIAIOSFODNN7EXAMPLE")

    result = await tool._arun()

    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert REDACTED_PLACEHOLDER in result


@pytest.mark.asyncio
async def test_arun_passes_through_scalar_response():
    """_arun must return non-string scalars unchanged (e.g. integers)."""
    tool = SecretReturningTool(metadata={})
    tool.set_response(42)

    result = await tool._arun()

    assert result == 42
