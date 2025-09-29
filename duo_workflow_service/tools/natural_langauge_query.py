import json
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

__all__ = ["NaturalLangaugeQuery"]


class NaturalLangaugeQueryInput(BaseModel):
    """Input validation for natural language to GLQL conversion."""

    query: str = Field(
        description="The natural language query to convert to GLQL (e.g., 'Show me open issues assigned to me')",
    )
    display: Optional[str] = Field(
        default="table",
        description="Display format: 'table', 'list', or 'orderedList'. Default is 'table'.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Custom title for the view. If not provided, will be auto-generated based on the query.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional description for the view.",
    )
    fields: Optional[str] = Field(
        default=None,
        description="Comma-separated list of fields to display (e.g., 'title, state, assignee, updated'). If not provided, will be auto-selected based on the query.",
    )
    limit: Optional[int] = Field(
        default=10,
        description="Maximum number of items to display (1-100). Default is 10.",
        ge=1,
        le=100,
    )
    sort: Optional[str] = Field(
        default=None,
        description="Sort order (e.g., 'updated desc', 'created asc', 'title asc'). If not provided, will be auto-selected.",
    )
    collapsed: Optional[bool] = Field(
        default=False,
        description="Whether the view should be initially collapsed. Default is false.",
    )

class NaturalLangaugeQuery(DuoBaseTool):
    name: str = "natural_langauge_query"
    description: str = """Convert natural language queries to GitLab Query Language (GLQL) format.

    This tool takes a natural language query about GitLab issues, merge requests, or epics
    and converts it to properly formatted GLQL that can be used in GitLab embedded views.

    The tool supports various query types such as:
    - "Show me open issues assigned to me"
    - "List all critical bugs in the frontend project"
    - "Find merge requests that need review"
    - "Show overdue issues with high priority"
    - "List epics in the engineering group"

    Optional parameters can be provided to customize the output format, including:
    - display: table, list, or orderedList
    - title: custom title for the view
    - description: optional description
    - fields: specific fields to display
    - limit: number of items to show
    - sort: sort order
    - collapsed: initial collapsed state

    The output will be a properly formatted GLQL code block ready for use in GitLab.

    For example:
    - Convert a simple query:
        natural_langauge_query(query="Show me open issues assigned to me")
    
    - Convert with custom options:
        natural_langauge_query(
            query="Show critical bugs in the frontend project",
            display="table",
            fields="title, assignee, created, labels",
            limit=20,
            sort="created desc"
        )
    """
    args_schema: Type[BaseModel] = NaturalLangaugeQueryInput

    async def _arun(self, **kwargs: Any) -> str:
        """Execute the natural language to GLQL conversion."""
        try:
            query = kwargs.get("query", "")
            display = kwargs.get("display", "table")
            title = kwargs.get("title")
            description = kwargs.get("description")
            fields = kwargs.get("fields")
            limit = kwargs.get("limit", 10)
            sort = kwargs.get("sort")
            collapsed = kwargs.get("collapsed", False)

            # Convert natural language to GLQL
            glql_query = self._convert_to_glql(query)
            
            # Auto-generate title if not provided
            if not title:
                title = self._generate_title(query)
            
            # Auto-select fields if not provided
            if not fields:
                fields = self._select_fields(query)
            
            # Auto-select sort if not provided
            if not sort:
                sort = self._select_sort(query)

            # Format the GLQL output
            glql_output = self._format_glql_output(
                display=display,
                title=title,
                description=description,
                fields=fields,
                limit=limit,
                sort=sort,
                collapsed=collapsed,
                query=glql_query
            )

            return json.dumps({
                "glql": glql_output,
                "success": True,
                "message": "Successfully converted natural language query to GLQL"
            })

        except Exception as e:
            return json.dumps({
                "error": f"Failed to convert query to GLQL: {str(e)}",
                "success": False
            })

    def _convert_to_glql(self, natural_query: str) -> str:
        """Convert natural language query to GLQL syntax."""
        query_lower = natural_query.lower()
        glql_parts = []

        # Handle assignee patterns
        if "assigned to me" in query_lower or "my issues" in query_lower or "my tasks" in query_lower:
            glql_parts.append("assignee = currentUser()")
        elif "unassigned" in query_lower or "no assignee" in query_lower:
            glql_parts.append("assignee = none")
        elif "assigned to" in query_lower:
            # Extract username if mentioned
            words = natural_query.split()
            for i, word in enumerate(words):
                if word.lower() == "to" and i + 1 < len(words):
                    username = words[i + 1].strip("@")
                    glql_parts.append(f"assignee = @{username}")
                    break

        # Handle state patterns
        if "open" in query_lower or "opened" in query_lower:
            glql_parts.append("state = opened")
        elif "closed" in query_lower:
            glql_parts.append("state = closed")
        elif "merged" in query_lower:
            glql_parts.append("state = merged")

        # Handle type patterns
        if "merge request" in query_lower or "mr" in query_lower:
            glql_parts.append("type = MergeRequest")
        elif "epic" in query_lower:
            glql_parts.append("type = Epic")
        elif "task" in query_lower:
            glql_parts.append("type = Task")
        elif "incident" in query_lower:
            glql_parts.append("type = Incident")

        # Handle priority/severity patterns
        if "critical" in query_lower:
            glql_parts.append("label = ~critical")
        elif "high priority" in query_lower:
            glql_parts.append("label = ~\"priority::high\"")
        elif "bug" in query_lower:
            glql_parts.append("label = ~bug")
        elif "feature" in query_lower:
            glql_parts.append("label = ~feature")

        # Handle time patterns
        if "overdue" in query_lower:
            glql_parts.append("due < today()")
        elif "due today" in query_lower:
            glql_parts.append("due = today()")
        elif "created today" in query_lower:
            glql_parts.append("created = today()")
        elif "updated today" in query_lower:
            glql_parts.append("updated = today()")
        elif "last week" in query_lower:
            glql_parts.append("updated > -1w")
        elif "last month" in query_lower:
            glql_parts.append("updated > -1m")

        # Handle review patterns
        if "need review" in query_lower or "needs review" in query_lower:
            glql_parts.append("reviewer = currentUser()")
            glql_parts.append("state = opened")
        elif "draft" in query_lower:
            glql_parts.append("draft = true")

        # Handle health status patterns
        if "at risk" in query_lower:
            glql_parts.append("health = \"at risk\"")
        elif "needs attention" in query_lower:
            glql_parts.append("health = \"needs attention\"")
        elif "on track" in query_lower:
            glql_parts.append("health = \"on track\"")

        # Handle milestone patterns
        if "no milestone" in query_lower:
            glql_parts.append("milestone = none")
        elif "current milestone" in query_lower:
            glql_parts.append("milestone = current")

        # Handle project/group patterns
        if "project" in query_lower:
            words = natural_query.split()
            for i, word in enumerate(words):
                if word.lower() == "project" and i + 1 < len(words):
                    project_name = words[i + 1].strip('"\'')
                    glql_parts.append(f"project = \"{project_name}\"")
                    break
        elif "group" in query_lower:
            words = natural_query.split()
            for i, word in enumerate(words):
                if word.lower() == "group" and i + 1 < len(words):
                    group_name = words[i + 1].strip('"\'')
                    glql_parts.append(f"group = \"{group_name}\"")
                    break

        # Default to open issues if no specific criteria
        if not glql_parts:
            glql_parts.append("state = opened")

        return " AND ".join(glql_parts)

    def _generate_title(self, query: str) -> str:
        """Generate a title based on the natural language query."""
        query_lower = query.lower()
        
        if "my" in query_lower and "issue" in query_lower:
            return "My Issues"
        elif "my" in query_lower and "task" in query_lower:
            return "My Tasks"
        elif "merge request" in query_lower or "mr" in query_lower:
            return "Merge Requests"
        elif "epic" in query_lower:
            return "Epics"
        elif "bug" in query_lower:
            return "Bug Reports"
        elif "overdue" in query_lower:
            return "Overdue Items"
        elif "review" in query_lower:
            return "Review Queue"
        elif "critical" in query_lower:
            return "Critical Items"
        else:
            return "Query Results"

    def _select_fields(self, query: str) -> str:
        """Select appropriate fields based on the query."""
        query_lower = query.lower()
        fields = ["title"]
        
        # Always include state for most queries
        if "merge request" not in query_lower:
            fields.append("state")
        
        # Add assignee for assignment-related queries
        if "assign" in query_lower or "my" in query_lower:
            fields.append("assignee")
        
        # Add health for health-related queries
        if "health" in query_lower or "risk" in query_lower or "attention" in query_lower:
            fields.append("health")
        
        # Add milestone for milestone queries
        if "milestone" in query_lower:
            fields.append("milestone")
        
        # Add labels for bug/feature queries
        if "bug" in query_lower or "feature" in query_lower or "label" in query_lower:
            fields.append("labels")
        
        # Add due date for overdue queries
        if "due" in query_lower or "overdue" in query_lower:
            fields.append("due")
        
        # Add created/updated for time-based queries
        if "created" in query_lower:
            fields.append("created")
        elif "updated" in query_lower or "recent" in query_lower:
            fields.append("updated")
        else:
            fields.append("updated")  # Default to updated
        
        # Add merge request specific fields
        if "merge request" in query_lower or "mr" in query_lower:
            fields.extend(["author", "sourceBranch"])
            if "review" in query_lower:
                fields.append("reviewer")
        
        return ", ".join(fields)

    def _select_sort(self, query: str) -> str:
        """Select appropriate sort order based on the query."""
        query_lower = query.lower()
        
        if "overdue" in query_lower:
            return "due asc"
        elif "recent" in query_lower or "latest" in query_lower:
            return "updated desc"
        elif "oldest" in query_lower:
            return "created asc"
        elif "created" in query_lower:
            return "created desc"
        elif "priority" in query_lower:
            return "updated desc"
        else:
            return "updated desc"  # Default sort

    def _format_glql_output(self, display: str, title: str, description: Optional[str], 
                          fields: str, limit: int, sort: str, collapsed: bool, query: str) -> str:
        """Format the final GLQL output."""
        lines = [
            "```glql",
            f"display: {display}",
            f"title: {title}"
        ]
        
        if description:
            lines.append(f"description: {description}")
        
        lines.extend([
            f"fields: {fields}",
            f"limit: {limit}",
            f"sort: {sort}",
            f"collapsed: {str(collapsed).lower()}",
            f"query: {query}",
            "```"
        ])
        
        return "\n".join(lines)

    def format_display_message(
        self, args: NaturalLangaugeQueryInput, _tool_response: Any = None
    ) -> str:
        """Format a user-friendly display message."""
        return f"Convert natural language query to GLQL: '{args.query}'"