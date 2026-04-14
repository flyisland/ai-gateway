# pylint: disable=file-naming-for-tests
import json
from unittest.mock import AsyncMock, Mock

import pytest

from duo_workflow_service.tools.ascp.create_component import (
    CreateAscpComponent,
    CreateAscpComponentInput,
)


@pytest.fixture(name="gitlab_client_mock")
def gitlab_client_mock_fixture():
    mock = Mock()
    mock.graphql = AsyncMock()
    return mock


@pytest.fixture(name="metadata")
def metadata_fixture(gitlab_client_mock):
    return {
        "gitlab_client": gitlab_client_mock,
        "gitlab_host": "gitlab.com",
    }


@pytest.fixture(name="created_component_data_fixture")
def created_component_data_fixture_func():
    """Fixture for created ASCP component data."""
    return {
        "id": "gid://gitlab/Ascp::Component/1",
        "title": "Authentication Service",
        "description": None,
        "subDirectory": "services/auth",
        "expectedUserBehavior": None,
        "scan": {"id": "gid://gitlab/Ascp::Scan/1"},
        "createdAt": "2025-02-19T10:00:00.000Z",
        "updatedAt": "2025-02-19T10:00:00.000Z",
    }


@pytest.mark.asyncio
async def test_ascp_create_component_success(
    gitlab_client_mock,
    metadata,
    created_component_data_fixture,
):
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "ascpComponentCreate": {
                "component": created_component_data_fixture,
                "errors": [],
            },
        },
    )

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Authentication Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )

    response_json = json.loads(response)
    assert "errors" in response_json
    assert "response" in response_json
    assert response_json["errors"] == []
    assert response_json["response"]["component"] == created_component_data_fixture
    assert response_json["response"]["component"]["title"] == "Authentication Service"
    assert response_json["response"]["component"]["subDirectory"] == "services/auth"

    gitlab_client_mock.graphql.assert_called_once()
    call_args = gitlab_client_mock.graphql.call_args[0]
    assert "ascpComponentCreate" in call_args[0]
    assert call_args[1]["input"]["projectPath"] == "namespace/project"
    assert call_args[1]["input"]["title"] == "Authentication Service"
    assert call_args[1]["input"]["subDirectory"] == "services/auth"
    assert call_args[1]["input"]["scanId"] == "gid://gitlab/Ascp::Scan/1"
    assert "description" not in call_args[1]["input"]
    assert "expectedUserBehavior" not in call_args[1]["input"]


@pytest.mark.asyncio
async def test_ascp_create_component_with_optional_fields(
    gitlab_client_mock,
    metadata,
    created_component_data_fixture,
):
    component_data = {
        **created_component_data_fixture,
        "description": "Handles user authentication",
        "expectedUserBehavior": "Users log in via OAuth",
    }
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "ascpComponentCreate": {
                "component": component_data,
                "errors": [],
            },
        },
    )

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Authentication Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
        description="Handles user authentication",
        expected_user_behavior="Users log in via OAuth",
    )

    response_json = json.loads(response)
    assert response_json["errors"] == []
    assert (
        response_json["response"]["component"]["description"]
        == "Handles user authentication"
    )
    assert (
        response_json["response"]["component"]["expectedUserBehavior"]
        == "Users log in via OAuth"
    )

    call_args = gitlab_client_mock.graphql.call_args[0]
    assert call_args[1]["input"]["description"] == "Handles user authentication"
    assert call_args[1]["input"]["expectedUserBehavior"] == "Users log in via OAuth"


@pytest.mark.asyncio
async def test_ascp_create_component_graphql_top_level_errors(
    gitlab_client_mock,
    metadata,
):
    """Top-level GraphQL errors (e.g. auth failures) are surfaced in the errors field."""
    gitlab_client_mock.graphql = AsyncMock(
        return_value={"errors": [{"message": "Unauthorized"}]},
    )

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Auth Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )

    response_json = json.loads(response)
    assert isinstance(response_json["errors"], list)
    assert response_json["errors"] == ["Unauthorized"]
    assert response_json["response"]["raw_response"] == {
        "errors": [{"message": "Unauthorized"}]
    }


