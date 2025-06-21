import json
from typing import Any

from duo_workflow_service.gitlab.http_client import GitlabHttpClient
from duo_workflow_service.gitlab.url_parser import GitLabUrlParser


async def fetch_gitlab_issue(
    client: GitlabHttpClient, issue_url: str, project: dict[str, Any]
) -> dict[str, Any]:
    gitlab_host = GitLabUrlParser.extract_host_from_url(project["web_url"])

    project_id, issue_iid = GitLabUrlParser.parse_issue_url(issue_url, gitlab_host)

    response = await client.aget(
        path=f"/api/v4/projects/{project_id}/issues/{issue_iid}",
        parse_json=False,
    )
    return json.loads(response)
