from typing import Literal, Union

from pydantic import BaseModel

__all__ = ["Context", "IssueContext", "MergeRequestContext", "PageContext"]


class Context(BaseModel, frozen=True):  # type: ignore[call-arg]
    type: Literal["issue", "epic", "merge_request", "commit", "build"]
    content: str


class IssueContext(BaseModel):
    type: Literal["issue"]
    title: str


class MergeRequestContext(BaseModel):
    type: Literal["merge_request"]
    title: str
    enhanced_context: bool = False


PageContext = Union[Context, IssueContext, MergeRequestContext]
