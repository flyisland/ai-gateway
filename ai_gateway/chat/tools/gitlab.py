from textwrap import dedent
from typing import Optional

from gitlab_cloud_connector import GitLabUnitPrimitive

from ai_gateway.chat.tools.base import BaseRemoteTool

__all__ = [
    "CommitReader",
    "MergeRequestReader",
    "IssueReader",
    "GitlabDocumentation",
    "SelfHostedGitlabDocumentation",
    "EpicReader",
    "BuildReader",
]


class IssueReader(BaseRemoteTool):
    name: str = "issue_reader"
    resource: str = "issues"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_ISSUE
    min_required_gl_version: Optional[str] = None

    description: str = dedent(
        """\
        Retrieves content of a specific issue. Use ONLY when:
        1. User provides a valid issue ID
        2. User is viewing a specific issue URL or provides a specific URL
        
        DO NOT use to search for issues by description or keywords.
        
        Action Input: Original user question
        
        Reject inputs without valid identifiers."""
    )

    example: str = dedent(
        """\
        Question: Please identify the author of #123 issue
        Thought: Need to use "issue_reader" to retrieve issue content.
        Action: issue_reader
        Action Input: Please identify the author of #123 issue"""
    )


class GitlabDocumentation(BaseRemoteTool):
    name: str = "gitlab_documentation"
    resource: str = "documentation answers"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.DOCUMENTATION_SEARCH
    min_required_gl_version: Optional[str] = None

    description: str = dedent(
        """\
        Answers questions about GitLab features including projects, groups, issues, 
        merge requests, epics, work items, milestones, labels, CI/CD pipelines, and git repositories."""
    )

    example: str = dedent(
        """\
        Question: How do I set up a new project?
        Thought: Question about GitLab functionality. Use "gitlab_documentation".
        Action: gitlab_documentation
        Action Input: How do I set up a new project?"""
    )


class SelfHostedGitlabDocumentation(BaseRemoteTool):
    name: str = "gitlab_documentation"
    resource: str = "documentation answers"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.DOCUMENTATION_SEARCH
    min_required_gl_version: Optional[str] = None

    description: str = dedent(
        """\
        Answers questions about GitLab features including projects, groups, issues, 
        merge requests, epics, work items, milestones, labels, CI/CD pipelines, and git repositories."""
    )

    example: str = dedent(
        """
        Question: How do I set up a new project?
        Thought: Question about GitLab functionality. Keep action input concise without punctuation.
        Action: gitlab_documentation
        Action Input: set up project
        """
    )


class EpicReader(BaseRemoteTool):
    name: str = "epic_reader"
    resource: str = "epics"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_EPIC
    min_required_gl_version: Optional[str] = None

    description: str = dedent(
        """\
        Retrieves content of a specific epic or work item. Use ONLY when:
        1. User provides a valid epic/work item ID
        2. User is viewing a specific epic/work item URL or provides a specific URL
        
        DO NOT use to search for epics/work items by description or keywords.
        
        Action Input: Original user question
        
        Reject inputs without valid identifiers."""
    )

    example: str = dedent(
        """\
        Question: Please identify the author of &123 epic.
        Thought: Need to use "epic_reader" to retrieve epic content.
        Action: epic_reader
        Action Input: Please identify the author of &123 epic."""
    )


class CommitReader(BaseRemoteTool):
    name: str = "commit_reader"
    resource: str = "commits"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_COMMIT
    min_required_gl_version: Optional[str] = "17.5.0-pre"

    description: str = dedent(
        """\
        Retrieves content of a specific commit. Use ONLY when:
        1. User provides a valid commit ID
        2. User is viewing a specific commit URL or provides a specific URL
        
        DO NOT use to search for commits by description or keywords.
        
        Action Input: Original user question
        
        Reject inputs without valid identifiers."""
    )

    example: str = dedent(
        """\
        Question: Please identify the author of #123 commit
        Thought: Need to use "commit_reader" to retrieve commit content.
        Action: commit_reader
        Action Input: Please identify the author of #123 commit"""
    )


class BuildReader(BaseRemoteTool):
    name: str = "build_reader"
    resource: str = "builds"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_BUILD
    min_required_gl_version: Optional[str] = "17.5.0-pre"

    description: str = dedent(
        """\
        Retrieves content of a specific build. Use ONLY when:
        1. User provides a valid build ID
        2. User is viewing a specific build URL or provides a specific URL
        
        DO NOT use to search for builds by description or keywords.
        
        Action Input: Original user question
        
        Reject inputs without valid identifiers."""
    )

    example: str = dedent(
        """\
        Question: Please identify the author of &123 build.
        Thought: Need to use "build_reader" to retrieve build content.
        Action: build_reader
        Action Input: Please identify the author of &123 build."""
    )


class MergeRequestReader(BaseRemoteTool):
    name: str = "merge_request_reader"
    resource: str = "merge_requests"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_MERGE_REQUEST
    min_required_gl_version: Optional[str] = "17.5.0-pre"

    description: str = dedent(
        """\
        Retrieves content of a specific merge request. Use ONLY when:
        1. User provides a valid merge request ID
        2. User is viewing a specific merge request URL or provides a specific URL
        
        DO NOT use to search for merge requests by description or keywords.
        
        Action Input: Original user question
        
        Reject inputs without valid identifiers."""
    )

    example: str = dedent(
        """\
        Question: Please identify the author of #123 merge request
        Thought: Need to use "merge_request_reader" to retrieve merge request content.
        Action: merge_request_reader
        Action Input: Please identify the author of #123 merge request"""
    )