from typing import Any, Callable, ClassVar, Dict, Optional, Union

import aiohttp

from duo_workflow_service.gitlab.http_client import GitlabHttpClient


class DirectGitLabHttpClient(GitlabHttpClient):
    """GitLab HTTP client implementation that directly calls the GitLab API with connection pooling."""

    # Class-level shared connection pool
    _session: ClassVar[Optional[aiohttp.ClientSession]] = None

    base_url: str
    gitlab_token: str

    @classmethod
    async def initialize_pool(cls, pool_size: int = 100, **session_kwargs) -> None:
        """Initialize the shared connection pool.

        Args:
            pool_size: Maximum number of connections in the pool
            **session_kwargs: Additional arguments to pass to aiohttp.ClientSession
        """
        if cls._session is None:
            connector = aiohttp.TCPConnector(limit=pool_size)
            cls._session = aiohttp.ClientSession(connector=connector, **session_kwargs)

    @classmethod
    async def close_pool(cls) -> None:
        """Close the shared connection pool."""
        if cls._session is not None:
            await cls._session.close()
            cls._session = None

    def __init__(self, base_url: str, gitlab_token: str):
        self.base_url = base_url
        self.gitlab_token = gitlab_token

    async def _call(
        self,
        path: str,
        method: str,
        parse_json: bool = True,
        data: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        object_hook: Union[Callable, None] = None,
    ) -> Any:
        """Execute a request to the GitLab API.

        Args:
            path: The API endpoint path
            method: HTTP method (GET, POST, etc.)
            parse_json: Whether to parse the response as JSON
            data: Request body data
            params: Query parameters
            object_hook: Optional JSON decoder hook

        Returns:
            The API response, parsed as JSON if parse_json=True
        """

        url = f"{self.base_url}/{path}"

        # Handle request arguments
        kwargs = {}
        if params:
            kwargs["params"] = params
        if data:
            # Pass data directly as a string parameter, not as a dict
            kwargs["data"] = data  # type: ignore

        headers = {
            "Authorization": f"Bearer {self.gitlab_token}",
            "Content-Type": "application/json",
        }

        if self._session is None:
            raise RuntimeError("HTTP client connection pool is not initialized")

        async with self._session.request(
            method, url, headers=headers, **kwargs
        ) as response:
            raw_response = await response.text()
            return self._parse_response(raw_response, parse_json, object_hook)
