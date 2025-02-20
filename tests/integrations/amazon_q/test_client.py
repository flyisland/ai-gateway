"""
This module contains unit tests for the Amazon Q Client and its factory.
It tests the functionality of creating clients, handling authentication,
and managing OAuth applications. The tests cover success scenarios as well
as various error conditions using mock objects to simulate AWS services.


"""

from typing import Dict
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import HTTPException

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.auth.glgo import GlgoAuthority
from ai_gateway.integrations.amazon_q.client import AmazonQClient, AmazonQClientFactory
from ai_gateway.integrations.amazon_q.errors import AWSException


# Fixtures
@pytest.fixture
def mock_glgo_authority() -> Mock:
    """
    Creates a mock GlgoAuthority with a mocked token method.

    Returns:
        Mock: Mocked GlgoAuthority instance
    """
    return Mock(spec=GlgoAuthority)


@pytest.fixture
def mock_current_user() -> Mock:
    """
    Creates a mock user with test credentials and claims.

    Returns:
        Mock: Mocked StarletteUser instance
    """
    user = Mock(spec=StarletteUser)
    user.global_user_id = "test_user_id"
    user.cloud_connector_token = "test_token"
    user.claims = Mock()
    user.claims.subject = "test_subject"
    return user


@pytest.fixture
def mock_credentials() -> Dict[str, str]:
    """
    Provides mock AWS credentials.

    Returns:
        Dict[str, str]: Dictionary containing mock AWS credentials
    """
    return {
        "AccessKeyId": "test_access_key",
        "SecretAccessKey": "test_secret_key",
        "SessionToken": "test_session_token",
    }


@pytest.fixture
def client_factory(mock_glgo_authority: Mock) -> AmazonQClientFactory:
    """
    Creates an AmazonQClientFactory instance with mocked dependencies.

    Args:
        mock_glgo_authority: Mocked GlgoAuthority instance

    Returns:
        AmazonQClientFactory: Configured client factory for testing
    """
    with patch("boto3.client") as mock_boto3_client:
        mock_boto3_client.return_value = Mock()
        factory = AmazonQClientFactory(
            glgo_authority=mock_glgo_authority,
            endpoint_url="https://test-endpoint",
            region="us-west-2",
        )
        factory.sts_client = mock_boto3_client.return_value
        return factory


@pytest.fixture
def amazon_q_client(mock_credentials: Dict[str, str]) -> AmazonQClient:
    """
    Creates an AmazonQClient instance with mocked credentials.

    Args:
        mock_credentials: Dictionary of mock AWS credentials

    Returns:
        AmazonQClient: Configured client for testing
    """
    with patch("q_developer_boto3.boto3.client") as mock_q_boto3_client:
        client = AmazonQClient(
            url="https://test-endpoint",
            region="us-west-2",
            credentials=mock_credentials,
        )
        client.client = mock_q_boto3_client.return_value
        return client


class TestAmazonQClientFactory:
    """Test suite for AmazonQClientFactory class."""

    def test_get_client_success(
        self,
        client_factory: AmazonQClientFactory,
        mock_current_user: Mock,
        mock_credentials: Dict[str, str],
    ) -> None:
        """Tests successful client creation with valid credentials."""
        # Mock the token method at the authority level
        client_factory.glgo_authority = Mock(spec=GlgoAuthority)
        client_factory.glgo_authority.token.return_value = "test_token"

        client_factory.sts_client.assume_role_with_web_identity.return_value = {
            "Credentials": mock_credentials
        }

        client = client_factory.get_client(mock_current_user, "test_role_arn")

        assert isinstance(client, AmazonQClient)
        client_factory.glgo_authority.token.assert_called_once_with(
            user_id="test_user_id",
            cloud_connector_token="test_token",
        )
        client_factory.sts_client.assume_role_with_web_identity.assert_called_once_with(
            RoleArn="test_role_arn",
            RoleSessionName="test_subject",
            WebIdentityToken="test_token",
            DurationSeconds=43200,
        )

    def test_get_client_missing_user_id(
        self, client_factory: AmazonQClientFactory
    ) -> None:
        """Tests error handling when user ID is missing."""
        mock_user = Mock(spec=StarletteUser)
        mock_user.global_user_id = None

        with pytest.raises(HTTPException) as exc_info:
            client_factory.get_client(mock_user, "test_role_arn")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "User Id is missing"

    def test_get_glgo_token_failure(
        self, client_factory: AmazonQClientFactory, mock_current_user: Mock
    ) -> None:
        """Tests error handling when GLGO token retrieval fails."""
        # Mock the authority at the instance level
        client_factory.glgo_authority = Mock(spec=GlgoAuthority)
        client_factory.glgo_authority.token.side_effect = Exception("Token error")

        with pytest.raises(HTTPException) as exc_info:
            client_factory._get_glgo_token(mock_current_user)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Cannot obtain OIDC token"


