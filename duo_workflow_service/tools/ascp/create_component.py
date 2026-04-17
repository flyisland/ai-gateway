from typing import Any, Optional, Type

from langchain_core.tools import ToolException
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from duo_workflow_service.tools.ascp.queries import CREATE_ASCP_COMPONENT_MUTATION
from duo_workflow_service.tools.ascp.utils import parse_graphql_errors
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class CreateAscpComponentResponse(BaseModel):
    """Response model for creating an ASCP component."""

    component: dict[str, Any]


class CreateAscpComponentInput(BaseModel):
    """Input model for the CreateAscpComponent tool."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    project_path: str = Field(
        description='Full path of the project (e.g., "namespace/project").',
    )
    title: str = Field(
        description="Title of the business component.",
    )
    sub_directory: str = Field(
        description="Subdirectory path within the repository that this component owns.",
    )
    scan_id: str = Field(
        description='GraphQL ID of the ASCP scan this component belongs to (e.g., "gid://gitlab/Ascp::Scan/1").',
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional description of the component.",
    )
    expected_user_behavior: Optional[str] = Field(
        default=None,
        description="Optional description of expected user behavior for this component.",
    )


class CreateAscpComponent(DuoBaseTool):
    """Tool for creating an ASCP (Application Security Collaboration Platform) component.

    On success, returns JSON with the created component details. On error, raises ToolException with error details.
    """

    name: str = "ascp_create_component"
    description: str = """
    Create a new ASCP component for a project within a given scan.

    Use this tool when you need to register a business component for an ASCP scan in
    a GitLab project. Provide the project full path, the component title, the subdirectory
    it owns, and the scan ID it belongs to. Optionally provide a description and expected
    user behavior.

    Example:
        ascp_create_component(
            project_path="my-group/my-project",
            title="Authentication Service",
            sub_directory="services/auth",
            scan_id="gid://gitlab/Ascp::Scan/1",
            description="Handles user authentication and session management"
        )
    """
    args_schema: Type[BaseModel] = CreateAscpComponentInput

    def format_display_message(
        self, args: CreateAscpComponentInput, _tool_response: Any = None
    ) -> str:
        return f"Create ASCP component '{args.title}' in {args.project_path}"

    async def _execute(self, **kwargs: Any) -> str:
        input_data = CreateAscpComponentInput.model_validate(kwargs).model_dump(
            by_alias=True, exclude_none=True
        )
        variables = {"input": input_data}

        response = await self.gitlab_client.graphql(
            CREATE_ASCP_COMPONENT_MUTATION,
            variables,
        )

        if not isinstance(response, dict):
            raise ToolException("GraphQL returned no response or invalid format")

        graphql_errors = response.get("errors")
        if graphql_errors:
            messages = parse_graphql_errors(graphql_errors)
            exc_message = "; ".join(messages)
            raise ToolException(exc_message)

        payload = response.get("ascpComponentCreate") or {}

        component = payload.get("component")
        errors = payload.get("errors")

        if errors:
            if not isinstance(errors, list):
                errors = [str(errors)]
            raise ToolException("; ".join(errors))

        if not component or not component.get("id"):
            raise ToolException("Failed to create ASCP component.")

        return CreateAscpComponentResponse(component=component).model_dump_json()
