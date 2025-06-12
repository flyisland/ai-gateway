"""Tests for tool permission mapping."""

import pytest
from unittest.mock import Mock
from gitlab_cloud_connector import GitLabUnitPrimitive

from duo_workflow_service import tools
from duo_workflow_service.components.tool_permissions import (
    get_required_unit_primitive,
    is_tool_permission_exempt,
    user_can_access_tool,
    TOOL_PERMISSION_MAPPING,
    PERMISSION_EXEMPT_TOOLS,
)


class TestToolPermissions:
    """Test tool permission functionality."""

    def test_get_required_unit_primitive_for_epic_tools(self):
        """Test that epic tools require ASK_EPIC permission."""
        assert get_required_unit_primitive(tools.CreateEpic) == GitLabUnitPrimitive.ASK_EPIC
        assert get_required_unit_primitive(tools.GetEpic) == GitLabUnitPrimitive.ASK_EPIC
        assert get_required_unit_primitive(tools.ListEpics) == GitLabUnitPrimitive.ASK_EPIC
        assert get_required_unit_primitive(tools.UpdateEpic) == GitLabUnitPrimitive.ASK_EPIC

    def test_get_required_unit_primitive_for_issue_tools(self):
        """Test that issue tools require ASK_ISSUE permission."""
        assert get_required_unit_primitive(tools.CreateIssue) == GitLabUnitPrimitive.ASK_ISSUE
        assert get_required_unit_primitive(tools.GetIssue) == GitLabUnitPrimitive.ASK_ISSUE
        assert get_required_unit_primitive(tools.ListIssues) == GitLabUnitPrimitive.ASK_ISSUE
        assert get_required_unit_primitive(tools.UpdateIssue) == GitLabUnitPrimitive.ASK_ISSUE

    def test_get_required_unit_primitive_for_merge_request_tools(self):
        """Test that merge request tools require ASK_MERGE_REQUEST permission."""
        assert get_required_unit_primitive(tools.CreateMergeRequest) == GitLabUnitPrimitive.ASK_MERGE_REQUEST
        assert get_required_unit_primitive(tools.GetMergeRequest) == GitLabUnitPrimitive.ASK_MERGE_REQUEST

    def test_get_required_unit_primitive_for_build_tools(self):
        """Test that build tools require ASK_BUILD permission."""
        assert get_required_unit_primitive(tools.GetLogsFromJob) == GitLabUnitPrimitive.ASK_BUILD
        assert get_required_unit_primitive(tools.GetPipelineErrorsForMergeRequest) == GitLabUnitPrimitive.ASK_BUILD

    def test_get_required_unit_primitive_for_commit_tools(self):
        """Test that commit tools require ASK_COMMIT permission."""
        assert get_required_unit_primitive(tools.GetCommit) == GitLabUnitPrimitive.ASK_COMMIT
        assert get_required_unit_primitive(tools.ListCommits) == GitLabUnitPrimitive.ASK_COMMIT

    def test_get_required_unit_primitive_for_unknown_tool(self):
        """Test that unknown tools return None."""
        class UnknownTool:
            pass
        
        assert get_required_unit_primitive(UnknownTool) is None

    def test_is_tool_permission_exempt_for_workflow_tools(self):
        """Test that workflow management tools are exempt from permissions."""
        assert is_tool_permission_exempt(tools.CreatePlan) is True
        assert is_tool_permission_exempt(tools.AddNewTask) is True
        assert is_tool_permission_exempt(tools.GetPlan) is True
        assert is_tool_permission_exempt(tools.HandoverTool) is True

    def test_is_tool_permission_exempt_for_gitlab_tools(self):
        """Test that GitLab tools are not exempt from permissions."""
        assert is_tool_permission_exempt(tools.CreateEpic) is False
        assert is_tool_permission_exempt(tools.GetIssue) is False

    def test_user_can_access_tool_with_permission(self):
        """Test that user can access tool when they have the required permission."""
        mock_user = Mock()
        mock_user.can.return_value = True
        
        assert user_can_access_tool(mock_user, tools.CreateEpic) is True
        mock_user.can.assert_called_with(GitLabUnitPrimitive.ASK_EPIC)

    def test_user_cannot_access_tool_without_permission(self):
        """Test that user cannot access tool when they lack the required permission."""
        mock_user = Mock()
        mock_user.can.return_value = False
        
        assert user_can_access_tool(mock_user, tools.CreateEpic) is False
        mock_user.can.assert_called_with(GitLabUnitPrimitive.ASK_EPIC)

    def test_user_can_access_exempt_tool(self):
        """Test that user can always access exempt tools."""
        mock_user = Mock()
        # Don't set up mock_user.can since it shouldn't be called
        
        assert user_can_access_tool(mock_user, tools.CreatePlan) is True
        mock_user.can.assert_not_called()

    def test_user_can_access_unknown_tool(self):
        """Test that user can access tools not in the permission mapping."""
        mock_user = Mock()
        
        class UnknownTool:
            pass
        
        assert user_can_access_tool(mock_user, UnknownTool) is True
        mock_user.can.assert_not_called()

    def test_all_mapped_tools_have_valid_primitives(self):
        """Test that all tools in the mapping have valid GitLab unit primitives."""
        for tool_class, primitive in TOOL_PERMISSION_MAPPING.items():
            assert isinstance(primitive, GitLabUnitPrimitive)
            assert hasattr(tool_class, '__name__')  # Ensure it's a proper class

    def test_exempt_tools_are_not_in_permission_mapping(self):
        """Test that exempt tools are not in the permission mapping."""
        for tool_class in PERMISSION_EXEMPT_TOOLS:
            assert tool_class not in TOOL_PERMISSION_MAPPING