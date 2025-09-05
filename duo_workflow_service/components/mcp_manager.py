"""MCP Manager for Server-wide MCP Client Management.

This module manages MCP client instances during server lifecycle, providing centralized access to MCP clients across the
application.
"""

from contextlib import asynccontextmanager
from typing import Optional

import structlog
from dotenv import find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from duo_workflow_service.components.mcp_client import McpClient

logger = structlog.get_logger(__name__)


class McpConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DUO_WORKFLOW_MCP__",
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = False
    server_url: str = "https://gitlab.com/api/v4/mcp_server"
    token: str = ""
    timeout: float = 30.0
    max_retries: int = 3


class McpManager:
    """Manages MCP client connections throughout server lifecycle.

    Provides:
    - Server startup MCP client initialization
    - Centralized client access
    - Graceful shutdown and cleanup
    - Health monitoring and reconnection
    """

    def __init__(self):
        self._client: McpClient = None
        self._client_config: McpConfig = None
        self._initialized = False
        self._shutdown = False

    async def initialize(self, client_config: Optional[McpConfig] = None) -> None:
        """Initialize MCP client based on configuration.

        Args:
            client_config: McpConfig
        """
        if self._initialized:
            logger.warning("MCP Manager already initialized")
            return

        logger.info("Initializing MCP Manager")

        self._client_config = client_config or McpConfig()

        try:
            await self._initialize_client(self._client_config)
        except Exception as e:
            logger.error(
                "Failed to initialize MCP client",
                error=str(e),
            )

        self._initialized = True
        logger.info("MCP Manager initialized successfully")

    async def _initialize_client(self, config: McpConfig) -> None:
        """Initialize a single MCP client."""
        if not config.enabled:
            logger.info("MCP client disabled")
            return

        client = McpClient(
            server_url=config.server_url,
            token=config.token,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

        # Initialize the client
        await client.initialize()

        # Store the client
        self._client = client

        logger.info("MCP client initialized")

    def get_client(self) -> Optional[McpClient]:
        """Get MCP client.

        Returns:
            MCP client instance or None if not found
        """
        if not self._initialized:
            logger.warning("MCP Manager not initialized")
            return None

        return self._clients.get()

    def is_client_available(self) -> bool:
        """Check if a client is available and initialized."""
        client = self._client
        return client is not None and client.is_initialized()

    async def health_check(self) -> bool:
        """Perform health check on MCP clients.

        Returns:
            Dict of client_name -> health_status
        """
        try:
            # Simple health check by listing tools
            await self._client.list_tools()
            result = True
            logger.debug("MCP client health check passed")
        except Exception as e:
            result = False
            logger.warning("MCP client health check failed", error=str(e))

        return result

    async def reconnect_client(self) -> bool:
        """Attempt to reconnect a failed MCP client.

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            # Close existing client if present
            if self._client:
                await self._client.close()
                del self._client

            # Reinitialize
            await self._initialize_client(self._client_configs)
            logger.info("MCP client reconnected successfully")
            return True

        except Exception as e:
            logger.error("Failed to reconnect MCP client", error=str(e))
            return False

    async def shutdown(self) -> None:
        """Gracefully shutdown MCP client."""
        if self._shutdown:
            return

        logger.info("Shutting down MCP Manager")
        self._shutdown = True

        self._client.close()

        logger.info("MCP Manager shutdown complete")

    @asynccontextmanager
    async def client_context(self):
        """Context manager for safe client access with automatic error handling.

        Yields:
            MCP client instance

        Example:
            async with mcp_manager.client_context() as client:
                tools = await client.list_tools()
        """
        client = self.get_client()

        if client is None:
            raise ValueError("MCP client not available")

        try:
            yield client
        except Exception as e:
            logger.warning("Error using MCP client", error=str(e))
            # Attempt reconnection on failure
            if not client.is_initialized():
                logger.info("Attempting to reconnect MCP client")
                await self.reconnect_client()
            raise

    def is_initialized(self) -> bool:
        """Check if MCP Manager is initialized."""
        return self._initialized

    def get_status(self) -> dict:
        """Get current status of MCP Manager."""
        return {
            "initialized": self._initialized,
            "shutdown": self._shutdown,
            "client": {
                "initialized": self._client.is_initialized(),
                "endpoint": self._client.server_url,
            },
        }


# Global MCP Manager instance
_mcp_manager = McpManager()


def get_mcp_manager() -> McpManager:
    """Get the global MCP Manager instance."""
    return _mcp_manager


async def initialize_mcp_manager(
    client_config: Optional[McpConfig] = None,
) -> None:
    """Initialize the global MCP Manager."""
    await _mcp_manager.initialize(client_config)


async def shutdown_mcp_manager() -> None:
    """Shutdown the global MCP Manager."""
    await _mcp_manager.shutdown()


def get_mcp_client() -> Optional[McpClient]:
    """Convenience function to get MCP client from global manager."""
    return _mcp_manager.get_client()
