from typing import Any, Dict, Tuple, TypedDict

from duo_workflow_service.gitlab.http_client import GitlabHttpClient


class Project(TypedDict):
    id: int
    description: str
    name: str
    http_url_to_repo: str
    web_url: str


async def fetch_project_data(
    client: GitlabHttpClient, project_id: int
) -> Tuple[Project, Dict[str, Any]]:
    project = await client.aget(
        path=f"/api/v4/projects/{project_id}",
        parse_json=True,
    )

    return project


async def fetch_project_languages(client: GitlabHttpClient, project_id: int) -> dict:
    try:
        project_languages = await client.aget(
            path=f"/api/v4/projects/{project_id}/languages",
            parse_json=True,
        )
        return project_languages or {}
    except Exception:
        return {}
