from typing import Literal, Union

from pydantic import BaseModel

__all__ = ["Context", "IssueContext", "MergeRequestContext", "PageContext"]


class Context(BaseModel, frozen=True):  # type: ignore[call-arg]
    type: Literal["issue", "epic", "merge_request", "commit", "build"]
    content: str


class CiBuildContext(BaseModel):
    type: Literal["build"]


class CommitContext(BaseModel):
    type: Literal["commit"]
    title: str


class EpicContext(BaseModel):
    type: Literal["epic"]
    title: str


class IssueContext(BaseModel):
    type: Literal["issue"]
    title: str


class MergeRequestContext(BaseModel):
    type: Literal["merge_request"]
    title: str


PageContext = Union[Context, CiBuildContext, CommitContext, EpicContext, IssueContext, MergeRequestContext]
