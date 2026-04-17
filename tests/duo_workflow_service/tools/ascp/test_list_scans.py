import json
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.tools import ToolException

from duo_workflow_service.tools.ascp.list_scans import ListAscpScans, ListAscpScansInput


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


@pytest.fixture(name="list_scans_response_fixture")
def list_scans_response_fixture_func():
    """Fixture for list ASCP scans API response (nodes + pageInfo)."""
    return {
        "nodes": [
            {
                "id": "gid://gitlab/Ascp::Scan/1",
                "scanSequence": 1,
                "scanType": "FULL",
                "commitSha": "abc123",
                "baseCommitSha": None,
                "baseScan": None,
                "createdAt": "2025-02-19T10:00:00.000Z",
                "updatedAt": "2025-02-19T10:00:00.000Z",
            },
        ],
        "pageInfo": {
            "hasNextPage": False,
            "endCursor": None,
        },
    }


@pytest.mark.asyncio
async def test_ascp_list_scans_success(
    gitlab_client_mock,
    metadata,
    list_scans_response_fixture,
):
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "project": {
                "ascpScans": list_scans_response_fixture,
            },
        },
    )

    tool = ListAscpScans(metadata=metadata)

    response = await tool._arun(project_path="namespace/project")

    response_json = json.loads(response)
    assert "scans" in response_json
    assert "page_info" in response_json
    assert response_json["scans"] == list_scans_response_fixture["nodes"]
    assert response_json["page_info"]["has_next_page"] is False
    assert response_json["page_info"]["end_cursor"] is None

    gitlab_client_mock.graphql.assert_called_once()
    call_args = gitlab_client_mock.graphql.call_args[0]
    assert "ListAscpScans" in call_args[0] or "ascpScans" in call_args[0]
    assert call_args[1]["fullPath"] == "namespace/project"


@pytest.mark.asyncio
async def test_ascp_list_scans_with_scan_type(
    gitlab_client_mock,
    metadata,
    list_scans_response_fixture,
):
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "project": {
                "ascpScans": list_scans_response_fixture,
            },
        },
    )

    tool = ListAscpScans(metadata=metadata)

    await tool._arun(
        project_path="namespace/project",
        scan_type="FULL",
    )

    call_args = gitlab_client_mock.graphql.call_args[0]
    assert call_args[1]["scanType"] == "FULL"


@pytest.mark.asyncio
async def test_ascp_list_scans_with_pagination(
    gitlab_client_mock,
    metadata,
    list_scans_response_fixture,
):
    list_scans_response_fixture["pageInfo"] = {
        "hasNextPage": True,
        "endCursor": "cursor123",
    }
    gitlab_client_mock.graphql = AsyncMock(
        return_value={
            "project": {
                "ascpScans": list_scans_response_fixture,
            },
        },
    )

    tool = ListAscpScans(metadata=metadata)

    await tool._arun(
        project_path="namespace/project",
        first=10,
        after="cursor123",
    )

    call_args = gitlab_client_mock.graphql.call_args[0]
    assert call_args[1]["first"] == 10
    assert call_args[1]["after"] == "cursor123"


