"""Integration test for user permission-based tool filtering."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from gitlab_cloud_connector import CloudConnectorUser, GitLabUnitPrimitive

from duo_workflow_service.components.tools_registry import ToolsRegistry
from duo_workflow_service.gitlab.http_client import GitlabHttpClient


@pytest.fixture
def gl_http_client():
    return AsyncMock(spec=GitlabHttpClient)


@pytest.fixture
def tool_metadata():
    return {
        "outbox": MagicMock(spec=asyncio.Queue),
        "inbox": MagicMock(spec=asyncio.Queue),
        "gitlab_client": AsyncMock(spec=GitlabHttpClient),
        "gitlab_host": "gitlab.example.com",
    }


class TestUserPermissionFiltering:
    """Integration tests for user permission-based tool filtering."""

    @pytest.mark.asyncio
    async def test_epic_specialist_user(self, gl_http_client, tool_metadata):
        """Test a user who only has epic permissions."""
        # Create a user that only has ASK_EPIC permission
        epic_user = MagicMock(spec=CloudConnectorUser)
        epic_user.can.side_effect = lambda primitive: primitive == GitLabUnitPrimitive.ASK_EPIC

        workflow_config = {
            "id": "test_workflow",
            "agent_privileges_names": ["read_write_gitlab"],
        }

        registry = await ToolsRegistry.configure(
            workflow_config=workflow_config,
            gl_http_client=gl_http_client,
            outbox=tool_metadata["outbox"],
            inbox=tool_metadata["inbox"],
            gitlab_host=tool_metadata["gitlab_host"],
            user=epic_user,
        )

        # Epic tools should be available
        epic_tools = ["create_epic", "get_epic", "list_epics", "update_epic", "list_epic_notes", "get_epic_note"]
        for tool_name in epic_tools:
            assert tool_name in registry._enabled_tools, f"Epic tool {tool_name} should be available"

        # Issue tools should NOT be available
        issue_tools = ["create_issue", "get_issue", "list_issues", "update_issue", "create_issue_note"]
        for tool_name in issue_tools:
            assert tool_name not in registry._enabled_tools, f"Issue tool {tool_name} should not be available"

        # Merge request tools should NOT be available
        mr_tools = ["create_merge_request", "get_merge_request", "create_merge_request_note"]
        for tool_name in mr_tools:
            assert tool_name not in registry._enabled_tools, f"MR tool {tool_name} should not be available"

        # Workflow management tools should still be available (exempt from permissions)
        workflow_tools = ["create_plan", "add_new_task", "get_plan", "set_task_status"]
        for tool_name in workflow_tools:
            assert tool_name in registry._enabled_tools, f"Workflow tool {tool_name} should be available"

    @pytest.mark.asyncio
    async def test_multi_permission_user(self, gl_http_client, tool_metadata):
        """Test a user with multiple GitLab permissions."""
        # Create a user with ASK_EPIC and ASK_ISSUE permissions
        multi_user = MagicMock(spec=CloudConnectorUser)
        multi_user.can.side_effect = lambda primitive: primitive in [
            GitLabUnitPrimitive.ASK_EPIC,
            GitLabUnitPrimitive.ASK_ISSUE,
        ]

        workflow_config = {
            "id": "test_workflow",
            "agent_privileges_names": ["read_write_gitlab"],
        }

        registry = await ToolsRegistry.configure(
            workflow_config=workflow_config,
            gl_http_client=gl_http_client,
            outbox=tool_metadata["outbox"],
            inbox=tool_metadata["inbox"],
            gitlab_host=tool_metadata["gitlab_host"],
            user=multi_user,
        )

        # Both epic and issue tools should be available
        epic_tools = ["create_epic", "get_epic", "list_epics"]
        issue_tools = ["create_issue", "get_issue", "list_issues"]
        
        for tool_name in epic_tools + issue_tools:
            assert tool_name in registry._enabled_tools, f"Tool {tool_name} should be available"

        # Merge request tools should NOT be available
        mr_tools = ["create_merge_request", "get_merge_request"]
        for tool_name in mr_tools:
            assert tool_name not in registry._enabled_tools, f"MR tool {tool_name} should not be available"

    @pytest.mark.asyncio
    async def test_no_gitlab_permissions_user(self, gl_http_client, tool_metadata):
        """Test a user with no GitLab-specific permissions."""
        # Create a user with only COMPLETE_CODE permission (for file operations)
        limited_user = MagicMock(spec=CloudConnectorUser)
        limited_user.can.side_effect = lambda primitive: primitive == GitLabUnitPrimitive.COMPLETE_CODE

        workflow_config = {
            "id": "test_workflow",
            "agent_privileges_names": ["read_write_gitlab", "read_write_files"],
        }

        registry = await ToolsRegistry.configure(
            workflow_config=workflow_config,
            gl_http_client=gl_http_client,
            outbox=tool_metadata["outbox"],
            inbox=tool_metadata["inbox"],
            gitlab_host=tool_metadata["gitlab_host"],
            user=limited_user,
        )

        # No GitLab tools should be available
        gitlab_tools = [
            "create_epic", "get_epic", "create_issue", "get_issue", 
            "create_merge_request", "get_merge_request"
        ]
        for tool_name in gitlab_tools:
            assert tool_name not in registry._enabled_tools, f"GitLab tool {tool_name} should not be available"

        # File system tools should be available (user has COMPLETE_CODE permission)
        file_tools = ["read_file", "create_file_with_contents", "edit_file", "list_dir"]
        for tool_name in file_tools:
            assert tool_name in registry._enabled_tools, f"File tool {tool_name} should be available"

        # Workflow management tools should still be available (exempt from permissions)
        workflow_tools = ["create_plan", "add_new_task", "get_plan"]
        for tool_name in workflow_tools:
            assert tool_name in registry._enabled_tools, f"Workflow tool {tool_name} should be available"

    @pytest.mark.asyncio
    async def test_superuser_with_all_permissions(self, gl_http_client, tool_metadata):
        """Test a user with all permissions."""
        # Create a user with all permissions
        superuser = MagicMock(spec=CloudConnectorUser)
        superuser.can.return_value = True

        workflow_config = {
            "id": "test_workflow",
            "agent_privileges_names": ["read_write_gitlab", "read_write_files", "run_commands"],
        }

        registry = await ToolsRegistry.configure(
            workflow_config=workflow_config,
            gl_http_client=gl_http_client,
            outbox=tool_metadata["outbox"],
            inbox=tool_metadata["inbox"],
            gitlab_host=tool_metadata["gitlab_host"],
            user=superuser,
        )

        # All configured tools should be available
        expected_tools = {
            # Workflow tools (always available)
            "create_plan", "add_new_task", "get_plan", "set_task_status",
            # GitLab tools
            "create_epic", "get_epic", "list_epics", "update_epic",
            "create_issue", "get_issue", "list_issues", "update_issue",
            "create_merge_request", "get_merge_request", "update_merge_request",
            # File tools
            "read_file", "create_file_with_contents", "edit_file", "list_dir",
            # Command tools
            "run_command",
            # No-op tools
            "handover_tool", "request_user_clarification_tool",
        }

        for tool_name in expected_tools:
            assert tool_name in registry._enabled_tools, f"Tool {tool_name} should be available for superuser"