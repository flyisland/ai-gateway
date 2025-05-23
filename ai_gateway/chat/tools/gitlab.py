from typing import Optional

from gitlab_cloud_connector import GitLabUnitPrimitive

from ai_gateway.chat.tools.base import BaseRemoteTool
from ai_gateway.chat.tools.prompt_loader import load_tool_prompt

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

    @property
    def description(self) -> str:
        return load_tool_prompt("issue_reader")["description"]

    @property
    def example(self) -> str:
        return load_tool_prompt("issue_reader")["example"]


class GitlabDocumentation(BaseRemoteTool):
    name: str = "gitlab_documentation"
    resource: str = "documentation answers"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.DOCUMENTATION_SEARCH
    min_required_gl_version: Optional[str] = None

    @property
    def description(self) -> str:
        return load_tool_prompt("gitlab_documentation")["description"]

    @property
    def example(self) -> str:
        return load_tool_prompt("gitlab_documentation")["example"]


class SelfHostedGitlabDocumentation(BaseRemoteTool):
    name: str = "gitlab_documentation"
    resource: str = "documentation answers"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.DOCUMENTATION_SEARCH
    min_required_gl_version: Optional[str] = None

    @property
    def description(self) -> str:
        return load_tool_prompt("self_hosted_gitlab_documentation")["description"]

    @property
    def example(self) -> str:
        return load_tool_prompt("self_hosted_gitlab_documentation")["example"]


class EpicReader(BaseRemoteTool):
    name: str = "epic_reader"
    resource: str = "epics"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_EPIC
    min_required_gl_version: Optional[str] = None

    @property
    def description(self) -> str:
        return load_tool_prompt("epic_reader")["description"]

    @property
    def example(self) -> str:
        return load_tool_prompt("epic_reader")["example"]


class CommitReader(BaseRemoteTool):
    name: str = "commit_reader"
    resource: str = "commits"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_COMMIT
    min_required_gl_version: Optional[str] = "17.5.0-pre"

    @property
    def description(self) -> str:
        return load_tool_prompt("commit_reader")["description"]

    @property
    def example(self) -> str:
        return load_tool_prompt("commit_reader")["example"]


class BuildReader(BaseRemoteTool):
    name: str = "build_reader"
    resource: str = "builds"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_BUILD
    min_required_gl_version: Optional[str] = "17.5.0-pre"

    @property
    def description(self) -> str:
        return load_tool_prompt("build_reader")["description"]

    @property
    def example(self) -> str:
        return load_tool_prompt("build_reader")["example"]


class MergeRequestReader(BaseRemoteTool):
    name: str = "merge_request_reader"
    resource: str = "merge_requests"
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_MERGE_REQUEST
    min_required_gl_version: Optional[str] = "17.5.0-pre"

    @property
    def description(self) -> str:
        return load_tool_prompt("merge_request_reader")["description"]

    @property
    def example(self) -> str:
        return load_tool_prompt("merge_request_reader")["example"]
