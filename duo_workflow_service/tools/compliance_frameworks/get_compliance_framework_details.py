# get_compliance_framework_details.py

import json
from typing import Any, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


GET_COMPLIANCE_FRAMEWORK_FULL_DETAILS_QUERY = """
query GetComplianceFrameworkFullDetails($id: ComplianceMgmtFrameworkID!, $projectsFirst: Int, $projectsAfter: String) {
    complianceFramework(id: $id) {
        id
        name
        description
        color
        default
        pipelineConfigurationFullPath
        namespace {
            id
            fullPath
            name
        }
        createdAt
        updatedAt
        projects(first: $projectsFirst, after: $projectsAfter) {
            pageInfo {
                hasNextPage
                endCursor
            }
            count
            nodes {
                id
                name
                fullPath
                description
                visibility
                archived
                webUrl
            }
        }
        complianceRequirements {
            nodes {
                id
                name
                description
                complianceRequirementsControls {
                    nodes {
                        id
                        name
                        description
                        createdAt
                        updatedAt
                    }
                }
            }
        }
    }
}
"""


class GetComplianceFrameworkDetailsInput(BaseModel):
    framework_id: str = Field(
        description="The ID of the compliance framework to get complete details for"
    )


class GetComplianceFrameworkDetails(DuoBaseTool):
    name: str = "get_compliance_framework_details"
    description: str = """Get complete details of a compliance framework including all requirements and controls.

    This tool retrieves the full compliance framework structure in a single call:
    - Framework metadata and configuration
    - All requirements with descriptions
    - All controls for each requirement
    - Namespace and project information
    
    The tool returns the complete framework hierarchy:
    Framework → Requirements → Controls
    
    Use this to:
    - View the complete compliance framework structure
    - Analyze all requirements and their implementation controls
    - Export or document compliance frameworks
    - Understand the full scope of compliance obligations
    
    Note: Requirements and controls are counted by iterating through results.
    
    Example:
        get_compliance_framework_details(framework_id="gid://gitlab/ComplianceManagement::Framework/123")
    """
    args_schema: Type[BaseModel] = GetComplianceFrameworkDetailsInput

    async def _arun(self, **kwargs: Any) -> str:
        framework_id = kwargs.pop("framework_id")

        try:
            variables = {
                "id": framework_id,
            }

            response = await self.gitlab_client.apost(
                path="/api/graphql",
                body=json.dumps({
                    "query": GET_COMPLIANCE_FRAMEWORK_FULL_DETAILS_QUERY,
                    "variables": variables,
                }),
            )

            if "errors" in response:
                return json.dumps({"error": response["errors"]})

            framework_data = response.get("data", {}).get("complianceFramework")
            
            if not framework_data:
                return json.dumps({
                    "error": f"Framework '{framework_id}' not found or no access"
                })

            requirements_data = framework_data.get("complianceRequirements", {})
            requirements = requirements_data.get("nodes", [])
            projects_data = framework_data.get("projects", {})

            # Build hierarchical result
            result = {
                "framework": {
                    "id": framework_data["id"],
                    "name": framework_data["name"],
                    "description": framework_data.get("description"),
                    "is_default": framework_data.get("default", False),
                    "color": framework_data.get("color"),
                    "pipeline_configuration_path": framework_data.get("pipelineConfigurationFullPath"),
                    "namespace": {
                        "id": framework_data["namespace"]["id"],
                        "name": framework_data["namespace"]["name"],
                        "path": framework_data["namespace"]["fullPath"],
                    },
                    "project_count": projects_data.get("count", 0),
                    "created_at": framework_data.get("createdAt"),
                    "updated_at": framework_data.get("updatedAt"),
                },
                "requirements": [],
                "summary": {
                    "total_requirements": 0,
                    "total_controls": 0,
                }
            }

            # Add projects if requested
            if include_projects and projects_data.get("nodes"):
                result["projects"] = {
                    "list": [],
                    "pagination": {
                        "has_next_page": projects_data.get("pageInfo", {}).get("hasNextPage", False),
                        "end_cursor": projects_data.get("pageInfo", {}).get("endCursor"),
                    }
                }
                
                for project in projects_data.get("nodes", []):
                    result["projects"]["list"].append({
                        "id": project["id"],
                        "name": project["name"],
                        "path": project["fullPath"],
                        "description": project.get("description"),
                        "visibility": project.get("visibility"),
                        "archived": project.get("archived", False),
                        "web_url": project.get("webUrl"),
                    })

            # Process requirements and controls
            for requirement in requirements:
                controls_data = requirement.get("complianceRequirementsControls", {})
                controls = controls_data.get("nodes", [])
                
                req_obj = {
                    "id": requirement["id"],
                    "name": requirement["name"],
                    "description": requirement.get("description"),
                    "control_count": len(controls),
                    "controls": []
                }
                
                for control in controls:
                    req_obj["controls"].append({
                        "id": control["id"],
                        "name": control["name"],
                        "description": control.get("description"),
                        "created_at": control.get("createdAt"),
                        "updated_at": control.get("updatedAt"),
                    })
                    result["summary"]["total_controls"] += 1
                
                result["requirements"].append(req_obj)
                result["summary"]["total_requirements"] += 1

            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(
        self, args: GetComplianceFrameworkDetailsInput, _tool_response: Any = None
    ) -> str:
        return f"Getting complete details for compliance framework: {args.framework_id}"