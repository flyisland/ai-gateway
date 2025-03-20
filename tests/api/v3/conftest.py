from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware import Middleware
from starlette_context.middleware import RawContextMiddleware

from ai_gateway.api.middleware import AccessLogMiddleware, MiddlewareAuthentication
from ai_gateway.api.v3 import api_router
from ai_gateway.config import Config
from ai_gateway.container import ContainerApplication


@pytest.fixture(scope="module")
def stub_auth_provider():
    class StubKeyAuthProvider:
        def authenticate(self, token):
            return None

    return StubKeyAuthProvider()


@pytest.fixture(scope="module")
def fast_api_router():
    return api_router


@pytest.fixture(scope="module")
def test_client(fast_api_router, stub_auth_provider, request):
    middlewares = [
        Middleware(RawContextMiddleware),
        Middleware(AccessLogMiddleware, skip_endpoints=[]),
        MiddlewareAuthentication(stub_auth_provider, False, None),
    ]
    app = FastAPI(middleware=middlewares)
    app.include_router(fast_api_router)
    client = TestClient(app)

    return client


@pytest.fixture(scope="module")
def mock_track_internal_event():
    with patch("ai_gateway.internal_events.InternalEventsClient.track_event") as mock:
        yield mock


@pytest.fixture(scope="module")
def mock_detect_abuse():
    with patch("ai_gateway.abuse_detection.AbuseDetector.detect") as mock:
        yield mock


@pytest.fixture(scope="module")
def mock_config(config_values):
    yield Config(_env_file=None, _env_prefix="AIGW_TEST", **config_values)


@pytest.fixture(scope="module")
def mock_container(mock_config: Config):
    container_application = ContainerApplication()
    container_application.config.from_dict(mock_config.model_dump())

    yield container_application


@pytest.fixture(scope="class")
def mock_client(test_client, stub_auth_provider, auth_user, mock_container):
    """Setup all the needed mocks to perform requests in the test environment"""
    with patch.object(stub_auth_provider, "authenticate", return_value=auth_user):
        yield test_client
