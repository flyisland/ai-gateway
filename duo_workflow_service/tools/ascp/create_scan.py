from typing import Any, ClassVar, Optional, Type

from langchain_core.tools import ToolException
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from duo_workflow_service.tools.ascp.queries import CREATE_ASCP_SCAN_MUTATION
from duo_workflow_service.tools.ascp.types import ScanTypeLiteral
from duo_workflow_service.tools.ascp.utils import parse_graphql_errors
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool
from duo_workflow_service.tools.tier_access_checker import (
    LICENSED_FEATURE_SECURITY_DASHBOARD,
)


class CreateAscpScanResponse(BaseModel):
    """Response model for creating an ASCP scan."""

    scan: dict[str, Any]


class CreateAscpScanInput(BaseModel):
    """Input model for the CreateAscpScan tool."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    project_path: str = Field(
        description='Full path of the project (e.g., "namespace/project").',
    )
    commit_sha: str = Field(
        description="Commit SHA for the scan (e.g., full 40-character Git SHA).",
    )
    scan_type: Optional[ScanTypeLiteral] = Field(
        default="FULL",
        description='Type of scan: "FULL" or "INCREMENTAL". Sent as scanType to the API. Defaults to "FULL".',
    )
    base_scan_id: Optional[str] = Field(
        default=None,
        description="GraphQL ID of the base scan (for INCREMENTAL scans).",
    )
    base_commit_sha: Optional[str] = Field(
        default=None,
        description="Base commit SHA (for INCREMENTAL scans).",
    )


class CreateAscpScan(DuoBaseTool):
    """Tool for creating an ASCP (Application Security Collaboration Platform) scan.

    On success, returns JSON with the created scan details. On error, raises ToolException with error details.
    """

    tier_check_licensed_feature: ClassVar[str] = LICENSED_FEATURE_SECURITY_DASHBOARD
    name: str = "ascp_create_scan"
    description: str = """
    Create a new ASCP scan for a project at a given commit.

    Use this tool when you need to record a full or incremental ASCP scan for
    a GitLab project. Provide the project full path (e.g., 'namespace/project'),
    the commit SHA to scan, and optionally scan_type ('FULL' or 'INCREMENTAL').
    For incremental scans, you can optionally provide base_scan_id and base_commit_sha.

    Example:
        ascp_create_scan(
            project_path="my-group/my-project",
            commit_sha="abc123def456...",
            scan_type="FULL"
        )
    """
    args_schema: Type[BaseModel] = CreateAscpScanInput

    def format_display_message(
        self, args: CreateAscpScanInput, _tool_response: Any = None
    ) -> str:
        return f"Create ASCP scan for {args.project_path} at {args.commit_sha}"

    async def _execute(self, **kwargs: Any) -> str:
        input_data = CreateAscpScanInput.model_validate(kwargs).model_dump(
            by_alias=True, exclude_none=True
        )
        variables = {"input": input_data}

        response = await self.gitlab_client.graphql(
            CREATE_ASCP_SCAN_MUTATION,
            variables,
        )

        if not isinstance(response, dict):
            raise ToolException("GraphQL returned no response or invalid format")

        graphql_errors = response.get("errors")
        if graphql_errors:
            messages = parse_graphql_errors(graphql_errors)
            exc_message = "; ".join(messages)
            raise ToolException(exc_message)

        payload = response.get("ascpScanCreate") or {}

        scan = payload.get("scan")
        errors = payload.get("errors")

        if errors:
            if not isinstance(errors, list):
                errors = [str(errors)]
            raise ToolException("; ".join(errors))

        if not scan or not scan.get("id"):
            raise ToolException("Failed to create ASCP scan.")

        return CreateAscpScanResponse(scan=scan).model_dump_json()
