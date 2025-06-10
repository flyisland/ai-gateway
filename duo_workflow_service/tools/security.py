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
    severity: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by severity. Possible values: critical, high, medium, low, unknown, info.",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by confidence. Possible values: confirmed, high, medium, low, unknown, experimental.",
    )
    report_type: Optional[str] = Field(
        default=None,
        description=(
            "Filter vulnerabilities by report type. Possible values: sast, dependency_scanning, "
            "container_scanning, dast, secret_detection, coverage_fuzzing, api_fuzzing."
        ),
    )
    state: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by state. Possible values: detected, confirmed, dismissed, resolved.",
    )
    scanner: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by scanner.",
    )
    scanner_id: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by scanner ID.",
    )
    has_resolution: Optional[bool] = Field(
        default=None,
        description="Filter vulnerabilities by whether they have a resolution.",
    )
    has_issues: Optional[bool] = Field(
        default=None,
        description="Filter vulnerabilities by whether they have issues.",
    )
    include_false_positives: Optional[bool] = Field(
        default=None,
        description="Include false positives in the results.",
    )
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
    description: str = f"""List security vulnerabilities in a GitLab project using GraphQL.

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

        project_id, errors = self._validate_project_url(url, project_id)

        if errors:
            return json.dumps({"error": "; ".join(errors)})

        # Build GraphQL query
        query = """
        query($projectId: ID!, $first: Int, $after: String) {
          project(fullPath: $projectId) {
            vulnerabilities(first: $first, after: $after) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                id
                title
                severity
                confidence
                reportType
                state
                scanner {
                  id
                  name
                }
                hasResolution
                hasIssues
                falsePositive
              }
            }
          }
        }
        """

        all_vulnerabilities = []
        cursor = None

        try:
            while True:
                variables = {
                    "projectId": project_id,
                    "first": per_page,
                    "after": cursor
                }

                response = await self.gitlab_client.apost(
                    path="/api/graphql",
                    body=json.dumps({
                        "query": query,
                        "variables": variables
                    })
                )

                vulnerabilities = response["data"]["project"]["vulnerabilities"]["nodes"]
                all_vulnerabilities.extend(vulnerabilities)

                page_info = response["data"]["project"]["vulnerabilities"]["pageInfo"]
                
                if not fetch_all_pages or not page_info["hasNextPage"]:
                    break

                cursor = page_info["endCursor"]

            return json.dumps({
                "vulnerabilities": all_vulnerabilities,
                "pagination": {
                    "total_items": len(all_vulnerabilities)
                }
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: ListVulnerabilitiesInput) -> str:
        if args.url:
            return f"List vulnerabilities in {args.url}"
        return f"List vulnerabilities in project {args.project_id}"
