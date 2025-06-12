import json
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool
from duo_workflow_service.tools.gitlab_resource_input import ProjectResourceInput

PROJECT_IDENTIFICATION_DESCRIPTION = """To identify the project you must provide either:
- project_id parameter, or
- A GitLab URL like:
  - https://gitlab.com/namespace/project
  - https://gitlab.com/group/subgroup/project
"""


class ListVulnerabilitiesInput(ProjectResourceInput):
    per_page: Optional[int] = Field(
        default=100,
        description="Number of results per page (default: 100, max: 100).",
    )
    page: Optional[int] = Field(
        default=1,
        description="Page number to fetch (default: 1).",
    )
    fetch_all_pages: Optional[bool] = Field(
        default=True,
        description="Whether to fetch all pages of results (default: True).",
    )


class ListVulnerabilities(DuoBaseTool):
    name: str = "list_vulnerabilities"
    description: str = f"""List security vulnerabilities in a GitLab project.

    {PROJECT_IDENTIFICATION_DESCRIPTION}

    For example:
    - Given project_id 13, the tool call would be:
        list_vulnerabilities(project_id=13)
    - Given the URL https://gitlab.com/namespace/project, the tool call would be:
        list_vulnerabilities(url="https://gitlab.com/namespace/project")
    """
    args_schema: Type[BaseModel] = ListVulnerabilitiesInput  # type: ignore

    async def _arun(self, **kwargs: Any) -> str:
        url = kwargs.pop("url", None)
        project_id = kwargs.pop("project_id", None)
        fetch_all_pages = kwargs.pop("fetch_all_pages", True)
        per_page = kwargs.pop("per_page", 100)
        page = kwargs.pop("page", 1)

        project_id, errors = self._validate_project_url(url, project_id)

        if errors:
            return json.dumps({"error": "; ".join(errors)})

        params = {k: v for k, v in kwargs.items() if v is not None}
        params["per_page"] = per_page
        params["page"] = page

        all_vulnerabilities = []
        current_page = page
        total_pages = None

        try:
            while True:
                params["page"] = current_page
                response = await self.gitlab_client.aget(
                    path=f"/api/v4/projects/{project_id}/vulnerabilities",
                    params=params,
                    parse_json=True,
                )

                vulnerabilities = response
                all_vulnerabilities.extend(vulnerabilities)

                # Get total pages from headers if available
                if total_pages is None and hasattr(self.gitlab_client, "last_response"):
                    total_pages = int(
                        self.gitlab_client.last_response.headers.get("X-Total-Pages", 0)
                    )

                # Break if we're not fetching all pages or if we've reached the last page
                if (
                    not fetch_all_pages
                    or len(vulnerabilities) < per_page
                    or (total_pages and current_page >= total_pages)
                ):
                    break

                current_page += 1

            return json.dumps(
                {
                    "vulnerabilities": all_vulnerabilities,
                    "pagination": {
                        "total_items": len(all_vulnerabilities),
                        "total_pages": total_pages,
                        "current_page": current_page,
                        "per_page": per_page,
                    },
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: ListVulnerabilitiesInput) -> str:
        if args.url:
            return f"List vulnerabilities in {args.url}"
        return f"List vulnerabilities in project {args.project_id}"
