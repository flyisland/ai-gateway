from typing import Any, Optional, Type

from langchain_core.tools import ToolException
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from duo_workflow_service.tools.ascp.queries import LIST_ASCP_COMPONENTS_QUERY
from duo_workflow_service.tools.ascp.utils import parse_graphql_errors
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


class ListAscpComponentsResponse(BaseModel):
    """Response model for listing ASCP components."""

    components: list[dict[str, Any]]
    page_info: dict[str, Any]


class ListAscpComponentsInput(BaseModel):
    """Input for listing ASCP components in a project."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    project_path: str = Field(
        description='The full path of the GitLab project (e.g., "namespace/project" or "group/subgroup/project").',
    )
    title: Optional[str] = Field(
        default=None,
        description=(
            "Filter components by title (case-insensitive substring match)."
            " If not specified, all components are returned."
        ),
    )
    sub_directory: Optional[str] = Field(
        default=None,
        description="Filter components by exact subdirectory path. If not specified, all components are returned.",
    )
    first: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Number of components per page (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}).",
    )
    after: Optional[str] = Field(
        default=None,
        description="Cursor for pagination (from previous response page_info.end_cursor).",
    )


class ListAscpComponents(DuoBaseTool):
    """Tool for listing ASCP (Application Security Collaboration Platform) components for a project.

    On success, returns JSON with components list and pagination info. On error, raises ToolException with error
    details.
    """

    name: str = "ascp_list_components"
    description: str = """
    List ASCP components for a GitLab project.

    Use this tool to retrieve the business components registered for an ASCP scan in a
    GitLab project. You can optionally filter by title (partial match) or subdirectory
    (exact match). Use first/after for pagination.

    Example:
        ascp_list_components(project_path="my-group/my-project")
        ascp_list_components(project_path="my-group/my-project", title="auth", first=10)
    """
    args_schema: Type[BaseModel] = ListAscpComponentsInput

    def format_display_message(
        self, args: ListAscpComponentsInput, _tool_response: Any = None
    ) -> str:
        return f"List ASCP components for {args.project_path}"

    async def _execute(self, **kwargs: Any) -> str:
        parsed = ListAscpComponentsInput.model_validate(kwargs)
        variables = parsed.model_dump(by_alias=True, exclude_none=True)
        project_path = parsed.project_path

        response = await self.gitlab_client.graphql(
            LIST_ASCP_COMPONENTS_QUERY,
            variables,
        )

        if not isinstance(response, dict):
            raise ToolException("GraphQL returned no response or invalid format")

        graphql_errors = response.get("errors")
        if graphql_errors:
            messages = parse_graphql_errors(graphql_errors)
            exc_message = "; ".join(messages)
            raise ToolException(exc_message)

        project_data = response.get("project")
        if project_data is None:
            raise ToolException(f"Project '{project_path}' not found or not accessible")

        ascp_components = project_data.get("ascpComponents") or {}
        nodes = ascp_components.get("nodes") or []
        page_info = ascp_components.get("pageInfo") or {}

        page_info_dict = {
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor"),
        }

        return ListAscpComponentsResponse(
            components=nodes, page_info=page_info_dict
        ).model_dump_json()
