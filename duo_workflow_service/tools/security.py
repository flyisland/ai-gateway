import json
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

class ListVulnerabilitiesInput(BaseModel):
    project_full_path: str = Field(
        description="The full path of the GitLab project (e.g., 'namespace/project' or 'group/subgroup/project')",
    )
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
    description: str = """List security vulnerabilities in a GitLab project using GraphQL.

    The project must be specified using its full path (e.g., 'namespace/project' or 'group/subgroup/project').

    For example:
    - Given the project path 'namespace/project', the tool call would be:
        list_vulnerabilities(project_full_path="namespace/project")
    """
    args_schema: Type[BaseModel] = ListVulnerabilitiesInput  # type: ignore

    async def _arun(self, **kwargs: Any) -> str:
        project_full_path = kwargs.pop("project_full_path")
        fetch_all_pages = kwargs.pop("fetch_all_pages", True)
        per_page = kwargs.pop("per_page", 100)

        # Build GraphQL query
        query = """
        query($projectFullPath: ID!, $first: Int, $after: String) {
          project(fullPath: $projectFullPath) {
            vulnerabilities(first: $first, after: $after) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                id
                title
                severity
                reportType
                state
                scanner {
                  id
                  name
                }
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
                    "projectFullPath": project_full_path,
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
        return f"List vulnerabilities in project {args.project_full_path}"
