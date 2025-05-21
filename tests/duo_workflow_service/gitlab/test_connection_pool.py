"""Tests for the connection pool manager."""

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
import pytest_asyncio

from duo_workflow_service.gitlab.connection_pool import (
    ConnectionPoolManager,
    connection_pool,
)


@pytest_asyncio.fixture
async def pool_manager():
    """Create a fresh connection pool manager for each test."""
    # Reset the singleton instance
    ConnectionPoolManager._instance = None
    ConnectionPoolManager._session = None

    # Create a new instance
    manager = ConnectionPoolManager()
    yield manager

    # Cleanup
    if manager._session:
        await manager._session.close()
        manager._session = None


@pytest.mark.asyncio
async def test_singleton_pattern():
    """Test that ConnectionPoolManager follows the singleton pattern."""
    manager1 = ConnectionPoolManager()
    manager2 = ConnectionPoolManager()
    assert manager1 is manager2


@pytest.mark.asyncio
async def test_session_not_initialized_error():
    """Test that accessing session before initialization raises an error."""
    manager = ConnectionPoolManager()
    with pytest.raises(
        RuntimeError, match="HTTP client connection pool is not initialized"
    ):
        _ = manager.session


@pytest.mark.asyncio
async def test_set_options():
    """Test setting pool options."""
    manager = ConnectionPoolManager()
    custom_timeout = aiohttp.ClientTimeout(total=60)
    manager.set_options(pool_size=200, timeout=custom_timeout)

    assert manager._pool_size == 200
    assert manager._session_kwargs["timeout"] == custom_timeout


@pytest.mark.asyncio
async def test_context_manager():
    """Test the async context manager functionality."""
    # Create a mock session with proper async close method
    mock_session = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.close.return_value = None  # Ensure close() returns None

    with patch("aiohttp.ClientSession", return_value=mock_session):
        connection_pool.set_options(
            pool_size=100, timeout=aiohttp.ClientTimeout(total=30)
        )
        async with connection_pool:
            # Check that session was created
            assert connection_pool._session is not None
            assert isinstance(connection_pool._session, AsyncMock)

        # Check that session was closed
        mock_session.close.assert_awaited_once()
        assert connection_pool._session is None


@pytest.mark.asyncio
async def test_multiple_context_entries():
    """Test that multiple context entries reuse the same session."""
    # Create a mock session with proper async close method
    mock_session = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.close.return_value = None  # Ensure close() returns None

    with patch(
        "aiohttp.ClientSession", return_value=mock_session
    ) as mock_session_class:
        connection_pool.set_options(
            pool_size=100, timeout=aiohttp.ClientTimeout(total=30)
        )
        async with connection_pool:
            session1 = connection_pool._session

            async with connection_pool:
                session2 = connection_pool._session

                # Should be the same session
                assert session1 is session2

                # Session creation should only happen once
                assert mock_session_class.call_count == 1

        # Session should be closed only once at the end
        mock_session.close.assert_awaited_once()
        assert connection_pool._session is None


@pytest.mark.asyncio
async def test_session_configuration():
    """Test that session is configured with the correct parameters."""
    pool_size = 150
    timeout = aiohttp.ClientTimeout(total=45)

    # Create a mock session with proper async close method
    mock_session = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.close.return_value = None  # Ensure close() returns None

    with patch(
        "aiohttp.ClientSession", return_value=mock_session
    ) as mock_session_class:
        connection_pool.set_options(pool_size=pool_size, timeout=timeout)

        async with connection_pool:
            # Verify that ClientSession was created with correct parameters
            mock_session_class.assert_called_once()
            _, kwargs = mock_session_class.call_args

            assert isinstance(kwargs["connector"], aiohttp.TCPConnector)
            assert kwargs["connector"].limit == pool_size
            assert kwargs["timeout"] == timeout
