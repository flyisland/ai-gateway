import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gitlab_cloud_connector import (
    CloudConnectorAuthError,
    CloudConnectorUser,
    UserClaims,
)

from duo_workflow_service.interceptors.authentication_interceptor import (
    AuthenticationInterceptor,
    AuthenticationMiddleware,
    current_user,
)


@pytest.fixture
def mock_continuation():
    return AsyncMock()


@pytest.fixture
def handler_call_details():
    mock_details = MagicMock()
    mock_details.invocation_metadata = (
        ("authorization", "bearer test-token"),
        ("x-gitlab-authentication-type", "oidc"),
        ("x-gitlab-realm", "test-realm"),
        ("x-gitlab-instance-id", "test-instance-id"),
        ("x-gitlab-global-user-id", "test-global-user-id"),
    )
    return mock_details


@pytest.fixture
def interceptor():
    return AuthenticationInterceptor()


@patch.dict(os.environ, {"DUO_WORKFLOW_AUTH__ENABLED": "false"})
@pytest.mark.asyncio
async def test_intercept_service_auth_disabled(
    interceptor, mock_continuation, handler_call_details
):
    await interceptor.intercept_service(mock_continuation, handler_call_details)
    user = current_user.get()
    assert user.is_authenticated
    assert user.is_debug


@patch.dict(
    os.environ,
    {
        "DUO_WORKFLOW_AUTH__ENABLED": "true",
        "CLOUD_CONNECTOR_SERVICE_NAME": "gitlab-duo-workflow-service",
    },
)
@patch(
    "duo_workflow_service.interceptors.authentication_interceptor.authenticate",
    return_value=(
        CloudConnectorUser(True, claims=UserClaims(gitlab_realm="test-realm")),
        None,
    ),
)
@pytest.mark.asyncio
async def test_intercept_service_auth_enabled(
    mock_authenticate, interceptor, mock_continuation, handler_call_details
):
    await interceptor.intercept_service(mock_continuation, handler_call_details)
    user = current_user.get()
    assert user.is_authenticated


@pytest.fixture
def mock_websocket():
    mock_ws = AsyncMock()
    mock_ws.headers = {
        "authorization": "bearer test-token",
        "x-gitlab-authentication-type": "oidc",
        "x-gitlab-realm": "test-realm",
        "x-gitlab-instance-id": "test-instance-id",
        "x-gitlab-global-user-id": "test-global-user-id",
    }
    mock_ws.close = AsyncMock()
    return mock_ws


@pytest.fixture
def websocket_middleware():
    return AuthenticationMiddleware()


@patch.dict(os.environ, {"DUO_WORKFLOW_AUTH__ENABLED": "false"})
@pytest.mark.asyncio
async def test_websocket_middleware_auth_disabled(websocket_middleware, mock_websocket):
    # Call the middleware
    await websocket_middleware(mock_websocket)

    # Check that the user is set correctly
    user = current_user.get()
    assert user.is_authenticated
    assert user.is_debug

    # Ensure websocket.close() was not called
    mock_websocket.close.assert_not_called()


@patch.dict(
    os.environ,
    {
        "DUO_WORKFLOW_AUTH__ENABLED": "true",
        "CLOUD_CONNECTOR_SERVICE_NAME": "gitlab-duo-workflow-service",
    },
)
@patch(
    "duo_workflow_service.interceptors.authentication_interceptor.authenticate",
    return_value=(
        CloudConnectorUser(True, claims=UserClaims(gitlab_realm="test-realm")),
        None,
    ),
)
@pytest.mark.asyncio
async def test_websocket_middleware_auth_enabled(
    mock_authenticate, websocket_middleware, mock_websocket
):
    # Call the middleware
    await websocket_middleware(mock_websocket)

    # Check that the user is set correctly
    user = current_user.get()
    assert user.is_authenticated

    # Ensure websocket.close() was not called
    mock_websocket.close.assert_not_called()


@patch.dict(
    os.environ,
    {
        "DUO_WORKFLOW_AUTH__ENABLED": "true",
        "CLOUD_CONNECTOR_SERVICE_NAME": "gitlab-duo-workflow-service",
    },
)
@patch(
    "duo_workflow_service.interceptors.authentication_interceptor.authenticate",
    return_value=(
        None,
        CloudConnectorAuthError("Invalid token"),
    ),
)
@pytest.mark.asyncio
async def test_websocket_middleware_auth_failure(
    mock_authenticate, websocket_middleware, mock_websocket
):
    # Call the middleware
    await websocket_middleware(mock_websocket)

    # Check that websocket.close() was called with the correct parameters
    mock_websocket.close.assert_called_once_with(code=1008, reason="Invalid token")
