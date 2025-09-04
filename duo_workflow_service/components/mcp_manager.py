"""MCP Manager for Server-wide MCP Client Management.

This module manages MCP client instances during server lifecycle, providing centralized access to MCP clients across the
application.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Dict, Optional, Set

import structlog

from duo_workflow_service.components.mcp_client import McpClient, McpClientFactory

logger = structlog.get_logger(__name__)


class McpManager:
    """Manages MCP client connections throughout server lifecycle.

    Provides:
    - Server startup MCP client initialization
    - Centralized client access and pooling
    - Graceful shutdown and cleanup
    - Health monitoring and reconnection
    """

    def __init__(self):
        self._clients: Dict[str, McpClient] = {}
        self._client_configs: Dict[str, dict] = {}
        self._initialized = False
        self._shutdown = False

    async def initialize(
        self, client_configs: Optional[Dict[str, dict]] = None
    ) -> None:
        """Initialize MCP clients based on configuration.

        Args:
            client_configs: Dict of client_name -> config mappings
                          If None, loads from environment variables
        """
        if self._initialized:
            logger.warning("MCP Manager already initialized")
            return

        logger.info("Initializing MCP Manager")

        if client_configs is None:
            client_configs = self._load_configs_from_env()

        self._client_configs = client_configs

        # Initialize each configured MCP client
        for client_name, config in client_configs.items():
            try:
                await self._initialize_client(client_name, config)
            except Exception as e:
                logger.error(
                    "Failed to initialize MCP client",
                    client_name=client_name,
                    error=str(e),
                )
                # Continue with other clients even if one fails

        self._initialized = True
        logger.info(
            "MCP Manager initialized successfully", client_count=len(self._clients)
        )

    def _load_configs_from_env(self) -> Dict[str, dict]:
        """Load MCP client configurations from environment variables."""
        configs = {}

        # Default GitLab MCP client
        gitlab_host = os.environ.get("GITLAB_HOST")
        gitlab_token = os.environ.get("GITLAB_TOKEN")

        if gitlab_host and gitlab_token:
            configs["gitlab"] = {
                "type": "gitlab",
                "gitlab_host": gitlab_host,
                "token": gitlab_token,
                "timeout": float(os.environ.get("MCP_TIMEOUT", 30.0)),
                "max_retries": int(os.environ.get("MCP_MAX_RETRIES", 3)),
                "enabled": os.environ.get("MCP_ENABLED", "true").lower() == "true",
            }

        # Support for multiple GitLab instances
        for i in range(1, 10):  # Support up to 10 instances
            host_key = f"GITLAB_HOST_{i}"
            token_key = f"GITLAB_TOKEN_{i}"

            host = os.environ.get(host_key)
            token = os.environ.get(token_key)

            if host and token:
                configs[f"gitlab_{i}"] = {
                    "type": "gitlab",
                    "gitlab_host": host,
                    "token": token,
                    "timeout": float(os.environ.get(f"MCP_TIMEOUT_{i}", 30.0)),
                    "max_retries": int(os.environ.get(f"MCP_MAX_RETRIES_{i}", 3)),
                    "enabled": os.environ.get(f"MCP_ENABLED_{i}", "true").lower()
                    == "true",
                }

        return configs

    async def _initialize_client(self, client_name: str, config: dict) -> None:
        """Initialize a single MCP client."""
        if not config.get("enabled", True):
            logger.info("MCP client disabled", client_name=client_name)
            return

        client_type = config.get("type", "gitlab")
        breakpoint()

        if client_type == "gitlab":
            client = McpClientFactory.create_gitlab_client(
                gitlab_host=config["gitlab_host"],
                token=config["token"],
                timeout=config.get("timeout", 30.0),
                max_retries=config.get("max_retries", 3),
            )
        else:
            raise ValueError(f"Unsupported MCP client type: {client_type}")

        # Initialize the client
        await client.initialize()

        # Store the client
        self._clients[client_name] = client

        logger.info("MCP client initialized", client_name=client_name, type=client_type)

    def get_client(self, client_name: str = "gitlab") -> Optional[McpClient]:
        """Get MCP client by name.

        Args:
            client_name: Name of the client to retrieve

        Returns:
            MCP client instance or None if not found
        """
        if not self._initialized:
            logger.warning("MCP Manager not initialized")
            return None

        return self._clients.get(client_name)

    def get_all_clients(self) -> Dict[str, McpClient]:
        """Get all initialized MCP clients."""
        return self._clients.copy()

    def get_client_names(self) -> Set[str]:
        """Get names of all available clients."""
        return set(self._clients.keys())

    def is_client_available(self, client_name: str = "gitlab") -> bool:
        """Check if a client is available and initialized."""
        client = self._clients.get(client_name)
        return client is not None and client.is_initialized()

    async def health_check(self, client_name: Optional[str] = None) -> Dict[str, bool]:
        """Perform health check on MCP clients.

        Args:
            client_name: Specific client to check, or None for all clients

        Returns:
            Dict of client_name -> health_status
        """
        results = {}

        clients_to_check = (
            {client_name: self._clients[client_name]}
            if client_name and client_name in self._clients
            else self._clients
        )

        for name, client in clients_to_check.items():
            try:
                # Simple health check by listing tools
                await client.list_tools()
                results[name] = True
                logger.debug("MCP client health check passed", client_name=name)
            except Exception as e:
                results[name] = False
                logger.warning(
                    "MCP client health check failed", client_name=name, error=str(e)
                )

        return results

    async def reconnect_client(self, client_name: str) -> bool:
        """Attempt to reconnect a failed MCP client.

        Args:
            client_name: Name of client to reconnect

        Returns:
            True if reconnection successful, False otherwise
        """
        if client_name not in self._client_configs:
            logger.error("No configuration found for client", client_name=client_name)
            return False

        try:
            # Close existing client if present
            if client_name in self._clients:
                await self._clients[client_name].close()
                del self._clients[client_name]

            # Reinitialize
            await self._initialize_client(
                client_name, self._client_configs[client_name]
            )
            logger.info("MCP client reconnected successfully", client_name=client_name)
            return True

        except Exception as e:
            logger.error(
                "Failed to reconnect MCP client", client_name=client_name, error=str(e)
            )
            return False

    async def shutdown(self) -> None:
        """Gracefully shutdown all MCP clients."""
        if self._shutdown:
            return

        logger.info("Shutting down MCP Manager")
        self._shutdown = True

        # Close all clients
        close_tasks = []
        for client_name, client in self._clients.items():
            logger.debug("Closing MCP client", client_name=client_name)
            close_tasks.append(client.close())

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self._clients.clear()
        logger.info("MCP Manager shutdown complete")

    @asynccontextmanager
    async def client_context(self, client_name: str = "gitlab"):
        """Context manager for safe client access with automatic error handling.

        Args:
            client_name: Name of client to use

        Yields:
            MCP client instance

        Example:
            async with mcp_manager.client_context("gitlab") as client:
                tools = await client.list_tools()
        """
        client = self.get_client(client_name)

        if client is None:
            raise ValueError(f"MCP client '{client_name}' not available")

        try:
            yield client
        except Exception as e:
            logger.warning(
                "Error using MCP client", client_name=client_name, error=str(e)
            )
            # Attempt reconnection on failure
            if not client.is_initialized():
                logger.info(
                    "Attempting to reconnect MCP client", client_name=client_name
                )
                await self.reconnect_client(client_name)
            raise

    def is_initialized(self) -> bool:
        """Check if MCP Manager is initialized."""
        return self._initialized

    def get_status(self) -> dict:
        """Get current status of MCP Manager."""
        return {
            "initialized": self._initialized,
            "shutdown": self._shutdown,
            "client_count": len(self._clients),
            "clients": {
                name: {
                    "initialized": client.is_initialized(),
                    "endpoint": client.mcp_endpoint,
                }
                for name, client in self._clients.items()
            },
        }


# Global MCP Manager instance
_mcp_manager = McpManager()


def get_mcp_manager() -> McpManager:
    """Get the global MCP Manager instance."""
    return _mcp_manager


async def initialize_mcp_manager(
    client_configs: Optional[Dict[str, dict]] = None,
) -> None:
    """Initialize the global MCP Manager."""
    await _mcp_manager.initialize(client_configs)


async def shutdown_mcp_manager() -> None:
    """Shutdown the global MCP Manager."""
    await _mcp_manager.shutdown()


def get_mcp_client(client_name: str = "gitlab") -> Optional[McpClient]:
    """Convenience function to get MCP client from global manager."""
    return _mcp_manager.get_client(client_name)
