import json
import logging
from typing import Any, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

logger = logging.getLogger(__name__)


class GetProjectInput(BaseModel):
    project_id: int = Field(description="Id of the project")


class GetProject(DuoBaseTool):
    name: str = "get_project"
    description: str = """Fetch details about the project"""
    args_schema: Type[BaseModel] = GetProjectInput  # type: ignore

    async def _arun(self, project_id: str) -> str:
        response = await self.gitlab_client.aget(
            path=f"/api/v4/projects/{project_id}",
            parse_json=False,
            use_http_response=True,
        )

        if not response.is_success():
            logger.error(
                f"Failed to get project: status_code={response.status_code}, error={response.body}"
            )
            return json.dumps({"error": f"Failed to get project: {response.body}"})

        return response.body

    def format_display_message(
        self, args: GetProjectInput, _tool_response: Any = None
    ) -> str:
        return f"Get project information for project {args.project_id}"
