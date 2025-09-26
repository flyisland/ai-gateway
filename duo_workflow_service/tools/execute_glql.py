import json
from typing import Any, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class ExecuteGLQLInput(BaseModel):
    """Input model for executing GLQL queries."""

    query: str = Field(
        description="The GLQL query string to execute against the GitLab API.",
    )


class ExecuteGLQL(DuoBaseTool):
    name: str = "execute_glql"

    # editorconfig-checker-disable
    description: str = """Execute a GLQL (GitLab Query Language) query against the GitLab API.

    This tool allows you to execute GLQL queries to retrieve data from GitLab using the /api/v4/glql endpoint.
    GLQL is GitLab's query language that provides a powerful way to query GitLab data.

    For example:
    - Execute a simple GLQL query:
        execute_glql(query="assignee = currentUser()")

    The query parameter should contain a valid GLQL query string.
    """
    # editorconfig-checker-enable

    args_schema: Type[BaseModel] = ExecuteGLQLInput  # type: ignore

    async def _arun(self, **kwargs: Any) -> str:
        query = kwargs.get("query")

        if not query:
            return json.dumps({"error": "Query parameter is required"})

        try:
            # Execute the GLQL query using the /api/v4/glql endpoint
            response = await self.gitlab_client.aget(
                path="/api/v4/glql",
                params={"query": query},
                parse_json=True,
            )

            return json.dumps({"glql_response": response})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(
        self, args: ExecuteGLQLInput, _tool_response: Any = None
    ) -> str:
        # Truncate long queries for display
        query_preview = args.query[:100] + "..." if len(args.query) > 100 else args.query
        return f"Execute GLQL query: {query_preview}"
