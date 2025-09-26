import json
from typing import Any
from unittest.mock import Mock

import pytest

from duo_workflow_service.tools.natural_langauge_query import (
    NaturalLangaugeQueryInput,
    NaturalLangaugeQuery,
)


@pytest.fixture(name="metadata")
def metadata_fixture():
    """Fixture for tool metadata."""
    return {}


class TestNaturalLangaugeQuery:
    """Test suite for NaturalLangaugeQuery."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,expected_glql_parts",
        [
            # Basic assignee patterns
            ("Show me issues assigned to me", ["assignee = currentUser()"]),
            ("Show my issues", ["assignee = currentUser()"]),
            ("Show my tasks", ["assignee = currentUser()"]),
            ("Show unassigned issues", ["assignee = none"]),
            ("Show issues with no assignee", ["assignee = none"]),
            ("Show issues assigned to @john", ["assignee = @john"]),
            
            # State patterns
            ("Show open issues", ["state = opened"]),
            ("Show opened issues", ["state = opened"]),
            ("Show closed issues", ["state = closed"]),
            ("Show merged merge requests", ["state = merged"]),
            
            # Type patterns
            ("Show merge requests", ["type = MergeRequest"]),
            ("Show MR", ["type = MergeRequest"]),
            ("Show epics", ["type = Epic"]),
            ("Show tasks", ["type = Task"]),
            ("Show incidents", ["type = Incident"]),
            
            # Priority/severity patterns
            ("Show critical issues", ["label = ~critical"]),
            ("Show high priority issues", ["label = ~\"priority::high\""]),
            ("Show bugs", ["label = ~bug"]),
            ("Show features", ["label = ~feature"]),
            
            # Time patterns
            ("Show overdue issues", ["due < today()"]),
            ("Show issues due today", ["due = today()"]),
            ("Show issues created today", ["created = today()"]),
            ("Show issues updated today", ["updated = today()"]),
            ("Show issues from last week", ["updated > -1w"]),
            ("Show issues from last month", ["updated > -1m"]),
            
            # Review patterns
            ("Show merge requests that need review", ["reviewer = currentUser()", "state = opened"]),
            ("Show MRs that needs review", ["reviewer = currentUser()", "state = opened"]),
            ("Show draft merge requests", ["draft = true"]),
            
            # Health status patterns
            ("Show issues at risk", ["health = \"at risk\""]),
            ("Show items that need attention", ["health = \"needs attention\""]),
            ("Show issues on track", ["health = \"on track\""]),
            
            # Milestone patterns
            ("Show issues with no milestone", ["milestone = none"]),
            ("Show current milestone issues", ["milestone = current"]),
            
            # Complex queries
            ("Show my open critical bugs", ["assignee = currentUser()", "state = opened", "label = ~critical", "label = ~bug"]),
            ("Show overdue high priority tasks", ["due < today()", "label = ~\"priority::high\"", "type = Task"]),
        ],
    )
    async def test_convert_to_glql_patterns(self, query, expected_glql_parts, metadata):
        """Test various natural language patterns are converted to correct GLQL."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        response = await tool._arun(query=query)
        response_data = json.loads(response)
        
        assert response_data["success"] is True
        assert "glql" in response_data
        
        # Extract the query line from the GLQL output
        glql_lines = response_data["glql"].split("\n")
        query_line = None
        for line in glql_lines:
            if line.startswith("query: "):
                query_line = line[7:]  # Remove "query: " prefix
                break
        
        assert query_line is not None, "Query line not found in GLQL output"
        
        # Check that all expected parts are in the query
        for expected_part in expected_glql_parts:
            assert expected_part in query_line, f"Expected '{expected_part}' in query '{query_line}'"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,display,title,description,fields,limit,sort,collapsed",
        [
            # Basic query with defaults
            ("Show my issues", None, None, None, None, None, None, None),
            
            # Query with custom display format
            ("Show bugs", "list", None, None, None, None, None, None),
            
            # Query with custom title and description
            ("Show critical items", "table", "Critical Issues", "High priority items that need attention", None, None, None, None),
            
            # Query with custom fields
            ("Show merge requests", "table", None, None, "title, author, state, updated", None, None, None),
            
            # Query with custom limit and sort
            ("Show recent issues", "table", None, None, None, 20, "updated desc", None),
            
            # Query with collapsed view
            ("Show all tasks", "orderedList", None, None, None, None, None, True),
            
            # Query with all custom parameters
            ("Show my work", "table", "My Work Items", "All items assigned to me", "title, state, due, updated", 15, "due asc", False),
        ],
    )
    async def test_custom_parameters(
        self, query, display, title, description, fields, limit, sort, collapsed, metadata
    ):
        """Test that custom parameters are properly handled."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        kwargs = {"query": query}
        if display is not None:
            kwargs["display"] = display
        if title is not None:
            kwargs["title"] = title
        if description is not None:
            kwargs["description"] = description
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if sort is not None:
            kwargs["sort"] = sort
        if collapsed is not None:
            kwargs["collapsed"] = collapsed
        
        response = await tool._arun(**kwargs)
        response_data = json.loads(response)
        
        assert response_data["success"] is True
        assert "glql" in response_data
        
        glql_output = response_data["glql"]
        lines = glql_output.split("\n")
        
        # Check display format
        expected_display = display or "table"
        assert f"display: {expected_display}" in lines
        
        # Check title (either custom or auto-generated)
        title_line = next((line for line in lines if line.startswith("title: ")), None)
        assert title_line is not None
        if title:
            assert f"title: {title}" in lines
        
        # Check description if provided
        if description:
            assert f"description: {description}" in lines
        
        # Check fields (either custom or auto-selected)
        fields_line = next((line for line in lines if line.startswith("fields: ")), None)
        assert fields_line is not None
        if fields:
            assert f"fields: {fields}" in lines
        
        # Check limit
        expected_limit = limit or 10
        assert f"limit: {expected_limit}" in lines
        
        # Check sort (either custom or auto-selected)
        sort_line = next((line for line in lines if line.startswith("sort: ")), None)
        assert sort_line is not None
        if sort:
            assert f"sort: {sort}" in lines
        
        # Check collapsed
        expected_collapsed = collapsed if collapsed is not None else False
        assert f"collapsed: {str(expected_collapsed).lower()}" in lines

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,expected_title",
        [
            ("Show my issues", "My Issues"),
            ("Show my tasks", "My Tasks"),
            ("Show merge requests", "Merge Requests"),
            ("Show MR", "Merge Requests"),
            ("Show epics", "Epics"),
            ("Show bugs", "Bug Reports"),
            ("Show overdue items", "Overdue Items"),
            ("Show items that need review", "Review Queue"),
            ("Show critical issues", "Critical Items"),
            ("Show random stuff", "Query Results"),  # Default case
        ],
    )
    async def test_title_generation(self, query, expected_title, metadata):
        """Test that titles are auto-generated correctly based on query content."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        response = await tool._arun(query=query)
        response_data = json.loads(response)
        
        assert response_data["success"] is True
        glql_output = response_data["glql"]
        assert f"title: {expected_title}" in glql_output

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,expected_fields_parts",
        [
            ("Show my issues", ["title", "state", "assignee", "updated"]),
            ("Show merge requests", ["title", "author", "sourceBranch"]),
            ("Show bugs with labels", ["title", "state", "labels", "updated"]),
            ("Show overdue tasks", ["title", "state", "due", "updated"]),
            ("Show items that need review", ["title", "author", "sourceBranch", "reviewer"]),
            ("Show health status items", ["title", "state", "health", "updated"]),
            ("Show milestone items", ["title", "state", "milestone", "updated"]),
            ("Show created items", ["title", "state", "created"]),
        ],
    )
    async def test_field_selection(self, query, expected_fields_parts, metadata):
        """Test that fields are auto-selected correctly based on query content."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        response = await tool._arun(query=query)
        response_data = json.loads(response)
        
        assert response_data["success"] is True
        glql_output = response_data["glql"]
        
        # Extract fields line
        fields_line = None
        for line in glql_output.split("\n"):
            if line.startswith("fields: "):
                fields_line = line[8:]  # Remove "fields: " prefix
                break
        
        assert fields_line is not None, "Fields line not found in GLQL output"
        
        # Check that expected field parts are present
        for expected_field in expected_fields_parts:
            assert expected_field in fields_line, f"Expected field '{expected_field}' in fields '{fields_line}'"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query,expected_sort",
        [
            ("Show overdue issues", "due asc"),
            ("Show recent issues", "updated desc"),
            ("Show latest items", "updated desc"),
            ("Show oldest issues", "created asc"),
            ("Show created items", "created desc"),
            ("Show priority issues", "updated desc"),
            ("Show random stuff", "updated desc"),  # Default case
        ],
    )
    async def test_sort_selection(self, query, expected_sort, metadata):
        """Test that sort order is auto-selected correctly based on query content."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        response = await tool._arun(query=query)
        response_data = json.loads(response)
        
        assert response_data["success"] is True
        glql_output = response_data["glql"]
        assert f"sort: {expected_sort}" in glql_output

    @pytest.mark.asyncio
    async def test_glql_output_format(self, metadata):
        """Test that the GLQL output has the correct format."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        response = await tool._arun(
            query="Show my issues",
            display="table",
            title="My Issues",
            description="Issues assigned to me",
            fields="title, state, updated",
            limit=15,
            sort="updated desc",
            collapsed=True
        )
        response_data = json.loads(response)
        
        assert response_data["success"] is True
        glql_output = response_data["glql"]
        
        expected_lines = [
            "```glql",
            "display: table",
            "title: My Issues",
            "description: Issues assigned to me",
            "fields: title, state, updated",
            "limit: 15",
            "sort: updated desc",
            "collapsed: true",
            "query: assignee = currentUser()",
            "```"
        ]
        
        actual_lines = glql_output.split("\n")
        
        # Check that all expected lines are present
        for expected_line in expected_lines:
            assert expected_line in actual_lines, f"Expected line '{expected_line}' not found in output"
        
        # Check that it starts and ends with code block markers
        assert actual_lines[0] == "```glql"
        assert actual_lines[-1] == "```"

    @pytest.mark.asyncio
    async def test_default_query_fallback(self, metadata):
        """Test that when no specific criteria are found, it defaults to open issues."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        response = await tool._arun(query="Show me something random")
        response_data = json.loads(response)
        
        assert response_data["success"] is True
        glql_output = response_data["glql"]
        assert "query: state = opened" in glql_output

    @pytest.mark.asyncio
    async def test_limit_validation(self, metadata):
        """Test that limit parameter is properly validated."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        # Test valid limits
        for limit in [1, 50, 100]:
            response = await tool._arun(query="Show issues", limit=limit)
            response_data = json.loads(response)
            assert response_data["success"] is True
            assert f"limit: {limit}" in response_data["glql"]

    @pytest.mark.asyncio
    async def test_error_handling(self, metadata):
        """Test error handling when something goes wrong."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        # Mock an internal method to raise an exception
        original_method = tool._convert_to_glql
        tool._convert_to_glql = Mock(side_effect=Exception("Test error"))
        
        response = await tool._arun(query="Show issues")
        response_data = json.loads(response)
        
        assert response_data["success"] is False
        assert "error" in response_data
        assert "Test error" in response_data["error"]
        
        # Restore original method
        tool._convert_to_glql = original_method

    @pytest.mark.asyncio
    async def test_complex_query_combinations(self, metadata):
        """Test complex queries with multiple criteria."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        test_cases = [
            {
                "query": "Show my open critical bugs that are overdue",
                "expected_parts": [
                    "assignee = currentUser()",
                    "state = opened",
                    "label = ~critical",
                    "label = ~bug",
                    "due < today()"
                ]
            },
            {
                "query": "Show merge requests assigned to @john that need review",
                "expected_parts": [
                    "assignee = @john",
                    "type = MergeRequest",
                    "reviewer = currentUser()",
                    "state = opened"
                ]
            },
            {
                "query": "Show high priority features created today",
                "expected_parts": [
                    "label = ~\"priority::high\"",
                    "label = ~feature",
                    "created = today()"
                ]
            }
        ]
        
        for test_case in test_cases:
            response = await tool._arun(query=test_case["query"])
            response_data = json.loads(response)
            
            assert response_data["success"] is True
            
            # Extract query line
            glql_lines = response_data["glql"].split("\n")
            query_line = None
            for line in glql_lines:
                if line.startswith("query: "):
                    query_line = line[7:]
                    break
            
            assert query_line is not None
            
            # Check all expected parts are present
            for expected_part in test_case["expected_parts"]:
                assert expected_part in query_line, f"Expected '{expected_part}' in '{query_line}' for query '{test_case['query']}'"

    def test_format_display_message(self, metadata):
        """Test the format_display_message method."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        # Test with basic input
        input_data = NaturalLangaugeQueryInput(query="Show my issues")
        message = tool.format_display_message(input_data)
        expected_message = "Convert natural language query to GLQL: 'Show my issues'"
        assert message == expected_message
        
        # Test with complex query
        input_data = NaturalLangaugeQueryInput(
            query="Show critical bugs assigned to me that are overdue",
            display="table",
            limit=20
        )
        message = tool.format_display_message(input_data)
        expected_message = "Convert natural language query to GLQL: 'Show critical bugs assigned to me that are overdue'"
        assert message == expected_message

    @pytest.mark.asyncio
    async def test_project_and_group_patterns(self, metadata):
        """Test project and group specific patterns."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        test_cases = [
            ("Show issues in project frontend", ["project = \"frontend\""]),
            ("Show items in group engineering", ["group = \"engineering\""]),
        ]
        
        for query, expected_parts in test_cases:
            response = await tool._arun(query=query)
            response_data = json.loads(response)
            
            assert response_data["success"] is True
            
            # Extract query line
            glql_lines = response_data["glql"].split("\n")
            query_line = None
            for line in glql_lines:
                if line.startswith("query: "):
                    query_line = line[7:]
                    break
            
            assert query_line is not None
            
            for expected_part in expected_parts:
                assert expected_part in query_line

    @pytest.mark.asyncio
    async def test_input_validation_edge_cases(self, metadata):
        """Test edge cases for input validation."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        # Test empty query
        response = await tool._arun(query="")
        response_data = json.loads(response)
        assert response_data["success"] is True  # Should still work with default fallback
        
        # Test very long query
        long_query = "Show " + "very " * 100 + "long query"
        response = await tool._arun(query=long_query)
        response_data = json.loads(response)
        assert response_data["success"] is True
        
        # Test query with special characters
        special_query = "Show issues with @#$%^&*() characters"
        response = await tool._arun(query=special_query)
        response_data = json.loads(response)
        assert response_data["success"] is True

    @pytest.mark.asyncio
    async def test_all_display_formats(self, metadata):
        """Test all supported display formats."""
        tool = NaturalLangaugeQuery(metadata=metadata)
        
        display_formats = ["table", "list", "orderedList"]
        
        for display_format in display_formats:
            response = await tool._arun(query="Show issues", display=display_format)
            response_data = json.loads(response)
            
            assert response_data["success"] is True
            assert f"display: {display_format}" in response_data["glql"]