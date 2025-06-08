import json
from unittest.mock import AsyncMock, Mock

import pytest

from duo_workflow_service.tools.security import (
    ListVulnerabilities,
    ListVulnerabilitiesInput,
)

# Common URL test parameters for GraphQL
URL_SUCCESS_CASES = [
    # Test with only URL
    (
        "https://gitlab.com/namespace/project",
        None,
        "namespace/project",
    ),
    # Test with URL and matching project_id
    (
        "https://gitlab.com/namespace/project",
        "namespace/project",
        "namespace/project",
    ),
]

URL_ERROR_CASES = [
    # URL and project_id both given, but don't match
    (
        "https://gitlab.com/namespace/project",
        "different/project",
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
def graphql_vulnerability_response():
    """Fixture for GraphQL vulnerability response data."""
    return {
        "data": {
            "project": {
                "id": "gid://gitlab/Project/1",
                "name": "test-project",
                "fullPath": "namespace/project",
                "vulnerabilities": {
                    "nodes": [
                        {
                            "id": "gid://gitlab/Vulnerability/1",
                            "title": "Test Vulnerability",
                            "severity": "HIGH",
                            "state": "DETECTED",
                            "reportType": "SAST",
                            "description": "A test vulnerability",
                            "scanner": {
                                "name": "Bandit",
                                "vendor": "GitLab",
                                "externalId": "bandit"
                            },
                            "identifiers": [
                                {
                                    "name": "CVE-2021-1234",
                                    "value": "CVE-2021-1234",
                                    "type": "CVE",
                                    "externalType": "cve",
                                    "externalId": "CVE-2021-1234",
                                    "url": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2021-1234"
                                }
                            ],
                            "location": {
                                "file": "app.py",
                                "startLine": 10,
                                "endLine": 12
                            },
                            "project": {
                                "id": "gid://gitlab/Project/1",
                                "name": "test-project",
                                "fullPath": "namespace/project"
                            },
                            "detectedAt": "2023-01-01T00:00:00Z",
                            "createdAt": "2023-01-01T00:00:00Z",
                            "updatedAt": "2023-01-01T00:00:00Z",
                            "dismissedAt": None,
                            "dismissedBy": None,
                            "resolvedAt": None,
                            "resolvedBy": None,
                            "confirmedAt": None,
                            "confirmedBy": None,
                            "falsePositive": False,
                            "hasIssues": False,
                            "hasResolution": True,
                            "hasSolutions": True,
                            "userNotesCount": 0,
                            "vulnerabilityPath": "/namespace/project/-/security/vulnerabilities/1",
                            "links": [
                                {
                                    "name": "CVE Details",
                                    "url": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2021-1234"
                                }
                            ]
                        }
                    ],
                    "pageInfo": {
                        "hasNextPage": False,
                        "hasPreviousPage": False,
                        "startCursor": "cursor1",
                        "endCursor": "cursor1"
                    },
                    "count": 1
                }
            }
        }
    }


@pytest.fixture
def empty_graphql_response():
    """Fixture for empty GraphQL response."""
    return {
        "data": {
            "project": {
                "id": "gid://gitlab/Project/1",
                "name": "test-project",
                "fullPath": "namespace/project",
                "vulnerabilities": {
                    "nodes": [],
                    "pageInfo": {
                        "hasNextPage": False,
                        "hasPreviousPage": False,
                        "startCursor": None,
                        "endCursor": None
                    },
                    "count": 0
                }
            }
        }
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
    gitlab_client_mock.apost = AsyncMock(return_value=response_data)

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

    gitlab_client_mock.apost.assert_not_called()


@pytest.mark.asyncio
async def test_list_vulnerabilities(gitlab_client_mock, metadata, graphql_vulnerability_response):
    gitlab_client_mock.apost = AsyncMock(return_value=graphql_vulnerability_response)

    tool = ListVulnerabilities(metadata=metadata)

    input_data = {
        "project_id": "namespace/project",
    }

    response = await tool.arun(input_data)
    response_data = json.loads(response)

    assert "vulnerabilities" in response_data
    assert len(response_data["vulnerabilities"]) == 1
    assert response_data["vulnerabilities"][0]["title"] == "Test Vulnerability"
    assert "project" in response_data
    assert "pagination" in response_data
    assert "total_count" in response_data

    # Verify GraphQL query was called
    gitlab_client_mock.apost.assert_called_once()
    call_args = gitlab_client_mock.apost.call_args
    assert call_args[1]["path"] == "/api/graphql"
    assert "query" in json.loads(call_args[1]["body"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,project_id,expected_project_path",
    URL_SUCCESS_CASES,
)
async def test_list_vulnerabilities_with_url_success(
    url,
    project_id,
    expected_project_path,
    gitlab_client_mock,
    metadata,
    graphql_vulnerability_response,
):
    tool = ListVulnerabilities(metadata=metadata)

    response = await tool_url_success_response(
        tool=tool,
        url=url,
        project_id=project_id,
        gitlab_client_mock=gitlab_client_mock,
        response_data=graphql_vulnerability_response,
    )

    response_data = json.loads(response)
    assert "vulnerabilities" in response_data
    assert len(response_data["vulnerabilities"]) == 1

    # Verify GraphQL query was called with correct project path
    gitlab_client_mock.apost.assert_called_once()
    call_args = gitlab_client_mock.apost.call_args
    assert call_args[1]["path"] == "/api/graphql"

    query_body = json.loads(call_args[1]["body"])
    assert f'project(fullPath: "{expected_project_path}")' in query_body["query"]


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
async def test_list_vulnerabilities_with_filters(gitlab_client_mock, metadata, graphql_vulnerability_response):
    gitlab_client_mock.apost = AsyncMock(return_value=graphql_vulnerability_response)

    tool = ListVulnerabilities(metadata=metadata)

    input_data = {
        "project_id": "namespace/project",
        "severity": "high",
        "state": "detected",
        "report_type": "sast",
        "scanner": "bandit",
        "has_resolution": True,
        "include_false_positives": False,
    }

    response = await tool.arun(input_data)
    response_data = json.loads(response)

    assert "vulnerabilities" in response_data
    assert len(response_data["vulnerabilities"]) == 1

    # Verify GraphQL query was called with filters
    gitlab_client_mock.apost.assert_called_once()
    call_args = gitlab_client_mock.apost.call_args
    assert call_args[1]["path"] == "/api/graphql"

    query_body = json.loads(call_args[1]["body"])
    query = query_body["query"]

    # Check that GraphQL filters are included
    # Check that GraphQL filters are included
    assert 'severity: ["HIGH"]' in query
    assert 'state: ["DETECTED"]' in query
    assert 'reportType: ["SAST"]' in query
    assert 'scanner: ["bandit"]' in query
    assert 'hasResolution: true' in query
    assert 'includeFalsePositives: false' in query

@pytest.mark.asyncio
async def test_list_vulnerabilities_empty_response(gitlab_client_mock, metadata, empty_graphql_response):
    gitlab_client_mock.apost = AsyncMock(return_value=empty_graphql_response)

    tool = ListVulnerabilities(metadata=metadata)

    input_data = {
        "project_id": "namespace/project",
    }

    response = await tool.arun(input_data)
    response_data = json.loads(response)

    assert "vulnerabilities" in response_data
    assert len(response_data["vulnerabilities"]) == 0
    assert response_data["total_count"] == 0


@pytest.mark.asyncio
async def test_list_vulnerabilities_graphql_error(gitlab_client_mock, metadata):
    # Simulate GraphQL error response
    error_response = {
        "errors": [
            {
                "message": "Project not found",
                "locations": [{"line": 2, "column": 3}],
                "path": ["project"]
            }
        ]
    }
    gitlab_client_mock.apost = AsyncMock(return_value=error_response)

    tool = ListVulnerabilities(metadata=metadata)

    input_data = {
        "project_id": "nonexistent/project",
    }

    response = await tool.arun(input_data)
    response_data = json.loads(response)

    assert "error" in response_data
    assert "GraphQL errors" in response_data["error"]


@pytest.mark.asyncio
async def test_list_vulnerabilities_exception(gitlab_client_mock, metadata):
    gitlab_client_mock.apost = AsyncMock(side_effect=Exception("API Error"))

    tool = ListVulnerabilities(metadata=metadata)

    response = await tool.arun({"project_id": "namespace/project"})

    error_response = json.loads(response)
    assert "error" in error_response
    assert "API Error" in error_response["error"]


@pytest.mark.parametrize(
    "input_data,expected_message",
    [
        (
            ListVulnerabilitiesInput(project_id="namespace/project"),
            "List vulnerabilities in project namespace/project (using GraphQL)",
        ),
        (
            ListVulnerabilitiesInput(url="https://gitlab.com/namespace/project"),
            "List vulnerabilities in https://gitlab.com/namespace/project (using GraphQL)",
        ),
    ],
)
def test_list_vulnerabilities_format_display_message(input_data, expected_message):
    tool = ListVulnerabilities(metadata={})
    assert tool.format_display_message(input_data) == expected_message
