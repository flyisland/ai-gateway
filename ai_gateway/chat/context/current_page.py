from typing import Literal, Union

from pydantic import BaseModel

__all__ = [
    "Context",
    "PageContext",
    "CurrentPageContext",
]


class Context(BaseModel, frozen=True):  # type: ignore[call-arg]
    """
    Represents current page context and gets its prompt content from GitLab application.
    This class is deprecated but is needed to process requests from
    GitLab instances earlier than 17.9. This class should be deleted as soon as we
    stop supporting GitLab 17.9, that should happen after two major releases.
    """

    type: Literal["issue", "epic", "merge_request", "commit", "build"]
    content: str


class PageContext(BaseModel):
    """
    Represents current page context. Is a parent class for individual GitLab AI resources.
    Field type should be overridden in the subclass as a Literal.
    """

    type: str


CurrentPageContext = Union[Context, PageContext]


class CiBuildContext(PageContext):
    type: Literal["build"]


class CommitContext(PageContext):
    type: Literal["commit"]
    title: str


class EpicContext(PageContext):
    type: Literal["epic"]
    title: str


class IssueContext(PageContext):
    type: Literal["issue"]
    title: str


class MergeRequestContext(PageContext):
    type: Literal["merge_request"]
    title: str
