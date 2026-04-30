import json
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.tools import ToolException

from duo_workflow_service.gitlab.http_client import GitLabHttpResponse
from duo_workflow_service.tools.start_flow import StartFlow, StartFlowInput


@pytest.fixture(name="gitlab_client_mock")
def gitlab_client_mock_fixture():
    return Mock()


@pytest.fixture(name="project")
def project_fixture():
    return {"id": 42, "web_url": "https://gitlab.com/group/project"}


@pytest.fixture(name="metadata")
def metadata_fixture(gitlab_client_mock, project):
    return {
        "gitlab_client": gitlab_client_mock,
        "gitlab_host": "gitlab.com",
        "project": project,
    }


@pytest.fixture(name="metadata_no_project")
def metadata_no_project_fixture(gitlab_client_mock):
    return {
        "gitlab_client": gitlab_client_mock,
        "gitlab_host": "gitlab.com",
    }


@pytest.fixture(name="tool")
def tool_fixture(metadata):
    return StartFlow(metadata=metadata)


@pytest.fixture(name="tool_no_project")
def tool_no_project_fixture(metadata_no_project):
    return StartFlow(metadata=metadata_no_project)


@pytest.mark.asyncio
async def test_execute_success(tool, gitlab_client_mock):
    gitlab_client_mock.apost = AsyncMock(
        return_value=GitLabHttpResponse(
            status_code=201,
            body={"id": "wf-123"},
        )
    )

    result = await tool.arun(
        {
            "workflow_definition": "fix_pipeline/v1",
            "goal": "https://gitlab.com/group/project/-/pipelines/99",
            "merge_request_url": "https://gitlab.com/group/project/-/merge_requests/1",
            "pipeline_source_branch": "feature-branch",
        }
    )

    data = json.loads(result)
    assert data["status"] == "started"
    assert data["workflow_id"] == "wf-123"
    assert data["flow_name"] == "fix_pipeline/v1"
    assert (
        data["session_url"]
        == "https://gitlab.com/group/project/-/automate/agent-sessions/wf-123"
    )

    posted_body = json.loads(gitlab_client_mock.apost.call_args.kwargs["body"])
    assert posted_body["workflow_definition"] == "fix_pipeline/v1"
    assert posted_body["goal"] == "https://gitlab.com/group/project/-/pipelines/99"
    assert posted_body["environment"] == "ambient"
    assert posted_body["start_workflow"] is True
    assert posted_body["project_id"] == 42


@pytest.mark.asyncio
async def test_execute_fix_pipeline_with_merge_request_url_and_source_branch(
    tool, gitlab_client_mock
):
    gitlab_client_mock.apost = AsyncMock(
        return_value=GitLabHttpResponse(status_code=201, body={"id": "wf-fp1"})
    )

    result = await tool.arun(
        {
            "workflow_definition": "fix_pipeline/v1",
            "goal": "https://gitlab.com/group/project/-/pipelines/99",
            "merge_request_url": "https://gitlab.com/group/project/-/merge_requests/1",
            "pipeline_source_branch": "feature-branch",
        }
    )

    data = json.loads(result)
    assert data["status"] == "started"
    assert data["workflow_id"] == "wf-fp1"

    posted_body = json.loads(gitlab_client_mock.apost.call_args.kwargs["body"])
    assert posted_body["additional_context"] == [
        {
            "Category": "merge_request",
            "Content": json.dumps(
                {"url": "https://gitlab.com/group/project/-/merge_requests/1"}
            ),
        },
        {
            "Category": "pipeline",
            "Content": json.dumps({"source_branch": "feature-branch"}),
        },
    ]


@pytest.mark.asyncio
async def test_execute_fix_pipeline_with_merge_request_url_only_raises(
    tool, gitlab_client_mock
):
    with pytest.raises(ToolException, match="source_branch is missing"):
        await tool._execute(
            workflow_definition="fix_pipeline/v1",
            goal="https://gitlab.com/group/project/-/pipelines/99",
            merge_request_url="https://gitlab.com/group/project/-/merge_requests/2",
        )

    gitlab_client_mock.apost.assert_not_called()


@pytest.mark.asyncio
async def test_execute_fix_pipeline_with_source_branch_only_raises(
    tool, gitlab_client_mock
):
    with pytest.raises(ToolException, match="merge_request_url is missing"):
        await tool._execute(
            workflow_definition="fix_pipeline/v1",
            goal="https://gitlab.com/group/project/-/pipelines/99",
            pipeline_source_branch="main",
        )

    gitlab_client_mock.apost.assert_not_called()


