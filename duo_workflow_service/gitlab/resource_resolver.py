"""Utilities for resolving GitLab resource identifiers to full paths."""

import urllib.parse

import structlog
from langchain_core.tools import ToolException

from duo_workflow_service.gitlab.http_client import GitlabHttpClient

log = structlog.stdlib.get_logger("workflow")


async def resolve_identifier_to_path(
    gitlab_client: GitlabHttpClient, identifier: str, scope: str
) -> str:
    """Resolve a project/group identifier to its full path.

    Raises:
        ToolException: If the identifier cannot be resolved.
    """
    if identifier.isdigit():
        endpoint = "projects" if scope == "project" else "groups"
        data = await gitlab_client.aget(f"/api/v4/{endpoint}/{identifier}")

        if not data.is_success():
            log.error(
                "Resolve parent path request failed",
                status_code=data.status_code,
                body=data.body,
            )
            raise ToolException(
                f"Failed to resolve {scope} from ID '{identifier}': {data.body}"
            )

        full_path = data.body.get(
            "path_with_namespace" if scope == "project" else "full_path"
        )
        if not full_path:
            raise ToolException(
                f"Could not resolve {scope} full path from ID '{identifier}'"
            )
    else:
        full_path = identifier

    return urllib.parse.unquote(full_path)
