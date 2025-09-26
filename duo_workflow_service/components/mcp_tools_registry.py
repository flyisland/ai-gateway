"""MCP-integrated Tools Registry.

This module provides a tools registry that integrates with the GitLab MCP server, replacing the need for locally defined
GitLab tools with dynamically loaded MCP tools from the GitLab MCP server.
"""

import asyncio
import json
from typing import Any, Optional, Type, Union

import structlog
from gitlab_cloud_connector import CloudConnectorUser
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from ai_gateway.code_suggestions.language_server import LanguageServerVersion
from duo_workflow_service.components.mcp_client import (
    McpClient,
    McpClientFactory,
    McpTool,
)
from duo_workflow_service.components.tools_registry import (
    _DEFAULT_TOOLS,
    NO_OP_TOOLS,
    ToolMetadata,
)
from duo_workflow_service.gitlab.gitlab_api import Project, WorkflowConfig
from duo_workflow_service.gitlab.http_client import GitlabHttpClient
from duo_workflow_service.tools import Toolset, ToolType
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

logger = structlog.get_logger(__name__)


class McpBaseTool(BaseTool):
    """Base class for MCP-backed tools."""

    mcp_tool: McpTool
    mcp_client: McpClient

    def __init__(
        self,
        mcp_tool: McpTool,
        mcp_client: McpClient,
        metadata: Optional[ToolMetadata] = None,
        **kwargs,
    ):
        """Initialize MCP tool.

        Args:
            mcp_tool: MCP tool definition
            mcp_client: MCP client instance
            metadata: Tool metadata for execution
        """
        # Handle both dataclass (input_schema) and protobuf (inputSchema) versions
        if hasattr(mcp_tool, "input_schema"):
            input_schema = mcp_tool.input_schema
        elif hasattr(mcp_tool, "inputSchema"):
            input_schema = mcp_tool.inputSchema
        else:
            input_schema = {}

        args_schema = self._create_args_schema(input_schema, mcp_tool.name)

        super().__init__(
            name=mcp_tool.name,
            description=mcp_tool.description,
            args_schema=args_schema,
            mcp_tool=mcp_tool,
            mcp_client=mcp_client,
            metadata=metadata,
            **kwargs,
        )

    def _create_args_schema(
        self, input_schema: Union[dict[str, Any], str], tool_name: str
    ) -> Optional[Type[BaseModel]]:
        """Create Pydantic model from JSON schema."""
        if not input_schema:
            return None

        try:
            # Handle string JSON schema
            if isinstance(input_schema, str):
                input_schema = json.loads(input_schema)

            # Convert JSON schema to Pydantic model
            # This is a simplified version - we might want to use a library like
            # pydantic-jsonschema for more complex schemas
            annotations = {}
            field_definitions = {}
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])

            for field_name, field_def in properties.items():
                field_type = self._json_type_to_python_type(
                    field_def.get("type", "string")
                )

                # Create proper type annotation
                annotations[field_name] = field_type

                # Create field definition with proper default
                if field_name in required:
                    # Required field - use Field with no default
                    field_definitions[field_name] = Field(...)
                else:
                    # Optional field - use Field with None default
                    field_definitions[field_name] = Field(default=None)

            if annotations:
                # Create class with proper annotations
                class_dict = {"__annotations__": annotations, **field_definitions}
                return type(f"{tool_name}Args", (BaseModel,), class_dict)

        except Exception as e:
            logger.warning(
                "Failed to create args schema for MCP tool",
                tool_name=tool_name,
                error=str(e),
            )

        return None

    def _json_type_to_python_type(self, json_type: str) -> Type:
        """Convert JSON schema type to Python type."""
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return type_mapping.get(json_type, str)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Sync run - not supported for MCP tools."""
        raise NotImplementedError("MCP tools can only be run asynchronously")

    async def _arun(self, **arguments: dict[str, Any]) -> str:
        """Execute MCP tool asynchronously."""
        try:
            result = await self.mcp_client.call_tool(self.mcp_tool.name, arguments)

            if result.is_error:
                logger.error(
                    "MCP tool execution failed",
                    tool_name=self.mcp_tool.name,
                    content=result.content,
                )
                return f"Error executing {self.mcp_tool.name}: {result.content}"

            # Return structured content if available, otherwise return text content
            if result.structured_content:
                return json.dumps(result.structured_content, indent=2)

            # Extract text from content array
            text_parts = []
            for content_item in result.content:
                if content_item.get("type") == "text":
                    text_parts.append(content_item.get("text", ""))

            return "\n".join(text_parts) if text_parts else str(result.content)

        except Exception as e:
            logger.error(
                "Failed to execute MCP tool", tool_name=self.mcp_tool.name, error=str(e)
            )
            return f"Error executing {self.mcp_tool.name}: {str(e)}"

    def format_display_message(
        self, arguments: dict[str, Any], _tool_response: Any = None
    ) -> str:
        """Format display message for the tool execution."""
        return f"Execute MCP tool {self.mcp_tool.name}: {arguments}"


class McpToolsRegistry:
    """Tools registry that integrates with GitLab MCP server.

    This registry dynamically loads tools from the MCP server and provides the same interface as the original
    ToolsRegistry.
    """

    def __init__(
        self,
        enabled_tools: list[str],
        preapproved_tools: list[str],
        tool_metadata: ToolMetadata,
        mcp_client: Optional[McpClient] = None,
        user: Optional[CloudConnectorUser] = None,
        language_server_version: Optional[LanguageServerVersion] = None,
    ):
        """Initialize MCP Tools Registry.

        Args:
            enabled_tools: list of enabled tool privilege names
            preapproved_tools: list of preapproved tool privilege names
            tool_metadata: Metadata for tool execution
            mcp_client: MCP client instance
            user: Cloud connector user for permission checks
            language_server_version: Language server version info
        """
        self.enabled_tools = enabled_tools
        self.preapproved_tools = preapproved_tools
        self.tool_metadata = tool_metadata
        self.mcp_client = mcp_client
        self.user = user
        self.language_server_version = language_server_version

        self._enabled_tools: dict[str, Union[BaseTool, Type[BaseModel]]] = {}
        self._preapproved_tool_names: set[str] = set()
        self._mcp_tool_names: list[str] = []

        self._initialize_default_tools()

    def _initialize_default_tools(self):
        """Initialize default tools that are always available."""
        # Add no-op tools (these don't need execution)
        self._enabled_tools.update(
            {tool_cls.tool_title: tool_cls for tool_cls in NO_OP_TOOLS}  # type: ignore
        )

        # Add default internal tools
        self._enabled_tools.update(
            {tool.name: tool for tool in [tool_cls() for tool_cls in _DEFAULT_TOOLS]}
        )

        # Mark default tools as preapproved
        self._preapproved_tool_names.update(self._enabled_tools.keys())

    async def load_mcp_tools(self) -> None:
        """Load tools from MCP server."""
        if not self.mcp_client:
            logger.warning("No MCP client configured, skipping MCP tool loading")
            return

        try:
            logger.info("Loading MCP tools from server")
            mcp_tools = await self.mcp_client.list_tools()

            for mcp_tool in mcp_tools:
                # Create LangChain-compatible tool from MCP tool
                tool = McpBaseTool(
                    mcp_tool=mcp_tool,
                    mcp_client=self.mcp_client,
                    metadata=self.tool_metadata,
                )

                # Check user permissions if user is provided
                if self.user:
                    tool_primitive = getattr(tool, "unit_primitive", None)
                    if tool_primitive and not self.user.can(tool_primitive):
                        logger.debug(
                            "User lacks permission for MCP tool",
                            tool_name=mcp_tool.name,
                        )
                        continue

                # Check language server version compatibility
                if isinstance(tool, DuoBaseTool) and self.language_server_version:
                    if not self.language_server_version.supports_node_executor_tools():
                        logger.debug(
                            "Language server version doesn't support MCP tool",
                            tool_name=mcp_tool.name,
                        )
                        continue

                self._enabled_tools[tool.name] = tool
                self._mcp_tool_names.append(tool.name)

                # MCP tools are preapproved by default (can be configured)
                if "run_mcp_tools" in self.preapproved_tools:
                    self._preapproved_tool_names.add(tool.name)

            logger.info("Loaded MCP tools", count=len(self._mcp_tool_names))

        except Exception as e:
            logger.error("Failed to load MCP tools", error=str(e))
            # Don't fail the entire registry if MCP tools fail to load

    @classmethod
    async def configure(
        cls,
        workflow_config: WorkflowConfig,
        gl_http_client: GitlabHttpClient,
        outbox: asyncio.Queue,
        inbox: asyncio.Queue,
        project: Optional[Project],
        user: Optional[CloudConnectorUser] = None,
        language_server_version: Optional[LanguageServerVersion] = None,
    ) -> "McpToolsRegistry":
        """Configure and create MCP Tools Registry.

        Args:
            workflow_config: Workflow configuration
            gl_http_client: GitLab HTTP client
            outbox: Outbox queue for actions
            inbox: Inbox queue for events
            project: GitLab project info
            user: Cloud connector user
            language_server_version: Language server version

        Returns:
            Configured McpToolsRegistry instance
        """
        if not workflow_config:
            raise RuntimeError("Failed to find tools configuration for workflow")

        if "agent_privileges_names" not in workflow_config:
            raise RuntimeError(
                f"Failed to find tools configuration for workflow {workflow_config.get('id', 'None')}"
            )

        agent_privileges = workflow_config.get("agent_privileges_names", [])
        preapproved_tools = workflow_config.get(
            "pre_approved_agent_privileges_names", []
        )

        tool_metadata = ToolMetadata(
            outbox=outbox,
            inbox=inbox,
            gitlab_client=gl_http_client,
            gitlab_host=workflow_config.get("gitlab_host", ""),
            project=project,
        )

        # We need to create a new client that is authenticated as the user
        # who initilize the workflow.
        mcp_client = None
        try:
            # Extract the token from the GitLab client
            # Only DirectGitLabHttpClient is supported
            token = gl_http_client.gitlab_token

            mcp_client = McpClientFactory.create_user_client(token=token)
            await mcp_client.initialize()
            logger.info("Created new MCP client for workflow")

        except Exception as e:
            logger.error("Failed to get/create MCP client", error=str(e))

        # Create registry instance
        registry = cls(
            enabled_tools=agent_privileges,
            preapproved_tools=preapproved_tools,
            tool_metadata=tool_metadata,
            mcp_client=mcp_client,
            user=user,
            language_server_version=language_server_version,
        )

        # Load MCP tools if client is available
        if mcp_client:
            await registry.load_mcp_tools()

        return registry

    def get(self, tool_name: str) -> Optional[ToolType]:
        """Get tool by name."""
        return self._enabled_tools.get(tool_name)

    def get_batch(self, tool_names: list[str]) -> list[ToolType]:
        """Get multiple tools by names."""
        return [
            self._enabled_tools[tool_name]
            for tool_name in tool_names
            if tool_name in self._enabled_tools
        ]

    def get_handlers(self, tool_names: list[str]) -> list[BaseTool]:
        """Get tool handlers (BaseTool instances only)."""
        tool_handlers: list[BaseTool] = []
        for tool_name in tool_names:
            handler = self._enabled_tools.get(tool_name)
            if isinstance(handler, BaseTool):
                tool_handlers.append(handler)
        return tool_handlers

    def approval_required(self, tool_name: str) -> bool:
        """Check if a tool requires human approval before execution."""
        return tool_name not in self._preapproved_tool_names

    def toolset(self, tool_names: list[str]) -> Toolset:
        """Create a Toolset instance representing complete collection of tools available to an agent.

        Args:
            tool_names: A list of tool names to include in the Toolset.

        Returns:
            A new Toolset instance containing the requested tools.
        """
        # Add MCP tools to the requested tool names
        all_tool_names = tool_names + self._mcp_tool_names

        all_tools = {
            tool_name: self._enabled_tools[tool_name]
            for tool_name in all_tool_names
            if tool_name in self._enabled_tools
        }

        pre_approved = {
            tool_name
            for tool_name in all_tool_names
            if tool_name in self._preapproved_tool_names
        }

        return Toolset(pre_approved=pre_approved, all_tools=all_tools)

    async def close(self):
        """Clean up resources."""
        if self.mcp_client:
            await self.mcp_client.close()
