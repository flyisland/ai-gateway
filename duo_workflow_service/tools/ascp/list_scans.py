from typing import Any, ClassVar, Optional, Type

from langchain_core.tools import ToolException
from pydantic import BaseModel, Field

from duo_workflow_service.tools.ascp.queries import LIST_ASCP_SCANS_QUERY
from duo_workflow_service.tools.ascp.types import ScanTypeLiteral
from duo_workflow_service.tools.ascp.utils import parse_graphql_errors
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool
from duo_workflow_service.tools.tier_access_checker import (
    LICENSED_FEATURE_SECURITY_DASHBOARD,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


class ListAscpScansResponse(BaseModel):
    """Response model for listing ASCP scans."""

    scans: list[dict[str, Any]]
    page_info: dict[str, Any]


class ListAscpScansInput(BaseModel):
    """Input model for the ListAscpScans tool."""

    project_path: str = Field(
        description='Full path of the project (e.g., "namespace/project").',
    )
    scan_type: Optional[ScanTypeLiteral] = Field(
        default=None,
        description='Optional filter: "FULL" or "INCREMENTAL". Omit to list all scans.',
    )
    first: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Number of scans per page (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}).",
    )
    after: Optional[str] = Field(
        default=None,
        description="Cursor for pagination (from previous response page_info.end_cursor).",
    )


class ListAscpScans(DuoBaseTool):
    """Tool for listing ASCP (Application Security Collaboration Platform) scans for a project.

    On success, returns JSON with scans list and pagination info. On error, raises ToolException with error details.
    """

    tier_check_licensed_feature: ClassVar[str] = LICENSED_FEATURE_SECURITY_DASHBOARD

    name: str = "ascp_list_scans"
    description: str = """
    List ASCP scans for a GitLab project.

    Use this tool when you need to see existing full or incremental ASCP scans for
    a project. Provide the project full path (e.g., 'namespace/project').
    Optionally filter by scan_type ('FULL' or 'INCREMENTAL') and use first/after
    for pagination. To create a new scan, use ascp_create_scan instead.

    Example:
        ascp_list_scans(project_path="my-group/my-project")
        ascp_list_scans(project_path="my-group/my-project", scan_type="FULL", first=10)
    """
    args_schema: Type[BaseModel] = ListAscpScansInput

    def format_display_message(
        self, args: ListAscpScansInput, _tool_response: Any = None
    ) -> str:
        if args.scan_type:
            return f"List ASCP scans for {args.project_path} (type={args.scan_type})"
        return f"List ASCP scans for {args.project_path}"

    async def _execute(self, **kwargs: Any) -> str:
        project_path = kwargs["project_path"]
        scan_type = kwargs.get("scan_type")
        first = kwargs.get("first", DEFAULT_PAGE_SIZE)
        after = kwargs.get("after")

        variables: dict[str, Any] = {
            "fullPath": project_path,
            "first": first,
        }
        if scan_type is not None:
            variables["scanType"] = scan_type
        if after is not None:
            variables["after"] = after

        response = await self.gitlab_client.graphql(
            LIST_ASCP_SCANS_QUERY,
            variables,
        )

        if not isinstance(response, dict):
            raise ToolException("GraphQL returned no response or invalid format")

        graphql_errors = response.get("errors")
        if graphql_errors:
            messages = parse_graphql_errors(graphql_errors)
            exc_message = "; ".join(messages)
            raise ToolException(exc_message)

        project = response.get("project")
        if project is None:
            raise ToolException("Project not found or access denied")

        ascp_scans = project.get("ascpScans") or {}
        nodes = ascp_scans.get("nodes") or []
        page_info = ascp_scans.get("pageInfo") or {}

        page_info_dict = {
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor"),
        }
        return ListAscpScansResponse(
            scans=nodes, page_info=page_info_dict
        ).model_dump_json()
