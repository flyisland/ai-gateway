import json
from typing import Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class GetProjectInput(BaseModel):
    project_id: int = Field(description="Id of the project")


class GetProject(DuoBaseTool):
    name: str = "get_project"
    description: str = """Fetch details about the project"""
    args_schema: Type[BaseModel] = GetProjectInput  # type: ignore

    async def _arun(self, project_id: str) -> str:
        return await self.gitlab_client.aget(
            path=f"/api/v4/projects/{project_id}", parse_json=False
        )

    def format_display_message(self, args: GetProjectInput) -> str:
        return f"Get project information for project {args.project_id}"


class GetUserContributedProjectsInput(BaseModel):
    username: str = Field(description="Username of the user to get contributed projects for")


class GetUserContributedProjects(DuoBaseTool):
    name: str = "get_user_contributed_projects"
    description: str = """Fetch information about projects that a user has contributed to using GraphQL"""
    args_schema: Type[BaseModel] = GetUserContributedProjectsInput  # type: ignore

    async def _arun(self, username: str) -> str:
        query = """
        query($username: String!) {
          user(username: $username) {
            contributedProjects {
              nodes {
                webUrl
                name
                description
                id
                fullPath
                visibility
                starCount
                forksCount
                lastActivityAt
              }
            }
          }
        }
        """

        variables = {"username": username}

        try:
            response = await self.gitlab_client.graphql(query=query, variables=variables)
            return json.dumps(response, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Failed to fetch contributed projects for user {username}: {str(e)}"})

    def format_display_message(self, args: GetUserContributedProjectsInput) -> str:
        return f"Get contributed projects for user {args.username}"


class AnalyticalQueryInput(BaseModel):
    query: str = Field(description="Analytical query to execute using ClickHouse")


class AnalyticalQuery(DuoBaseTool):
    name: str = "analytical_query"
    description: str = """Execute analytical queries using ClickHouse"""
    args_schema: Type[BaseModel] = AnalyticalQueryInput  # type: ignore

    async def _arun(self, query: str) -> str:
        try:
            response = await self.gitlab_client.aget(
                path="/-/clickhouse",
                params={"query": query},
                parse_json=False
            )
            return response
        except Exception as e:
            return json.dumps({"error": f"Failed to execute analytical query: {str(e)}"})

    def format_display_message(self, args: AnalyticalQueryInput) -> str:
        return f"Execute analytical query"
