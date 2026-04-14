from typing import Any, Optional, Type

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from duo_workflow_service.tools.ascp.queries import (
    CREATE_ASCP_SECURITY_CONTEXT_MUTATION,
)
from duo_workflow_service.tools.ascp.types import AscpSeverityLiteral
from duo_workflow_service.tools.ascp.utils import parse_graphql_errors
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class AscpSecurityGuidelineInput(BaseModel):
    """Input model for a single security guideline."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str = Field(
        description="Name of the security guideline.",
    )
    operation: str = Field(
        description="Operation this guideline applies to (e.g., 'READ', 'WRITE', 'DELETE').",
    )
    legitimate_use: Optional[str] = Field(
        default=None,
        description="Description of legitimate use for this operation.",
    )
    security_boundary: Optional[str] = Field(
        default=None,
        description="Security boundary conditions for this guideline.",
    )
    business_context: Optional[str] = Field(
        default=None,
        description="Business context explaining why this guideline exists.",
    )
    severity_if_violated: Optional[AscpSeverityLiteral] = Field(
        default="MEDIUM",
        description=(
            'Severity level if this guideline is violated: "LOW", "MEDIUM", "HIGH",'
            ' or "CRITICAL". Defaults to "MEDIUM".'
        ),
    )


class CreateAscpSecurityContextResponseBody(BaseModel):
    """Nested response: security context entity and raw API payload."""

    security_context: Optional[dict[str, Any]] = None
    raw_response: Optional[dict[str, Any]] = None


class CreateAscpSecurityContextResponse(BaseModel):
    """Unified response shape for success and error."""

    errors: list[str] = Field(default_factory=list)
    response: CreateAscpSecurityContextResponseBody = Field(
        default_factory=CreateAscpSecurityContextResponseBody
    )


class CreateAscpSecurityContextInput(BaseModel):
    """Input model for the CreateAscpSecurityContext tool."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    project_path: str = Field(
        description='Full path of the project (e.g., "namespace/project").',
    )
    component_id: str = Field(
        description=(
            "GraphQL ID of the ASCP component to attach this security context to"
            ' (e.g., "gid://gitlab/Ascp::Component/1").'
        ),
    )
    scan_id: str = Field(
        description='GraphQL ID of the ASCP scan this security context belongs to (e.g., "gid://gitlab/Ascp::Scan/1").',
    )
    guidelines: list[AscpSecurityGuidelineInput] = Field(
        min_length=1,
        description="List of security guidelines for this context. At least one is required.",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Optional summary of the security context.",
    )
    authentication_model: Optional[str] = Field(
        default=None,
        description="Optional description of the authentication model used by this component.",
    )
    authorization_model: Optional[str] = Field(
        default=None,
        description="Optional description of the authorization model used by this component.",
    )
    data_sensitivity: Optional[str] = Field(
        default=None,
        description="Optional description of data sensitivity classification for this component.",
    )


class CreateAscpSecurityContext(DuoBaseTool):
    """Tool for creating an ASCP (Application Security Collaboration Platform) security context.

    Returned JSON uses a single shape for success and error: {"errors": list[str],
    "response": {"security_context": ... | null, "raw_response": ... | null}}. Success when
    errors is empty and response.security_context is set; on error, errors is non-empty and
    response contains security_context and/or raw_response (raw API payload) when available.
    """

    name: str = "ascp_create_security_context"
    description: str = """
    Create a new ASCP security context for a component within a given scan.

    Use this tool when you need to define the security context for an ASCP component,
    including security guidelines, authentication/authorization models, and data sensitivity.
    Provide the project full path, the component ID, the scan ID, and at least one security
    guideline.

    Example:
        ascp_create_security_context(
            project_path="my-group/my-project",
            component_id="gid://gitlab/Ascp::Component/1",
            scan_id="gid://gitlab/Ascp::Scan/1",
            guidelines=[{
                "name": "No direct DB access",
                "operation": "READ",
                "severity_if_violated": "HIGH"
            }],
            summary="Security context for the authentication service"
        )
    """
    args_schema: Type[BaseModel] = CreateAscpSecurityContextInput

    def format_display_message(
        self, args: CreateAscpSecurityContextInput, _tool_response: Any = None
    ) -> str:
        return f"Create ASCP security context for component {args.component_id}"

    async def _execute(self, **kwargs: Any) -> str:
        input_data = CreateAscpSecurityContextInput.model_validate(kwargs).model_dump(
            by_alias=True, exclude_none=True
        )
        variables = {"input": input_data}

        try:
            response = await self.gitlab_client.graphql(
                CREATE_ASCP_SECURITY_CONTEXT_MUTATION,
                variables,
            )
        except Exception as e:
            return CreateAscpSecurityContextResponse(
                errors=[
                    f"ascp_create_security_context failed: {type(e).__name__}: {e!s}",
                ],
                response=CreateAscpSecurityContextResponseBody(
                    security_context=None, raw_response=None
                ),
            ).model_dump_json()

        if not isinstance(response, dict):
            return CreateAscpSecurityContextResponse(
                errors=["GraphQL returned no response or invalid format"],
                response=CreateAscpSecurityContextResponseBody(
                    security_context=None, raw_response=None
                ),
            ).model_dump_json()

        graphql_errors = response.get("errors")
        if graphql_errors:
            messages = parse_graphql_errors(graphql_errors)
            return CreateAscpSecurityContextResponse(
                errors=messages,
                response=CreateAscpSecurityContextResponseBody(
                    security_context=None, raw_response=response
                ),
            ).model_dump_json()

        payload = response.get("ascpSecurityContextCreate") or {}

        security_context = payload.get("securityContext")
        errors = payload.get("errors")

        if errors:
            if not isinstance(errors, list):
                errors = [str(errors)]
            return CreateAscpSecurityContextResponse(
                errors=errors,
                response=CreateAscpSecurityContextResponseBody(
                    security_context=security_context, raw_response=payload
                ),
            ).model_dump_json()

        if not security_context or not security_context.get("id"):
            return CreateAscpSecurityContextResponse(
                errors=["Failed to create ASCP security context."],
                response=CreateAscpSecurityContextResponseBody(
                    security_context=security_context, raw_response=payload
                ),
            ).model_dump_json()

        return CreateAscpSecurityContextResponse(
            errors=[],
            response=CreateAscpSecurityContextResponseBody(
                security_context=security_context, raw_response=None
            ),
        ).model_dump_json()
