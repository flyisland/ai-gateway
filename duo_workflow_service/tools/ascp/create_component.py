from typing import Any, Optional, Type

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from duo_workflow_service.tools.ascp.queries import CREATE_ASCP_COMPONENT_MUTATION
from duo_workflow_service.tools.ascp.utils import parse_graphql_errors
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class CreateAscpComponentResponseBody(BaseModel):
    """Nested response: component entity and raw API payload."""

    component: Optional[dict[str, Any]] = None
    raw_response: Optional[dict[str, Any]] = None


class CreateAscpComponentResponse(BaseModel):
    """Unified response shape for success and error."""

    errors: list[str] = Field(default_factory=list)
    response: CreateAscpComponentResponseBody = Field(
        default_factory=CreateAscpComponentResponseBody
    )


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

    Returned JSON uses a single shape for success and error: {"errors": list[str],
    "response": {"component": ... | null, "raw_response": ... | null}}. Success when
    errors is empty and response.component is set; on error, errors is non-empty and
    response contains component and/or raw_response (raw API payload) when available.
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

        try:
            response = await self.gitlab_client.graphql(
                CREATE_ASCP_COMPONENT_MUTATION,
                variables,
            )
        except Exception as e:
            return CreateAscpComponentResponse(
                errors=[
                    f"ascp_create_component failed: {type(e).__name__}: {e!s}",
                ],
                response=CreateAscpComponentResponseBody(
                    component=None, raw_response=None
                ),
            ).model_dump_json()

        if not isinstance(response, dict):
            return CreateAscpComponentResponse(
                errors=["GraphQL returned no response or invalid format"],
                response=CreateAscpComponentResponseBody(
                    component=None, raw_response=None
                ),
            ).model_dump_json()

        graphql_errors = response.get("errors")
        if graphql_errors:
            messages = parse_graphql_errors(graphql_errors)
            return CreateAscpComponentResponse(
                errors=messages,
                response=CreateAscpComponentResponseBody(
                    component=None, raw_response=response
                ),
            ).model_dump_json()

        payload = response.get("ascpComponentCreate") or {}

        component = payload.get("component")
        errors = payload.get("errors")

        if errors:
            if not isinstance(errors, list):
                errors = [str(errors)]
            return CreateAscpComponentResponse(
                errors=errors,
                response=CreateAscpComponentResponseBody(
                    component=component, raw_response=payload
                ),
            ).model_dump_json()

        if not component or not component.get("id"):
            return CreateAscpComponentResponse(
                errors=["Failed to create ASCP component."],
                response=CreateAscpComponentResponseBody(
                    component=component, raw_response=payload
                ),
            ).model_dump_json()

        return CreateAscpComponentResponse(
            errors=[],
            response=CreateAscpComponentResponseBody(
                component=component, raw_response=None
            ),
        ).model_dump_json()
