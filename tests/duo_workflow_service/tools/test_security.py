import json
from unittest.mock import AsyncMock, Mock

import pytest

from duo_workflow_service.tools.security import (
    GetProjectVulnerabilities,
    GetProjectVulnerabilitiesInput,
    GetProjectSecurityConfiguration,
    GetProjectSecurityConfigurationInput,
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
def security_config_data():
    """Fixture for common security configuration data."""
    return {
        "auto_fix_enabled": True,
        "auto_fix_enabled_for_containers": True,
        "auto_fix_enabled_for_dependencies": True,
        "auto_fix_enabled_for_vulnerabilities": True,
        "scanners": [
            {
                "name": "sast",
                "enabled": True,
            },
            {
                "name": "dependency_scanning",
                "enabled": True,
            },
        ],
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
async def test_get_project_vulnerabilities(gitlab_client_mock, metadata, vulnerability_data):
    gitlab_client_mock.aget = AsyncMock(return_value=vulnerability_data)

    tool = GetProjectVulnerabilities(metadata=metadata)

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
async def test_get_project_vulnerabilities_with_url_success(
    url,
    project_id,
    expected_path,
    gitlab_client_mock,
    metadata,
    vulnerability_data,
):
    tool = GetProjectVulnerabilities(metadata=metadata)

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
async def test_get_project_vulnerabilities_with_url_error(
    url, project_id, error_contains, gitlab_client_mock, metadata
):
    tool = GetProjectVulnerabilities(metadata=metadata)

    await assert_tool_url_error(
        tool=tool,
        url=url,
        project_id=project_id,
        error_contains=error_contains,
        gitlab_client_mock=gitlab_client_mock,
    )


@pytest.mark.asyncio
async def test_get_project_security_configuration(
    gitlab_client_mock, metadata, security_config_data
):
    gitlab_client_mock.aget = AsyncMock(return_value=security_config_data)

    tool = GetProjectSecurityConfiguration(metadata=metadata)

    input_data = {
        "project_id": 1,
    }

    response = await tool.arun(input_data)

    expected_response = json.dumps({"security_configuration": security_config_data})
    assert response == expected_response

    gitlab_client_mock.aget.assert_called_once_with(
        path="/api/v4/projects/1/security_configuration",
        parse_json=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,project_id,expected_path",
    [
        # Modify paths for security configuration endpoint
        (
            "https://gitlab.com/namespace/project",
            None,
            "/api/v4/projects/namespace%2Fproject/security_configuration",
        ),
        (
            "https://gitlab.com/namespace/project",
            "namespace%2Fproject",
            "/api/v4/projects/namespace%2Fproject/security_configuration",
        ),
    ],
)
async def test_get_project_security_configuration_with_url_success(
    url,
    project_id,
    expected_path,
    gitlab_client_mock,
    metadata,
    security_config_data,
):
    tool = GetProjectSecurityConfiguration(metadata=metadata)

    response = await tool_url_success_response(
        tool=tool,
        url=url,
        project_id=project_id,
        gitlab_client_mock=gitlab_client_mock,
        response_data=security_config_data,
    )

    expected_response = json.dumps({"security_configuration": security_config_data})
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
async def test_get_project_security_configuration_with_url_error(
    url, project_id, error_contains, gitlab_client_mock, metadata
):
    tool = GetProjectSecurityConfiguration(metadata=metadata)

    await assert_tool_url_error(
        tool=tool,
        url=url,
        project_id=project_id,
        error_contains=error_contains,
        gitlab_client_mock=gitlab_client_mock,
    )


@pytest.mark.asyncio
async def test_get_project_vulnerabilities_exception(gitlab_client_mock, metadata):
    gitlab_client_mock.aget = AsyncMock(side_effect=Exception("API Error"))

    tool = GetProjectVulnerabilities(metadata=metadata)

    response = await tool.arun({"project_id": 1})

    error_response = json.loads(response)
    assert "error" in error_response
    assert "API Error" in error_response["error"]


@pytest.mark.asyncio
async def test_get_project_security_configuration_exception(gitlab_client_mock, metadata):
    gitlab_client_mock.aget = AsyncMock(side_effect=Exception("API Error"))

    tool = GetProjectSecurityConfiguration(metadata=metadata)

    response = await tool.arun({"project_id": 1})

    error_response = json.loads(response)
    assert "error" in error_response
    assert "API Error" in error_response["error"]


@pytest.mark.parametrize(
    "input_data,expected_message",
    [
        (
            GetProjectVulnerabilitiesInput(project_id=42),
            "Get vulnerabilities for project 42",
        ),
        (
            GetProjectVulnerabilitiesInput(url="https://gitlab.com/namespace/project"),
            "Get vulnerabilities for project https://gitlab.com/namespace/project",
        ),
    ],
)
def test_get_project_vulnerabilities_format_display_message(input_data, expected_message):
    tool = GetProjectVulnerabilities(metadata={})
    assert tool.format_display_message(input_data) == expected_message


@pytest.mark.parametrize(
    "input_data,expected_message",
    [
        (
            GetProjectSecurityConfigurationInput(project_id=42),
            "Get security configuration for project 42",
        ),
        (
            GetProjectSecurityConfigurationInput(url="https://gitlab.com/namespace/project"),
            "Get security configuration for project https://gitlab.com/namespace/project",
        ),
    ],
)
def test_get_project_security_configuration_format_display_message(input_data, expected_message):
    tool = GetProjectSecurityConfiguration(metadata={})
    assert tool.format_display_message(input_data) == expected_message 