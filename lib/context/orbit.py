"""Orbit tool usage tracking context variables.

These context variables track Orbit tool calls within a workflow session for telemetry (Snowplow events) and billing
(orbit_called flag).
"""

from contextvars import ContextVar

# MCP server name prefix for Orbit tools. Workhorse prefixes tool names
# with the server name (e.g., "orbit" + "_" + "query_graph" = "orbit_query_graph").
# Update this if the Orbit MCP server is registered under a different name.
ORBIT_TOOL_PREFIX = "orbit_"

orbit_tool_call_count: ContextVar[int] = ContextVar("orbit_tool_call_count", default=0)
total_tool_call_count: ContextVar[int] = ContextVar("total_tool_call_count", default=0)
