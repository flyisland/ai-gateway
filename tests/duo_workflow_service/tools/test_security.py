import json
from unittest.mock import AsyncMock, Mock

import pytest

from duo_workflow_service.tools.security import (
    ListVulnerabilities,
    ListVulnerabilitiesInput,
)

# Common URL test parameters
URL_SUCCESS_CASES = [
    # Test with only URL
    (
        "https://gitlab.com/namespace/project",
        None,
        "/api/v4/projects/namespace%2Fproject/vulnerabilities",
    ),
    # Test with URL and matching project_id
    (
        "https://gitlab.com/namespace/project",
        "namespace%2Fproject",
        "/api/v4/projects/namespace%2Fproject/vulnerabilities",
    ),
]

URL_ERROR_CASES = [
    # URL and project_id both given, but don't match
    (
        "https://gitlab.com/namespace/project",
        "different%2Fproject",
        "Project ID mismatch",
    ),
    # URL given isn't a valid GitLab URL
    (
        "https://example.com/not-gitlab",
        None,
        "Failed to parse URL",
    ),
]


@pytest.fixture
def vulnerability_data():
    """Fixture for common vulnerability data."""
    return {
        "id": 1,
        "title": "Test Vulnerability",
        "severity": "high",
        "state": "detected",
    }


@pytest.fixture
def gitlab_client_mock():
    return Mock()


@pytest.fixture
def metadata(gitlab_client_mock):
    return {
        "gitlab_client": gitlab_client_mock,
        "gitlab_host": "gitlab.com",
    }


async def tool_url_success_response(
    tool,
    url,
    project_id,
    gitlab_client_mock,
    response_data,
    **kwargs,
):
    gitlab_client_mock.aget = AsyncMock(return_value=response_data)

    response = await tool._arun(
        url=url, project_id=project_id, **kwargs
    )

    return response


async def assert_tool_url_error(
    tool,
    url,
    project_id,
    error_contains,
    gitlab_client_mock,
    **kwargs,
):
    response = await tool._arun(
        url=url, project_id=project_id, **kwargs
    )

    error_response = json.loads(response)
    assert "error" in error_response
    assert error_contains in error_response["error"]

    gitlab_client_mock.aget.assert_not_called()


@pytest.mark.asyncio
async def test_list_vulnerabilities(gitlab_client_mock, metadata, vulnerability_data):
    gitlab_client_mock.aget = AsyncMock(return_value=vulnerability_data)

    tool = ListVulnerabilities(metadata=metadata)

    input_data = {
        "project_id": 1,
    }

    response = await tool.arun(input_data)

    expected_response = json.dumps({"vulnerabilities": vulnerability_data})
    assert response == expected_response

    gitlab_client_mock.aget.assert_called_once_with(
        path="/api/v4/projects/1/vulnerabilities",
        parse_json=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,project_id,expected_path",
    URL_SUCCESS_CASES,
)
async def test_list_vulnerabilities_with_url_success(
    url,
    project_id,
    expected_path,
    gitlab_client_mock,
    metadata,
    vulnerability_data,
):
    tool = ListVulnerabilities(metadata=metadata)

    response = await tool_url_success_response(
        tool=tool,
        url=url,
        project_id=project_id,
        gitlab_client_mock=gitlab_client_mock,
        response_data=vulnerability_data,
    )

    expected_response = json.dumps({"vulnerabilities": vulnerability_data})
    assert response == expected_response

    gitlab_client_mock.aget.assert_called_once_with(
        path=expected_path,
        parse_json=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,project_id,error_contains",
    URL_ERROR_CASES,
)
async def test_list_vulnerabilities_with_url_error(
    url, project_id, error_contains, gitlab_client_mock, metadata
):
    tool = ListVulnerabilities(metadata=metadata)

    await assert_tool_url_error(
        tool=tool,
        url=url,
        project_id=project_id,
        error_contains=error_contains,
        gitlab_client_mock=gitlab_client_mock,
    )


@pytest.mark.asyncio
async def test_list_vulnerabilities_with_filters(gitlab_client_mock, metadata, vulnerability_data):
    gitlab_client_mock.aget = AsyncMock(return_value=vulnerability_data)

    tool = ListVulnerabilities(metadata=metadata)

    input_data = {
        "project_id": 1,
        "severity": "high",
        "state": "detected",
        "report_type": "sast",
        "scanner": "bandit",
        "has_resolution": True,
        "include_false_positives": False,
    }

    response = await tool.arun(input_data)

    expected_response = json.dumps({"vulnerabilities": vulnerability_data})
    assert response == expected_response

    gitlab_client_mock.aget.assert_called_once_with(
        path="/api/v4/projects/1/vulnerabilities",
        params={
            "severity": "high",
            "state": "detected",
            "report_type": "sast",
            "scanner": "bandit",
            "has_resolution": True,
            "include_false_positives": False,
        },
        parse_json=False,
    )


@pytest.mark.asyncio
async def test_list_vulnerabilities_exception(gitlab_client_mock, metadata):
    gitlab_client_mock.aget = AsyncMock(side_effect=Exception("API Error"))

    tool = ListVulnerabilities(metadata=metadata)

    response = await tool.arun({"project_id": 1})

    error_response = json.loads(response)
    assert "error" in error_response
    assert "API Error" in error_response["error"]


@pytest.mark.parametrize(
    "input_data,expected_message",
    [
        (
            ListVulnerabilitiesInput(project_id=42),
            "List vulnerabilities in project 42",
        ),
        (
            ListVulnerabilitiesInput(url="https://gitlab.com/namespace/project"),
            "List vulnerabilities in https://gitlab.com/namespace/project",
        ),
    ],
)
def test_list_vulnerabilities_format_display_message(input_data, expected_message):
    tool = ListVulnerabilities(metadata={})
    assert tool.format_display_message(input_data) == expected_message 