from typing import Literal, Union
from pydantic import BaseModel

__all__ = [
    "Context",
    "IssueContext",
    "MergeRequestContext",
    "PageContext"
]


class Context(BaseModel, frozen=True):  # type: ignore[call-arg]
    type: Literal["issue", "epic", "merge_request", "commit", "build"]
    content: str


class IssueContext(BaseModel):
    type: Literal["issue"]
    title: str


class EpicContext(Context):
    type: Literal["epic"] = "epic"


class MergeRequestContext(BaseModel):
    type: Literal["merge_request"]
    title: str
    enhanced_context: bool = False


class CommitContext(Context):
    type: Literal["commit"] = "commit"


class BuildContext(Context):
    type: Literal["build"] = "build"


PageContext = Union[Context, IssueContext, MergeRequestContext]
