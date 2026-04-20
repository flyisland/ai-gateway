"""Tool execution tracking context variables."""

from contextvars import ContextVar

type ToolExecutions = list[str]

tool_executions: ContextVar[ToolExecutions | None] = ContextVar(
    "tool_executions", default=None
)


def init_tool_executions() -> None:
    """Initialize the tool executions context variable with an empty list."""
    tool_executions.set([])


def get_tool_executions() -> ToolExecutions | None:
    """Retrieve and reset the tool executions context variable.

    Returns:
        The list of tool names executed in the current context, or None if
        the context variable was never initialized. Resets the context variable
        to None after reading.
    """

    current = tool_executions.get()
    tool_executions.set(None)
    return current