@pytest.mark.asyncio
async def test_ascp_list_scans_full_request_and_response(
    gitlab_client_mock,
    metadata,
):
    """Full round-trip: send all four query variables, receive full response shape."""
    # Request: fullPath, scanType, first, after (from list_ascp_scans.graphql 2-5)
    project_path = "my-group/my-project"
    scan_type = "FULL"
    first = 10
    after = "cursor123"

    # Response: full ascpScans shape (nodes + pageInfo from list_ascp_scans.graphql 8-26)
    full_response = {
        "project": {
            "ascpScans": {
                "nodes": [
                    {
                        "id": "gid://gitlab/Ascp::Scan/1",
                        "scanSequence": 1,
                        "scanType": "FULL",
                        "commitSha": "abc123def",
                        "baseCommitSha": None,
                        "baseScan": None,
                        "createdAt": "2025-02-19T10:00:00.000Z",
                        "updatedAt": "2025-02-19T10:00:00.000Z",
                    },
                ],
                "pageInfo": {
                    "hasNextPage": True,
                    "endCursor": "next_cursor_xyz",
                },
            },
        },
    }
    gitlab_client_mock.graphql = AsyncMock(return_value=full_response)

    tool = ListAscpScans(metadata=metadata)
    response = await tool._arun(
        project_path=project_path,
        scan_type=scan_type,
        first=first,
        after=after,
    )

    # Assert request variables sent
    gitlab_client_mock.graphql.assert_called_once()
    call_args = gitlab_client_mock.graphql.call_args[0]
    variables = call_args[1]
    assert variables["fullPath"] == project_path
    assert variables["scanType"] == scan_type
    assert variables["first"] == first
    assert variables["after"] == after

    # Assert response parsed (scans = nodes, page_info from pageInfo)
    response_json = json.loads(response)
    assert "scans" in response_json
    assert "page_info" in response_json
    expected_nodes = full_response["project"]["ascpScans"]["nodes"]
    expected_page_info = full_response["project"]["ascpScans"]["pageInfo"]
    assert response_json["scans"] == expected_nodes
    assert (
        response_json["page_info"]["has_next_page"] == expected_page_info["hasNextPage"]
    )
    assert response_json["page_info"]["end_cursor"] == expected_page_info["endCursor"]


@pytest.mark.asyncio
async def test_ascp_list_scans_project_not_found(
    gitlab_client_mock,
    metadata,
):
    gitlab_client_mock.graphql = AsyncMock(return_value={"project": None})

    tool = ListAscpScans(metadata=metadata)

    with pytest.raises(ToolException) as exc_info:
        await tool._arun(project_path="namespace/project")

    assert "Project not found or access denied" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ascp_list_scans_top_level_graphql_errors(
    gitlab_client_mock,
    metadata,
):
    """When response has top-level GraphQL errors, tool raises ToolException."""
    gitlab_client_mock.graphql = AsyncMock(
        return_value={"errors": [{"message": "Unauthorized"}]}
    )

    tool = ListAscpScans(metadata=metadata)

    with pytest.raises(ToolException) as exc_info:
        await tool._arun(project_path="namespace/project")

    assert "Unauthorized" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ascp_list_scans_malformed_response(
    gitlab_client_mock,
    metadata,
):
    """Non-dict response raises ToolException."""
    gitlab_client_mock.graphql = AsyncMock(return_value=None)

    tool = ListAscpScans(metadata=metadata)

    with pytest.raises(ToolException) as exc_info:
        await tool._arun(project_path="namespace/project")

    assert "no response or invalid format" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ascp_list_scans_exception(
    gitlab_client_mock,
    metadata,
):
    gitlab_client_mock.graphql = AsyncMock(
        side_effect=ConnectionError("Network failure"),
    )

    tool = ListAscpScans(metadata=metadata)

    # Exceptions propagate directly
    with pytest.raises(ConnectionError, match="Network failure"):
        await tool._arun(project_path="namespace/project")


def test_ascp_list_scans_format_display_message():
    """Test format_display_message returns expected string."""
    tool = ListAscpScans(metadata={})
    input_data = ListAscpScansInput(project_path="my-group/my-project")
    expected_message = "List ASCP scans for my-group/my-project"
    assert tool.format_display_message(input_data) == expected_message


def test_ascp_list_scans_format_display_message_with_scan_type():
    """Test format_display_message with scan_type filter."""
    tool = ListAscpScans(metadata={})
    input_data = ListAscpScansInput(
        project_path="my-group/my-project",
        scan_type="FULL",
    )
    expected_message = "List ASCP scans for my-group/my-project (type=FULL)"
    assert tool.format_display_message(input_data) == expected_message
