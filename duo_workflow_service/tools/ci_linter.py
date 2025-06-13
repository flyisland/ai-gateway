import json
from typing import Any, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class CiLinterInput(BaseModel):
    project_id: int = Field(description="Id of the project")
    content: str = Field(
        description="The content of the CI/CD YAML configuration to validate."
    )


class CiLinter(DuoBaseTool):
    name: str = "ci_linter"
    description: str = """Validates a CI/CD YAML configuration against GitLab CI syntax rules in the context of the
    project. This tool can be used when you have a project_id and the content of the CI/CD YAML configuration.

    For example:
    - Given project_id 42 and content of the CI/CD YAML configuration, the tool call would be:
        ci_linter(project_id=42, content="stages:\n  - build\n  - test\nbuild:\n  stage: build\n  script: echo 'Building...'\ntest:\n  stage: test\n  script: echo 'Testing...'\n")

    This tool will return a JSON response indicating whether the configuration is valid or not, along with any errors found.
    """

    args_schema: Type[BaseModel] = CiLinterInput

    async def _arun(self, content: str, **kwargs: Any) -> str:
        url = kwargs.pop("url", None)
        project_id = kwargs.pop("project_id", None)

        project_id, errors = self._validate_project_url(url, project_id)

        if errors:
            return json.dumps({"error": "; ".join(errors)})

        try:
            response = await self.gitlab_client.apost(
                path=f"/api/v4/projects/{project_id}/ci/lint",
                body=json.dumps({"content": content}),
            )
            return json.dumps(response)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: CiLinterInput) -> str:
        return f"Validate CI/CD YAML configuration in context of project: {args.project_id}"
