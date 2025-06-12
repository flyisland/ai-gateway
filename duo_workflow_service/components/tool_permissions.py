"""Tool permission mapping for GitLab unit primitives.

This module defines the mapping between workflow tools and the GitLab unit primitives
required to access them. This enables filtering tools based on user permissions.
"""

from typing import Dict, Type, Optional
from langchain.tools import BaseTool
from gitlab_cloud_connector import GitLabUnitPrimitive

from duo_workflow_service import tools


# Mapping of tool classes to their required GitLab unit primitives
TOOL_PERMISSION_MAPPING: Dict[Type[BaseTool], GitLabUnitPrimitive] = {
    # Epic-related tools
    tools.CreateEpic: GitLabUnitPrimitive.ASK_EPIC,
    tools.UpdateEpic: GitLabUnitPrimitive.ASK_EPIC,
    tools.GetEpic: GitLabUnitPrimitive.ASK_EPIC,
    tools.ListEpics: GitLabUnitPrimitive.ASK_EPIC,
    tools.ListEpicNotes: GitLabUnitPrimitive.ASK_EPIC,
    tools.GetEpicNote: GitLabUnitPrimitive.ASK_EPIC,
    
    # Issue-related tools
    tools.CreateIssue: GitLabUnitPrimitive.ASK_ISSUE,
    tools.UpdateIssue: GitLabUnitPrimitive.ASK_ISSUE,
    tools.GetIssue: GitLabUnitPrimitive.ASK_ISSUE,
    tools.ListIssues: GitLabUnitPrimitive.ASK_ISSUE,
    tools.ListIssueNotes: GitLabUnitPrimitive.ASK_ISSUE,
    tools.GetIssueNote: GitLabUnitPrimitive.ASK_ISSUE,
    tools.CreateIssueNote: GitLabUnitPrimitive.ASK_ISSUE,
    
    # Merge Request-related tools
    tools.CreateMergeRequest: GitLabUnitPrimitive.ASK_MERGE_REQUEST,
    tools.UpdateMergeRequest: GitLabUnitPrimitive.ASK_MERGE_REQUEST,
    tools.GetMergeRequest: GitLabUnitPrimitive.ASK_MERGE_REQUEST,
    tools.ListMergeRequestDiffs: GitLabUnitPrimitive.ASK_MERGE_REQUEST,
    tools.ListAllMergeRequestNotes: GitLabUnitPrimitive.ASK_MERGE_REQUEST,
    tools.CreateMergeRequestNote: GitLabUnitPrimitive.ASK_MERGE_REQUEST,
    
    # Build/Job-related tools
    tools.GetLogsFromJob: GitLabUnitPrimitive.ASK_BUILD,
    tools.GetPipelineErrorsForMergeRequest: GitLabUnitPrimitive.ASK_BUILD,
    
    # Commit-related tools
    tools.GetCommit: GitLabUnitPrimitive.ASK_COMMIT,
    tools.ListCommits: GitLabUnitPrimitive.ASK_COMMIT,
    tools.GetCommitDiff: GitLabUnitPrimitive.ASK_COMMIT,
    tools.GetCommitComments: GitLabUnitPrimitive.ASK_COMMIT,
    
    # Search tools - using DOCUMENTATION_SEARCH as they're read-only search operations
    tools.GroupProjectSearch: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    tools.IssueSearch: GitLabUnitPrimitive.ASK_ISSUE,
    tools.MergeRequestSearch: GitLabUnitPrimitive.ASK_MERGE_REQUEST,
    tools.MilestoneSearch: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    tools.UserSearch: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    tools.BlobSearch: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    tools.CommitSearch: GitLabUnitPrimitive.ASK_COMMIT,
    tools.WikiBlobSearch: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    tools.NoteSearch: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    
    # Project and repository tools - using DOCUMENTATION_SEARCH for read-only operations
    tools.GetProject: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    tools.GetRepositoryFile: GitLabUnitPrimitive.DOCUMENTATION_SEARCH,
    
    # File system tools - these don't require specific GitLab permissions
    # but we'll use COMPLETE_CODE as they're typically used for code operations
    tools.ReadFile: GitLabUnitPrimitive.COMPLETE_CODE,
    tools.WriteFile: GitLabUnitPrimitive.COMPLETE_CODE,
    tools.EditFile: GitLabUnitPrimitive.COMPLETE_CODE,
    tools.ListDir: GitLabUnitPrimitive.COMPLETE_CODE,
    tools.FindFiles: GitLabUnitPrimitive.COMPLETE_CODE,
    tools.Grep: GitLabUnitPrimitive.COMPLETE_CODE,
    tools.Mkdir: GitLabUnitPrimitive.COMPLETE_CODE,
    
    # Git tools
    tools.git.Command: GitLabUnitPrimitive.COMPLETE_CODE,
    
    # Command execution
    tools.RunCommand: GitLabUnitPrimitive.COMPLETE_CODE,
    
    # Workflow context
    tools.GetWorkflowContext: GitLabUnitPrimitive.DUO_WORKFLOW_EXECUTE_WORKFLOW,
}

# Tools that don't require specific permissions (internal workflow tools)
PERMISSION_EXEMPT_TOOLS = {
    tools.CreatePlan,
    tools.AddNewTask,
    tools.RemoveTask,
    tools.UpdateTaskDescription,
    tools.GetPlan,
    tools.SetTaskStatus,
    tools.HandoverTool,
    tools.RequestUserClarificationTool,
}


def get_required_unit_primitive(tool_class: Type[BaseTool]) -> Optional[GitLabUnitPrimitive]:
    """Get the required GitLab unit primitive for a tool class.
    
    Args:
        tool_class: The tool class to check
        
    Returns:
        The required GitLabUnitPrimitive, or None if the tool doesn't require permissions
    """
    return TOOL_PERMISSION_MAPPING.get(tool_class)


def is_tool_permission_exempt(tool_class: Type[BaseTool]) -> bool:
    """Check if a tool is exempt from permission checks.
    
    Args:
        tool_class: The tool class to check
        
    Returns:
        True if the tool is exempt from permission checks
    """
    return tool_class in PERMISSION_EXEMPT_TOOLS


def user_can_access_tool(user, tool_class: Type[BaseTool]) -> bool:
    """Check if a user can access a specific tool.
    
    Args:
        user: CloudConnectorUser instance
        tool_class: The tool class to check
        
    Returns:
        True if the user can access the tool
    """
    # Check if tool is exempt from permission checks
    if is_tool_permission_exempt(tool_class):
        return True
    
    # Get required unit primitive
    required_primitive = get_required_unit_primitive(tool_class)
    if required_primitive is None:
        # If no specific permission is defined, allow access
        return True
    
    # Check if user has the required permission
    return user.can(required_primitive)