class TestAmazonQClient:
    """Test suite for AmazonQClient class."""

    def test_send_event_success(self, amazon_q_client: AmazonQClient) -> None:
        """Tests successful event sending."""
        mock_request = Mock()
        mock_request.payload.model_dump_json.return_value = '{"test": "data"}'
        mock_request.code = "test_code"

        # Configure mock to return successfully
        amazon_q_client.client.send_event.return_value = {"Success": True}

        # Should not raise any exception
        amazon_q_client.send_event(mock_request)

        amazon_q_client.client.send_event.assert_called_once_with(
            providerId="GITLAB",
            eventId="Quick Action",
            eventVersion="1.0",
            event='{"test": "data"}',
        )

    def test_send_event_access_denied(self, amazon_q_client: AmazonQClient) -> None:
        """Tests failure handling when sending events with access denied."""
        mock_request = Mock()
        mock_request.payload.model_dump_json.return_value = '{"test": "data"}'
        mock_request.code = "test_code"

        # Configure mock to raise ClientError with AccessDeniedException
        error_response = {
            "Error": {"Code": "AccessDeniedException", "Message": "Access denied"}
        }
        amazon_q_client.client.send_event.side_effect = ClientError(
            error_response, "SendEvent"
        )

        # Should raise AWSException
        with pytest.raises(AWSException) as exc_info:
            amazon_q_client.send_event(mock_request)

        assert "AccessDeniedException" in str(exc_info.value)
        assert "Access denied" in str(exc_info.value)

    def test_create_or_update_auth_application_success(
        self, amazon_q_client: AmazonQClient
    ) -> None:
        """Tests successful creation of OAuth application."""
        mock_request = Mock()
        mock_request.client_id = "test_client_id"
        mock_request.client_secret = "test_secret"
        mock_request.instance_url = "test_url"
        mock_request.redirect_url = "test_redirect"

        amazon_q_client.create_or_update_auth_application(mock_request)

        amazon_q_client.client.create_o_auth_app_connection.assert_called_once_with(
            clientId="test_client_id",
            clientSecret="test_secret",
            instanceUrl="test_url",
            redirectUrl="test_redirect",
        )

    def test_create_or_update_auth_application_conflict(
        self, amazon_q_client: AmazonQClient
    ) -> None:
        """Tests handling of conflict when creating OAuth application."""
        mock_request = Mock()
        mock_request.client_id = "test_client_id"
        mock_request.client_secret = "test_secret"
        mock_request.instance_url = "test_url"
        mock_request.redirect_url = "test_redirect"

        # First call raises conflict, second call (update) succeeds
        error_response = {
            "Error": {"Code": "ConflictException", "Message": "Resource already exists"}
        }
        amazon_q_client.client.create_o_auth_app_connection.side_effect = ClientError(
            error_response, "CreateOAuthAppConnection"
        )

        amazon_q_client.create_or_update_auth_application(mock_request)

        amazon_q_client.client.update_o_auth_app_connection.assert_called_once_with(
            clientId="test_client_id",
            clientSecret="test_secret",
            instanceUrl="test_url",
            redirectUrl="test_redirect",
        )

    def test_create_or_update_auth_application_access_denied(
        self, amazon_q_client: AmazonQClient
    ) -> None:
        """Tests access denied error handling for OAuth application creation."""
        mock_request = Mock()
        mock_request.client_id = "test_client_id"
        mock_request.client_secret = "test_secret"
        mock_request.instance_url = "test_url"
        mock_request.redirect_url = "test_redirect"

        error_response = {
            "Error": {"Code": "AccessDeniedException", "Message": "Access denied"}
        }
        amazon_q_client.client.create_o_auth_app_connection.side_effect = ClientError(
            error_response, "CreateOAuthAppConnection"
        )

        with pytest.raises(AWSException) as exc_info:
            amazon_q_client.create_or_update_auth_application(mock_request)

        assert "AccessDeniedException" in str(exc_info.value)
        assert "Access denied" in str(exc_info.value)

    def test_send_event_validation_error(self, amazon_q_client: AmazonQClient) -> None:
        """Tests parameter validation error handling."""
        mock_request = Mock()
        mock_request.payload.model_dump_json.return_value = '{"test": "data"}'
        mock_request.code = "test_code"

        # Configure mock to raise ParamValidationError
        amazon_q_client.client.send_event.side_effect = ParamValidationError(
            report="Invalid parameters"
        )

        with pytest.raises(HTTPException) as exc_info:
            amazon_q_client.send_event(mock_request)

        assert exc_info.value.status_code == 400
        assert "Invalid parameters" in str(exc_info.value.detail)

    @pytest.fixture
    def mock_aws_credentials(self):
        """Fixture for mock AWS credentials."""
        return {
            "AccessKeyId": "test_access_key",
            "SecretAccessKey": "test_secret_key",
            "SessionToken": "test_session_token",
        }

    def test_client_initialization(self, mock_aws_credentials):
        """Tests client initialization with credentials."""
        with patch("boto3.client") as mock_boto3_client:
            client = AmazonQClient(
                url="https://test-endpoint",
                region="us-west-2",
                credentials=mock_aws_credentials,
            )

            mock_boto3_client.assert_called_once_with(
                "q",
                region_name="us-west-2",
                endpoint_url="https://test-endpoint",
                aws_access_key_id="test_access_key",
                aws_secret_access_key="test_secret_key",
                aws_session_token="test_session_token",
            )

    def test_send_message_success(self, amazon_q_client: AmazonQClient) -> None:
        """Tests successful message sending."""
        payload = {
            "message": "Hello, this is a test message",
            "conversation_id": "conv-123",
        }

        expected_response = {"messageId": "msg-123", "status": "success"}

        amazon_q_client.client.send_message.return_value = expected_response

        response = amazon_q_client.send_chat_message(payload)

        amazon_q_client.client.send_message.assert_called_once_with(
            message="Hello, this is a test message", conversationId="conv-123"
        )
        assert response == expected_response

    def test_send_message_empty_message(self, amazon_q_client: AmazonQClient) -> None:
        """Tests sending empty message."""
        payload = {"message": "", "conversation_id": "conv-123"}

        amazon_q_client.client.send_message.return_value = {"messageId": "msg-123"}

        response = amazon_q_client.send_chat_message(payload)

        amazon_q_client.client.send_message.assert_called_once_with(
            message="", conversationId="conv-123"
        )
        assert response["messageId"] == "msg-123"

    def test_send_message_long_message(self, amazon_q_client: AmazonQClient) -> None:
        """Tests sending a long message."""
        long_message = "x" * 1000  # 1000 character message
        payload = {"message": long_message, "conversation_id": "conv-123"}

        amazon_q_client.client.send_message.return_value = {"messageId": "msg-123"}

        response = amazon_q_client.send_chat_message(payload)

        amazon_q_client.client.send_message.assert_called_once_with(
            message=long_message, conversationId="conv-123"
        )
        assert response["messageId"] == "msg-123"

    def test_send_message_special_characters(
        self, amazon_q_client: AmazonQClient
    ) -> None:
        """Tests sending message with special characters."""
        payload = {
            "message": "Special chars: !@#$%^&*()\n\t",
            "conversation_id": "conv-123",
        }

        amazon_q_client.client.send_message.return_value = {"messageId": "msg-123"}

        response = amazon_q_client.send_chat_message(payload)

        amazon_q_client.client.send_message.assert_called_once_with(
            message="Special chars: !@#$%^&*()\n\t", conversationId="conv-123"
        )
        assert response["messageId"] == "msg-123"

    def test_send_message_unicode_characters(
        self, amazon_q_client: AmazonQClient
    ) -> None:
        """Tests sending message with unicode characters."""
        payload = {
            "message": "Unicode test: 你好 안녕하세요 👋 🌟",
            "conversation_id": "conv-123",
        }

        amazon_q_client.client.send_message.return_value = {"messageId": "msg-123"}

        response = amazon_q_client.send_chat_message(payload)

        amazon_q_client.client.send_message.assert_called_once_with(
            message="Unicode test: 你好 안녕하세요 👋 🌟", conversationId="conv-123"
        )
        assert response["messageId"] == "msg-123"
