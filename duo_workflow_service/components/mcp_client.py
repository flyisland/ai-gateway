"""MCP Client for GitLab MCP Server Integration.

This module provides a client to interact with the GitLab MCP server that exposes GitLab functionality through the Model
Context Protocol (MCP).
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class McpErrorCode(Enum):
    """MCP JSON-RPC error codes according to the spec."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class McpError(Exception):
    """MCP Error representation."""

    code: int
    message: str
    data: Optional[dict[str, Any]] = None


@dataclass
class McpTool:
    """MCP Tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class McpToolResult:
    """Result from MCP tool execution."""

    content: list[dict[str, Any]]
    structured_content: Optional[dict[str, Any]] = None
    is_error: bool = False


class McpClient:
    """Client for communicating with MCP server.

    Provides methods to:
    - Initialize connection with the server
    - List available tools
    - Execute tools with arguments
    - Handle JSON-RPC protocol communication
    """

    def __init__(
        self, server_url: str, token: str, timeout: float = 30.0, max_retries: int = 3
    ):
        """Initialize MCP client.

        Args:
            server_url: URL of the MCP server
            token: Access Token for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        self._request_id = 0
        self._initialized = False
        self._available_tools: list[McpTool] = []

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    def _get_next_request_id(self) -> int:
        """Get next request ID for JSON-RPC."""
        self._request_id += 1
        return self._request_id

    async def _make_request(
        self, method: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Make JSON-RPC request to MCP server.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            JSON-RPC response

        Raises:
            McpError: If the request fails or server returns error
            httpx.HTTPError: For HTTP-level errors
        """
        request_data = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._get_next_request_id(),
        }

        if params is not None:
            request_data["params"] = params

        logger.debug("Making MCP request", method=method, params=params)

        try:
            response = await self._client.post(self.server_url, json=request_data)
            response.raise_for_status()

            # Check if this is a notification method that may not return JSON
            is_notification = method.startswith("notifications/")

            # Handle empty response body for notifications
            if response.text.strip() == "":
                if is_notification:
                    logger.debug("Empty response for notification", method=method)
                    return {"jsonrpc": "2.0", "result": None}

                logger.warning(
                    "Empty response for non-notification method", method=method
                )
                raise McpError(
                    code=McpErrorCode.PARSE_ERROR.value,
                    message="Empty response from server",
                )

            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                if is_notification:
                    # For notifications, treat any parsing error as a successful response
                    logger.debug(
                        "Non-JSON response for notification (treating as success)",
                        method=method,
                        response_text=response.text[
                            :200
                        ],  # Log first 200 chars for debugging
                    )
                    return {"jsonrpc": "2.0", "result": None}

                # For non-notifications, this is still an error
                logger.error(
                    "JSON decode error in MCP response", error=str(e), method=method
                )
                raise McpError(
                    code=McpErrorCode.PARSE_ERROR.value,
                    message="Failed to parse JSON response",
                )

            # Check for JSON-RPC error
            if "error" in response_data:
                error_info = response_data["error"]
                raise McpError(
                    code=error_info.get("code", McpErrorCode.INTERNAL_ERROR.value),
                    message=error_info.get("message", "Unknown error"),
                    data=error_info.get("data"),
                )

            return response_data

        except httpx.HTTPError as e:
            logger.error("HTTP error in MCP request", error=str(e), method=method)
            raise

    async def initialize(self) -> dict[str, Any]:
        """Initialize connection with MCP server.

        Returns:
            Server capabilities and information

        Raises:
            McpError: If initialization fails
        """
        if self._initialized:
            return {"status": "already_initialized"}

        logger.info("Initializing MCP client", endpoint=self.server_url)

        try:
            # Initialize request
            init_response = await self._make_request("initialize")

            # Send initialized notification
            await self._make_request("notifications/initialized")

            self._initialized = True
            logger.info("MCP client initialized successfully")

            return init_response.get("result", {})

        except Exception as e:
            logger.error("Failed to initialize MCP client", error=str(e))
            raise

    async def list_tools(self) -> list[McpTool]:
        """List available tools from MCP server.

        Returns:
            List of available MCP tools

        Raises:
            McpError: If listing tools fails
        """
        if not self._initialized:
            await self.initialize()

        logger.debug("Listing MCP tools")

        try:
            response = await self._make_request("tools/list")
            tools_data = response.get("result", {}).get("tools", [])

            self._available_tools = []
            for tool_data in tools_data:
                tool = McpTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                )
                self._available_tools.append(tool)

            logger.info("Listed MCP tools", count=len(self._available_tools))
            return self._available_tools

        except Exception as e:
            logger.error("Failed to list MCP tools", error=str(e))
            raise

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> McpToolResult:
        """Execute a tool with given arguments.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            McpError: If tool execution fails
        """
        if not self._initialized:
            await self.initialize()

        logger.debug("Calling MCP tool", tool_name=tool_name, arguments=arguments)

        try:
            response = await self._make_request(
                "tools/call", {"name": tool_name, "arguments": arguments}
            )

            result_data = response.get("result", {})

            return McpToolResult(
                content=result_data.get("content", []),
                structured_content=result_data.get("structuredContent"),
                is_error=result_data.get("isError", False),
            )

        except Exception as e:
            logger.error("Failed to call MCP tool", tool_name=tool_name, error=str(e))
            raise

    def get_tool_by_name(self, name: str) -> Optional[McpTool]:
        """Get tool definition by name.

        Args:
            name: Tool name

        Returns:
            Tool definition if found, None otherwise
        """
        return next((tool for tool in self._available_tools if tool.name == name), None)

    def is_initialized(self) -> bool:
        """Check if client is initialized."""
        return self._initialized

    def get_available_tools(self) -> list[McpTool]:
        """Get list of available tools (cached)."""
        return self._available_tools.copy()


class McpClientFactory:
    """Factory for creating MCP clients with different configurations."""

    @staticmethod
    def create_user_client(
        token: str, timeout: float = 30.0, max_retries: int = 3
    ) -> McpClient:
        """Create MCP client configured for user.

        Args:
            token: GitLab Personal Access Token
            timeout: Request timeout
            max_retries: Maximum retries

        Returns:
            Configured MCP client
        """
        return McpClient(
            server_url="https://gitlab.com/api/v4/mcp_server",
            token=token,
            timeout=timeout,
            max_retries=max_retries,
        )


# Exception classes
class McpClientError(Exception):
    """Base exception for MCP client errors."""


class McpConnectionError(McpClientError):
    """Error connecting to MCP server."""


class McpToolError(McpClientError):
    """Error executing MCP tool."""

    def __init__(
        self, message: str, tool_name: str, mcp_error: Optional[McpError] = None
    ):
        super().__init__(message)
        self.tool_name = tool_name
        self.mcp_error = mcp_error