@pytest.mark.asyncio
async def test_execute_fix_pipeline_without_optional_params_raises(
    tool, gitlab_client_mock
):
    with pytest.raises(ToolException, match="merge_request_url is missing"):
        await tool._execute(
            workflow_definition="fix_pipeline/v1",
            goal="https://gitlab.com/group/project/-/pipelines/99",
        )

    gitlab_client_mock.apost.assert_not_called()


@pytest.mark.asyncio
async def test_execute_non_fix_pipeline_ignores_merge_request_url_and_source_branch(
    tool, gitlab_client_mock
):
    gitlab_client_mock.apost = AsyncMock(
        return_value=GitLabHttpResponse(status_code=201, body={"id": "wf-fp5"})
    )

    result = await tool.arun(
        {
            "workflow_definition": "developer/v1",
            "goal": "https://gitlab.com/group/project/-/issues/5",
            "merge_request_url": "https://gitlab.com/group/project/-/merge_requests/1",
            "pipeline_source_branch": "feature-branch",
        }
    )

    data = json.loads(result)
    assert data["status"] == "started"

    posted_body = json.loads(gitlab_client_mock.apost.call_args.kwargs["body"])
    assert "additional_context" not in posted_body


@pytest.mark.asyncio
async def test_execute_without_project(tool_no_project, gitlab_client_mock):
    gitlab_client_mock.apost = AsyncMock(
        return_value=GitLabHttpResponse(status_code=201, body={"id": "wf-789"})
    )

    result = await tool_no_project.arun(
        {
            "workflow_definition": "developer/v1",
            "goal": "https://gitlab.com/group/project/-/issues/5",
        }
    )

    data = json.loads(result)
    assert data["status"] == "started"
    assert data["workflow_id"] == "wf-789"
    assert data["session_url"] is None

    posted_body = json.loads(gitlab_client_mock.apost.call_args.kwargs["body"])
    assert "project_id" not in posted_body


@pytest.mark.asyncio
async def test_execute_string_body_response(tool, gitlab_client_mock):
    gitlab_client_mock.apost = AsyncMock(
        return_value=GitLabHttpResponse(
            status_code=201,
            body=json.dumps({"id": "wf-str"}),
        )
    )

    result = await tool.arun({"workflow_definition": "code_review/v1", "goal": "42"})

    data = json.loads(result)
    assert data["workflow_id"] == "wf-str"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 403, 404, 422, 500])
async def test_execute_http_failure(tool, gitlab_client_mock, status_code):
    gitlab_client_mock.apost = AsyncMock(
        return_value=GitLabHttpResponse(status_code=status_code, body="error body")
    )

    # arun converts ToolException into a ToolMessage with the error string
    # when handle_tool_error is truthy (default); use ainvoke on the internal
    # coroutine to surface the raised exception directly.
    with pytest.raises(ToolException) as exc_info:
        await tool._execute(
            workflow_definition="fix_pipeline/v1",
            goal="https://gitlab.com/group/project/-/pipelines/99",
            merge_request_url="https://gitlab.com/group/project/-/merge_requests/1",
            pipeline_source_branch="feature-branch",
        )

    assert str(status_code) in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_exception(tool, gitlab_client_mock):
    gitlab_client_mock.apost = AsyncMock(side_effect=RuntimeError("network error"))

    with pytest.raises(RuntimeError, match="network error"):
        await tool._execute(
            workflow_definition="developer/v1",
            goal="https://gitlab.com/group/project/-/issues/1",
        )


def test_format_display_message_with_workflow_id_and_session_url(tool):
    args = StartFlowInput(
        workflow_definition="fix_pipeline/v1", goal="https://example.com/pipelines/1"
    )
    response = json.dumps(
        {
            "workflow_id": "wf-abc",
            "session_url": "https://gitlab.com/group/project/-/automate/agent-sessions/wf-abc",
        }
    )

    msg = tool.format_display_message(args, response)

    assert "fix_pipeline/v1" in msg
    assert "wf-abc" in msg
    assert "View session" in msg


def test_format_display_message_with_workflow_id_no_session_url(tool):
    args = StartFlowInput(workflow_definition="code_review/v1", goal="99")
    response = json.dumps({"workflow_id": "wf-abc", "session_url": None})

    msg = tool.format_display_message(args, response)

    assert "code_review/v1" in msg
    assert "wf-abc" in msg
    assert "View session" not in msg


@pytest.mark.parametrize(
    "response",
    [
        None,
        "not valid json{{{",
        json.dumps({}),  # missing workflow_id
    ],
)
def test_format_display_message_fallback(tool, response):
    args = StartFlowInput(
        workflow_definition="developer/v1", goal="https://example.com/issues/5"
    )

    msg = tool.format_display_message(args, response)

    assert "developer/v1" in msg
    assert "https://example.com/issues/5" in msg
