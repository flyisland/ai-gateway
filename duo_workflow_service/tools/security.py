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


class GetProjectVulnerabilitiesInput(ProjectResourceInput):
    """Input model for retrieving project vulnerabilities."""
    # TODO: Add pagination parameters if needed
    # TODO: Add filtering parameters based on GitLab API documentation
    pass


class GetProjectVulnerabilities(DuoBaseTool):
    """Tool for retrieving vulnerability findings for a specific project."""
    name: str = "get_project_vulnerabilities"
    description: str = f"""Retrieve vulnerability findings for a specific project.

    {PROJECT_IDENTIFICATION_DESCRIPTION}

    For example:
    - Given project_id 13, the tool call would be:
        get_project_vulnerabilities(project_id=13)
    - Given the URL https://gitlab.com/namespace/project, the tool call would be:
        get_project_vulnerabilities(url="https://gitlab.com/namespace/project")
    """
    args_schema: Type[BaseModel] = GetProjectVulnerabilitiesInput

    async def _arun(self, **kwargs: Any) -> str:
        url = kwargs.pop("url", None)
        project_id = kwargs.pop("project_id", None)

        project_id, errors = self._validate_project_url(url, project_id)

        if errors:
            return json.dumps({"error": "; ".join(errors)})

        try:
            response = await self.gitlab_client.aget(
                path=f"/api/v4/projects/{project_id}/vulnerabilities",
                parse_json=False,
            )
            return json.dumps({"vulnerabilities": response})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: GetProjectVulnerabilitiesInput) -> str:
        if args.url:
            return f"Get vulnerabilities for project {args.url}"
        return f"Get vulnerabilities for project {args.project_id}"


class GetProjectSecurityConfigurationInput(ProjectResourceInput):
    """Input model for retrieving project security configuration."""
    pass


class GetProjectSecurityConfiguration(DuoBaseTool):
    """Tool for retrieving security configuration for a specific project."""
    name: str = "get_project_security_configuration"
    description: str = f"""List all security scanners enabled in a project.

    {PROJECT_IDENTIFICATION_DESCRIPTION}

    For example:
    - Given project_id 13, the tool call would be:
        get_project_security_configuration(project_id=13)
    - Given the URL https://gitlab.com/namespace/project, the tool call would be:
        get_project_security_configuration(url="https://gitlab.com/namespace/project")
    """
    args_schema: Type[BaseModel] = GetProjectSecurityConfigurationInput

    async def _arun(self, **kwargs: Any) -> str:
        url = kwargs.pop("url", None)
        project_id = kwargs.pop("project_id", None)

        project_id, errors = self._validate_project_url(url, project_id)

        if errors:
            return json.dumps({"error": "; ".join(errors)})

        try:
            response = await self.gitlab_client.aget(
                path=f"/api/v4/projects/{project_id}/security_configuration",
                parse_json=False,
            )
            return json.dumps({"security_configuration": response})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: GetProjectSecurityConfigurationInput) -> str:
        if args.url:
            return f"Get security configuration for project {args.url}"
        return f"Get security configuration for project {args.project_id}" 