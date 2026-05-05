import json
from typing import Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from duo_workflow_service.errors.typing import TierAccessDeniedException
from duo_workflow_service.gitlab.http_client import GitLabHttpResponse
from duo_workflow_service.tools.tier_access_checker import TierAccessChecker


@pytest.fixture(name="gitlab_client_mock")
def gitlab_client_mock_fixture():
    mock = Mock()
    mock.aget = AsyncMock()
    mock.apost = AsyncMock()
    return mock


@pytest.fixture(name="checker")
def checker_fixture(gitlab_client_mock):
    return TierAccessChecker(
        tool_name="tier_gated_tool",
        gitlab_client=gitlab_client_mock,
    )


def _graphql_response(available: bool, required_plan: Optional[str] = None):
    return GitLabHttpResponse(
        200,
        {
            "data": {
                "project": {
                    "licensedFeatureAvailability": {
                        "available": available,
                        "requiredPlan": required_plan,
                    }
                }
            }
        },
    )


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=True,
)
async def test_check_tier_access_raises_when_unavailable(
    _, checker, gitlab_client_mock
):
    gitlab_client_mock.apost = AsyncMock(
        return_value=_graphql_response(available=False, required_plan="ultimate")
    )

    with pytest.raises(TierAccessDeniedException) as exc_info:
        await checker.check_tier_access(
            "SECURITY_DASHBOARD",
            "[]",
            {"project_full_path": "my-group/my-project"},
        )

    assert exc_info.value.required_plan == "ultimate"


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=True,
)
async def test_check_tier_access_passes_when_available(_, checker, gitlab_client_mock):
    gitlab_client_mock.apost = AsyncMock(return_value=_graphql_response(available=True))

    await checker.check_tier_access(
        "SECURITY_DASHBOARD",
        "[]",
        {"project_full_path": "my-group/my-project"},
    )


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=False,
)
async def test_check_tier_access_skipped_on_old_gitlab(_, checker, gitlab_client_mock):
    await checker.check_tier_access(
        "SECURITY_DASHBOARD",
        "[]",
        {"project_full_path": "my-group/my-project"},
    )

    gitlab_client_mock.apost.assert_not_called()


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=True,
)
async def test_check_tier_access_swallows_graphql_errors(
    _, checker, gitlab_client_mock
):
    gitlab_client_mock.apost = AsyncMock(side_effect=Exception("network error"))

    await checker.check_tier_access(
        "SECURITY_DASHBOARD",
        "[]",
        {"project_full_path": "my-group/my-project"},
    )


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=True,
)
async def test_check_tier_access_uses_namespace_scope_for_groups(
    _, checker, gitlab_client_mock
):
    ns_response = GitLabHttpResponse(
        200,
        {
            "data": {
                "namespace": {
                    "licensedFeatureAvailability": {
                        "available": False,
                        "requiredPlan": "premium",
                    }
                }
            }
        },
    )
    gitlab_client_mock.apost = AsyncMock(return_value=ns_response)

    with pytest.raises(TierAccessDeniedException) as exc_info:
        await checker.check_tier_access(
            "EPICS",
            "[]",
            {"group_id": "my-group"},
        )

    assert exc_info.value.required_plan == "premium"
    call_body = json.loads(gitlab_client_mock.apost.call_args.kwargs["body"])
    assert (
        "namespace(fullPath:" in call_body["query"] or "namespace" in call_body["query"]
    )


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=True,
)
async def test_check_tier_access_skips_non_empty_response(
    _, checker, gitlab_client_mock
):
    """No tier check when the tool result is not empty/error."""
    await checker.check_tier_access(
        "SECURITY_DASHBOARD",
        json.dumps({"items": [1, 2, 3]}),
        {"project_full_path": "my-group/my-project"},
    )

    gitlab_client_mock.apost.assert_not_called()


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=True,
)
async def test_check_tier_access_skips_no_feature(_, checker, gitlab_client_mock):
    """No tier check when feature is None."""
    await checker.check_tier_access(
        None,
        "[]",
        {"project_full_path": "my-group/my-project"},
    )

    gitlab_client_mock.apost.assert_not_called()


@pytest.mark.parametrize(
    "result,expected",
    [
        (json.dumps({"error": "forbidden"}), True),
        (json.dumps([]), True),
        (json.dumps({"items": []}), True),
        (json.dumps({"items": [1, 2]}), False),
        (json.dumps({"count": 5}), False),
        ("not json", False),
        (42, False),
    ],
)
def test_is_empty_or_error_response(result, expected):
    assert TierAccessChecker._is_empty_or_error_response(result) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs,project,expected",
    [
        ({"project_full_path": "ns/project"}, None, ("ns/project", "project")),
        ({"unrelated": "value"}, None, None),
        (
            {"unrelated": "value"},
            {
                "id": 42,
                "web_url": "http://gdk.test:3000/free-group/test-project",
            },
            ("free-group/test-project", "project"),
        ),
    ],
)
async def test_get_resource_path(kwargs, project, expected):
    checker = TierAccessChecker(
        tool_name="test_tool",
        gitlab_client=Mock(),
        project=project,
    )
    result = await checker._get_resource_path(kwargs)
    assert result == expected


@pytest.mark.asyncio
async def test_get_resource_path_from_group_id(gitlab_client_mock):
    mock_response = Mock()
    mock_response.is_success.return_value = True
    mock_response.body = {"full_path": "my-group"}
    gitlab_client_mock.aget = AsyncMock(return_value=mock_response)

    checker = TierAccessChecker(
        tool_name="test_tool",
        gitlab_client=gitlab_client_mock,
    )
    result = await checker._get_resource_path({"group_id": "123"})

    assert result == ("my-group", "namespace")


@pytest.mark.asyncio
@patch(
    "duo_workflow_service.tools.tier_access_checker.supports_licensed_feature_availability",
    return_value=True,
)
async def test_check_tier_access_skips_when_no_resource_path(
    _, checker, gitlab_client_mock
):
    """No GraphQL call when resource path cannot be resolved from kwargs."""
    await checker.check_tier_access(
        "SECURITY_DASHBOARD",
        "[]",
        {},
    )

    gitlab_client_mock.apost.assert_not_called()