@pytest.mark.asyncio
async def test_ascp_create_component_response_without_key(
    gitlab_client_mock,
    metadata,
):
    """When response has no ascpComponentCreate key and no top-level errors, returns generic error."""
    gitlab_client_mock.graphql = AsyncMock(return_value={})

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Auth Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )

    response_json = json.loads(response)
    assert "errors" in response_json
    assert "response" in response_json
    assert isinstance(response_json["errors"], list)
    assert response_json["errors"][0] == "Failed to create ASCP component."


@pytest.mark.asyncio
async def test_ascp_create_component_mutation_errors(
    gitlab_client_mock,
    metadata,
):
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "ascpComponentCreate": {
                "component": None,
                "errors": ["Scan not found"],
            },
        },
    )

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Auth Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/999",
    )

    response_json = json.loads(response)
    assert "errors" in response_json
    assert "response" in response_json
    assert isinstance(response_json["errors"], list)
    assert "Scan not found" in response_json["errors"][0]


@pytest.mark.asyncio
async def test_ascp_create_component_multiple_errors(
    gitlab_client_mock,
    metadata,
):
    """When mutation returns multiple errors, all appear in the tool response."""
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "ascpComponentCreate": {
                "component": None,
                "errors": ["Error one", "Error two"],
            },
        },
    )

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Auth Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )

    response_json = json.loads(response)
    assert response_json["errors"] == ["Error one", "Error two"]


@pytest.mark.asyncio
async def test_ascp_create_component_exception(
    gitlab_client_mock,
    metadata,
):
    gitlab_client_mock.graphql = AsyncMock(
        side_effect=ConnectionError("Network failure"),
    )

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Auth Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )

    response_json = json.loads(response)
    assert "errors" in response_json
    assert "response" in response_json
    assert isinstance(response_json["errors"], list)
    assert len(response_json["errors"]) == 1
    assert "ascp_create_component" in response_json["errors"][0]
    assert "ConnectionError" in response_json["errors"][0]
    assert "Network failure" in response_json["errors"][0]


@pytest.mark.asyncio
async def test_ascp_create_component_malformed_response(
    gitlab_client_mock,
    metadata,
):
    """Non-dict response (e.g. None) must return JSON with error list."""
    gitlab_client_mock.graphql = AsyncMock(return_value=None)

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Auth Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )

    response_json = json.loads(response)
    assert "errors" in response_json
    assert "response" in response_json
    assert isinstance(response_json["errors"], list)
    assert any(
        "no response or invalid format" in msg for msg in response_json["errors"]
    )


@pytest.mark.asyncio
async def test_ascp_create_component_missing_component_id(
    gitlab_client_mock,
    metadata,
):
    """When mutation returns component without id, tool returns error."""
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "ascpComponentCreate": {
                "component": {"title": "Auth Service"},
                "errors": [],
            },
        },
    )

    tool = CreateAscpComponent(metadata=metadata)

    response = await tool._arun(
        project_path="namespace/project",
        title="Auth Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )

    response_json = json.loads(response)
    assert "errors" in response_json
    assert isinstance(response_json["errors"], list)
    assert "Failed to create ASCP component" in response_json["errors"][0]


def test_ascp_create_component_format_display_message():
    """Test format_display_message returns expected string."""
    tool = CreateAscpComponent(metadata={})
    input_data = CreateAscpComponentInput(
        project_path="my-group/my-project",
        title="Authentication Service",
        sub_directory="services/auth",
        scan_id="gid://gitlab/Ascp::Scan/1",
    )
    expected_message = (
        "Create ASCP component 'Authentication Service' in my-group/my-project"
    )
    assert tool.format_display_message(input_data) == expected_message
