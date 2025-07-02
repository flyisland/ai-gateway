from unittest.mock import AsyncMock

import pytest

from duo_workflow_service.gitlab.gitlab_project import (
    fetch_project_data,
    fetch_project_languages,
)


@pytest.mark.asyncio
async def test_fetch_project_data_success():
    gitlab_client = AsyncMock()
    # Mock response for project data
    gitlab_client.aget.return_value = {
        "id": 123,
        "description": "Test Project",
        "name": "test-project",
        "http_url_to_repo": "http://example.com/test-project.git",
    }

    project_id = 123
    project = await fetch_project_data(gitlab_client, project_id)

    # Verify the call: fetch project details
    gitlab_client.aget.assert_called_once_with(
        path=f"/api/v4/projects/{project_id}", parse_json=True
    )

    assert project["id"] == 123
    assert project["description"] == "Test Project"
    assert project["name"] == "test-project"
    assert project["http_url_to_repo"] == "http://example.com/test-project.git"


@pytest.mark.asyncio
async def test_fetch_project_data_with_invalid_project_id():
    gitlab_client = AsyncMock()
    # Mock response that simulates an error (e.g., 404)
    gitlab_client.aget.side_effect = Exception("Project not found")

    project_id = 999
    with pytest.raises(Exception, match="Project not found"):
        await fetch_project_data(gitlab_client, project_id)

    gitlab_client.aget.assert_called_once_with(
        path=f"/api/v4/projects/{project_id}", parse_json=True
    )


@pytest.mark.asyncio
async def test_fetch_project_languages_success():
    gitlab_client = AsyncMock()
    gitlab_client.aget.return_value = {
        "Python": 45.2,
        "JavaScript": 30.8,
        "TypeScript": 20.1,
        "CSS": 3.9,
    }

    project_id = 123
    languages = await fetch_project_languages(gitlab_client, project_id)

    gitlab_client.aget.assert_called_once_with(
        path=f"/api/v4/projects/{project_id}/languages", parse_json=True
    )

    assert languages["Python"] == 45.2
    assert languages["JavaScript"] == 30.8
    assert languages["TypeScript"] == 20.1
    assert languages["CSS"] == 3.9


@pytest.mark.asyncio
async def test_fetch_project_languages_api_error():
    gitlab_client = AsyncMock()
    gitlab_client.aget.side_effect = Exception("API Error")

    project_id = 123
    languages = await fetch_project_languages(gitlab_client, project_id)

    gitlab_client.aget.assert_called_once_with(
        path=f"/api/v4/projects/{project_id}/languages", parse_json=True
    )

    # Should return empty dict on error
    assert languages == {}
