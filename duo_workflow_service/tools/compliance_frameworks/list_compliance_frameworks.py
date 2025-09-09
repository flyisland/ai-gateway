import json
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool
from duo_workflow_service.tools.compliance_frameworks.queries.compliance_frameworks import (
   LIST_NAMESPACE_COMPLIANCE_FRAMEWORKS_QUERY
)


class ListComplianceFrameworksInput(BaseModel):
    namespace_path: str = Field(
        description="The full path of the namespace (group or organization) to list compliance frameworks for"
    )
    limit: Optional[int] = Field(
        default=20,
        description="Maximum number of frameworks to return (default: 20, max: 100)",
    )
    after: Optional[str] = Field(
        default=None,
        description="Cursor for pagination to get next page of results",
    )


class ListComplianceFrameworks(DuoBaseTool):
    name: str = "list_compliance_frameworks"
    description: str = """List all compliance frameworks available in a namespace (group/organization).

    This tool provides a high-level overview of all compliance frameworks, showing:
    - Framework names, descriptions, and configurations
    - Default framework indicators
    - Project count for each framework
    - Framework metadata (colors, pipeline configs, timestamps)
    
    Use this to:
    - Discover available compliance frameworks in your organization
    - Get framework IDs for detailed queries
    - See framework usage statistics
    - Identify default frameworks
    
    For detailed requirements and controls, use get_compliance_framework_details.
    
    Examples:
        list_compliance_frameworks(namespace_path="my-organization")
        list_compliance_frameworks(namespace_path="my-org/sub-group", limit=50)
    """
    args_schema: Type[BaseModel] = ListComplianceFrameworksInput

    async def _arun(self, **kwargs: Any) -> str:
        namespace_path = kwargs.pop("namespace_path")
        limit = min(kwargs.pop("limit", 20), 100)
        after = kwargs.pop("after", None)

        try:
            variables = {
                "fullPath": namespace_path,
                "first": limit,
            }
            
            if after:
                variables["after"] = after

            response = await self.gitlab_client.apost(
                path="/api/graphql",
                body=json.dumps({
                    "query": LIST_NAMESPACE_COMPLIANCE_FRAMEWORKS_QUERY,
                    "variables": variables,
                }),
            )

            if "errors" in response:
                return json.dumps({"error": response["errors"]})

            namespace_data = response.get("data", {}).get("namespace")
            
            if not namespace_data:
                return json.dumps({
                    "error": f"Namespace '{namespace_path}' not found or no access"
                })

            frameworks_data = namespace_data.get("complianceFrameworks", {})
            frameworks = frameworks_data.get("nodes", [])
            page_info = frameworks_data.get("pageInfo", {})

            result = {
                "namespace": {
                    "id": namespace_data["id"],
                    "name": namespace_data["name"],
                    "path": namespace_data["fullPath"]
                },
                "frameworks": [],
                "total_count": frameworks_data.get("count", 0),
                "pagination": {
                    "has_next_page": page_info.get("hasNextPage", False),
                    "end_cursor": page_info.get("endCursor"),
                },
            }

            for framework in frameworks:
                result["frameworks"].append({
                    "id": framework["id"],
                    "name": framework["name"],
                    "description": framework.get("description"),
                    "is_default": framework.get("default", False),
                    "color": framework.get("color"),
                    "pipeline_configuration_path": framework.get("pipelineConfigurationFullPath"),
                    "project_count": framework.get("projects", {}).get("count", 0),
                    "updated_at": framework.get("updatedAt"),
                })

            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(
        self, args: ListComplianceFrameworksInput, _tool_response: Any = None
    ) -> str:
        message = f"Listing compliance frameworks in namespace: {args.namespace_path}"
        if args.limit != 20:
            message += f" (limit: {args.limit})"
        if args.after:
            message += " (next page)"
        return message