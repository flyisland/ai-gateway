from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.tools import ToolException

from duo_workflow_service.gitlab.resource_resolver import resolve_identifier_to_path


@pytest.fixture(name="gitlab_client_mock")
def gitlab_client_mock_fixture():
    mock = Mock()
    mock.aget = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_non_numeric_identifier():
    path = await resolve_identifier_to_path(Mock(), "ns%2Fproject", "project")
    assert path == "ns/project"


@pytest.mark.asyncio
async def test_numeric_project_id(gitlab_client_mock):
    mock_response = Mock()
    mock_response.is_success.return_value = True
    mock_response.body = {"path_with_namespace": "resolved/project"}
    gitlab_client_mock.aget = AsyncMock(return_value=mock_response)

    path = await resolve_identifier_to_path(gitlab_client_mock, "42", "project")

    assert path == "resolved/project"
    gitlab_client_mock.aget.assert_called_once_with("/api/v4/projects/42")


@pytest.mark.asyncio
async def test_numeric_group_id(gitlab_client_mock):
    mock_response = Mock()
    mock_response.is_success.return_value = True
    mock_response.body = {"full_path": "my-group"}
    gitlab_client_mock.aget = AsyncMock(return_value=mock_response)

    path = await resolve_identifier_to_path(gitlab_client_mock, "123", "namespace")

    assert path == "my-group"
    gitlab_client_mock.aget.assert_called_once_with("/api/v4/groups/123")


@pytest.mark.asyncio
async def test_api_failure(gitlab_client_mock):
    mock_response = Mock()
    mock_response.is_success.return_value = False
    mock_response.status_code = 404
    mock_response.body = "Not found"
    gitlab_client_mock.aget = AsyncMock(return_value=mock_response)

    with pytest.raises(ToolException):
        await resolve_identifier_to_path(gitlab_client_mock, "999", "project")


@pytest.mark.asyncio
async def test_missing_path_in_response(gitlab_client_mock):
    mock_response = Mock()
    mock_response.is_success.return_value = True
    mock_response.body = {}
    gitlab_client_mock.aget = AsyncMock(return_value=mock_response)

    with pytest.raises(ToolException, match="Could not resolve project full path"):
        await resolve_identifier_to_path(gitlab_client_mock, "42", "project")
