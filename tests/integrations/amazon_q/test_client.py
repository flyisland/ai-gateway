import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from pydantic import BaseModel

from ai_gateway.api.auth_utils import StarletteUser
from ai_gateway.api.v1.amazon_q.typing import (
    EventHookPayload,
    EventIssuePayload,
    EventMergeRequestPayload,
    EventRequest,
)
from ai_gateway.auth.glgo import GlgoAuthority
from ai_gateway.integrations.amazon_q.client import (
    QUICK_ACTION_EVENT_ID,
    SYSTEM_HOOK_EVENT_MAP,
    AmazonQClient,
    AmazonQClientFactory,
)
from ai_gateway.integrations.amazon_q.errors import AWSException


# Create a custom ClientError subclass with the name "AccessDeniedException"
class AccessDeniedException(ClientError):
    def __init__(self):
        super().__init__(
            error_response={
                "Error": {"Code": "AccessDeniedException", "Message": "Access denied"}
            },
            operation_name="SendEvent",
        )


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


@pytest.fixture
def event_merge_request_payload():
    """Fixture for EventMergeRequestPayload"""
    return EventMergeRequestPayload(
        source="merge_request",
        merge_request_id="1",
        merge_request_iid="1",
        command="dev",
        role_arn="arn:aws:iam::123456789012:role/test-role",
        project_path="a/b/c",
        project_id="123",
        note_id="1",
        discussion_id="1",
        source_branch="dev",
        target_branch="main",
        last_commit_id="123",
    )


@pytest.fixture
def event_issue_payload():
    """Fixture for EventIssuePayload"""
    return EventIssuePayload(
        source="issue",
        issue_id="1",
        issue_iid="1",
        command="dev",
        role_arn="arn:aws:iam::123456789012:role/test-role",
        project_path="a/b/c",
        project_id="123",
        note_id="1",
        discussion_id="1",
    )


@pytest.fixture
def event_hook_payload():
    """Fixture for EventHookPayload"""
    return EventHookPayload(
        source="system_hook",
        data={
            "object_kind": "merge_request",
            "project_id": 1,
            "ref": "refs/heads/main",
            "checkout_sha": "abc123",
            "user_id": 1,
            "user_name": "Test User",
            "repository": {
                "name": "test-repo",
                "url": "git@gitlab.com:group/project.git",
                "description": "test repository",
                "homepage": "https://gitlab.com/group/project",
            },
            "project": {
                "id": 20,
                "name": "Project1",
                "description": None,
            },
        },
    )


@pytest.fixture
def event_request_merge(event_merge_request_payload):
    """Fixture for EventRequest with merge request payload"""
    return EventRequest(
        role_arn="arn:aws:iam::123456789012:role/test-role",
        code="test-code",
        payload=event_merge_request_payload,
    )


@pytest.fixture
def event_request_issue(event_issue_payload):
    """Fixture for EventRequest with issue payload"""
    return EventRequest(
        role_arn="arn:aws:iam::123456789012:role/test-role",
        code="test-code",
        payload=event_issue_payload,
    )


@pytest.fixture
def event_request_hook(event_hook_payload):
    """Fixture for EventRequest with system hook payload"""
    return EventRequest(
        role_arn="arn:aws:iam::123456789012:role/test-role",
        code="test-code",
        payload=event_hook_payload,
    )


class TestAmazonQClientFactory:
    @pytest.fixture
    def mock_glgo_authority(self):
        return MagicMock(spec=GlgoAuthority)

    @pytest.fixture
    def mock_sts_client(self):
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def mock_boto3(self, mock_sts_client):
        with patch("ai_gateway.integrations.amazon_q.client.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_sts_client
            yield mock_boto3

    @pytest.fixture
    def amazon_q_client_factory(self, mock_glgo_authority, mock_boto3):
        return AmazonQClientFactory(
            glgo_authority=mock_glgo_authority,
            endpoint_url="https://mock.endpoint",
            region="us-east-1",
        )

    @pytest.fixture
    def mock_user(self):
        user = MagicMock(spec=StarletteUser)
        user.global_user_id = "test-user-id"
        user.cloud_connector_token = "mock-cloud-connector-token"
        user.claims = MagicMock(subject="test-session")
        return user

    def test_get_glgo_token(
        self, amazon_q_client_factory, mock_user, mock_glgo_authority
    ):
        mock_glgo_authority.token.return_value = "mock-token"
        token = amazon_q_client_factory._get_glgo_token(mock_user)

        mock_glgo_authority.token.assert_called_once_with(
            user_id="test-user-id", cloud_connector_token="mock-cloud-connector-token"
        )
        assert token == "mock-token"

    def test_missing_user_id_for_glgo_token(
        self, amazon_q_client_factory, mock_user, mock_glgo_authority
    ):
        mock_user.global_user_id = None

        with pytest.raises(HTTPException) as exc:
            amazon_q_client_factory._get_glgo_token(mock_user)
        assert exc.value.status_code == 400
        assert exc.value.detail == "User Id is missing"

    def test_glgo_token_raises_error(
        self, amazon_q_client_factory, mock_user, mock_glgo_authority
    ):
        mock_glgo_authority.token.side_effect = KeyError()

        with pytest.raises(HTTPException) as exc:
            amazon_q_client_factory._get_glgo_token(mock_user)
        assert exc.value.status_code == 500
        assert exc.value.detail == "Cannot obtain OIDC token"

    def test_get_aws_credentials(
        self, amazon_q_client_factory, mock_user, mock_sts_client
    ):
        mock_sts_client.assume_role_with_web_identity.return_value = {
            "Credentials": {
                "AccessKeyId": "mock-key",
                "SecretAccessKey": "mock-secret",
                "SessionToken": "mock-token",
            }
        }

        credentials = amazon_q_client_factory._get_aws_credentials(
            mock_user, token="mock-web-identity-token", role_arn="mock-role-arn"
        )

        mock_sts_client.assume_role_with_web_identity.assert_called_once_with(
            RoleArn="mock-role-arn",
            RoleSessionName="test-session",
            WebIdentityToken="mock-web-identity-token",
            DurationSeconds=43200,
        )
        assert credentials == {
            "AccessKeyId": "mock-key",
            "SecretAccessKey": "mock-secret",
            "SessionToken": "mock-token",
        }

    def test_get_aws_credentials_no_claims(
        self, amazon_q_client_factory, mock_user, mock_sts_client
    ):
        mock_user.claims = None
        mock_sts_client.assume_role_with_web_identity.return_value = {
            "Credentials": {
                "AccessKeyId": "mock-key",
                "SecretAccessKey": "mock-secret",
                "SessionToken": "mock-token",
            }
        }

        credentials = amazon_q_client_factory._get_aws_credentials(
            mock_user, token="mock-web-identity-token", role_arn="mock-role-arn"
        )

        mock_sts_client.assume_role_with_web_identity.assert_called_once_with(
            RoleArn="mock-role-arn",
            RoleSessionName="placeholder",
            WebIdentityToken="mock-web-identity-token",
            DurationSeconds=43200,
        )

        assert credentials == {
            "AccessKeyId": "mock-key",
            "SecretAccessKey": "mock-secret",
            "SessionToken": "mock-token",
        }

    def test_get_client(
        self, amazon_q_client_factory, mock_user, mock_glgo_authority, mock_sts_client
    ):
        with patch(
            "ai_gateway.integrations.amazon_q.client.AmazonQClient"
        ) as mock_q_client_class:
            mock_q_client_instance = MagicMock()
            mock_q_client_class.return_value = mock_q_client_instance

            credentials = {
                "AccessKeyId": "mock-key",
                "SecretAccessKey": "mock-secret",
                "SessionToken": "mock-token",
            }

            mock_glgo_authority.token.return_value = "mock-token"
            mock_sts_client.assume_role_with_web_identity.return_value = {
                "Credentials": credentials
            }

            client = amazon_q_client_factory.get_client(
                current_user=mock_user,
                role_arn="mock-role-arn",
            )

            mock_glgo_authority.token.assert_called_once_with(
                user_id="test-user-id",
                cloud_connector_token="mock-cloud-connector-token",
            )

            mock_sts_client.assume_role_with_web_identity.assert_called_once_with(
                RoleArn="mock-role-arn",
                RoleSessionName="test-session",
                WebIdentityToken="mock-token",
                DurationSeconds=43200,
            )

            mock_q_client_class.assert_called_once_with(
                url="https://mock.endpoint", region="us-east-1", credentials=credentials
            )

            assert client == mock_q_client_instance


class TestAmazonQClient:
    @pytest.fixture
    def mock_credentials(self):
        return {
            "AccessKeyId": "test-access-key",
            "SecretAccessKey": "test-secret-key",
            "SessionToken": "test-session-token",
        }

    @pytest.fixture
    def mock_application_request(self):
        class ApplicationRequest:
            client_id = "test-client-id"
            client_secret = "test-secret"
            instance_url = "https://test.example.com"
            redirect_url = "https://test.example.com/callback"

        return ApplicationRequest()

    @pytest.fixture
    def mock_event_request(self) -> Any:
        class Payload(BaseModel):
            first_field: str = "test field"
            second_field: int = 1
            third_field: Optional[str] = None

        class EventRequest:
            payload = Payload()

        return EventRequest()

    @pytest.fixture
    def mock_q_client(self):
        with patch(
            "ai_gateway.integrations.amazon_q.client.q_boto3.client"
        ) as mock_client:
            yield mock_client.return_value

    @pytest.fixture
    def q_client(self, mock_credentials, mock_q_client):
        return AmazonQClient(
            url="https://q-api.example.com",
            region="us-west-2",
            credentials=mock_credentials,
        )

    @pytest.fixture
    def params(self):
        return dict(
            clientId="test-client-id",
            clientSecret="test-secret",
            instanceUrl="https://test.example.com",
            redirectUrl="https://test.example.com/callback",
        )

    def test_init_creates_client_with_correct_params(self, mock_credentials):
        with patch(
            "ai_gateway.integrations.amazon_q.client.q_boto3.client"
        ) as mock_client:
            AmazonQClient(
                url="https://q-api.example.com",
                region="us-west-2",
                credentials=mock_credentials,
            )

            mock_client.assert_called_once_with(
                "q",
                region_name="us-west-2",
                endpoint_url="https://q-api.example.com",
                aws_access_key_id="test-access-key",
                aws_secret_access_key="test-secret-key",
                aws_session_token="test-session-token",
            )

    def test_create_auth_application_success(
        self, q_client, mock_q_client, mock_application_request, params
    ):
        q_client.create_or_update_auth_application(mock_application_request)
        mock_q_client.create_o_auth_app_connection.assert_called_once_with(**params)

        assert not mock_q_client.update_o_auth_app_connection.called

    def test_update_auth_application_on_conflict(
        self, q_client, mock_q_client, mock_application_request, params
    ):
        error_response = {
            "Error": {"Code": "ConflictException", "Message": "A conflict occurred"}
        }
        mock_q_client.create_o_auth_app_connection.side_effect = ClientError(
            error_response, "create_o_auth_app_connection"
        )

        q_client.create_or_update_auth_application(mock_application_request)

        mock_q_client.create_o_auth_app_connection.assert_called_once_with(**params)
        mock_q_client.update_o_auth_app_connection.assert_called_once_with(**params)

    def test_raises_non_conflict_aws_errors(
        self, q_client, mock_q_client, mock_application_request
    ):
        error_response = {
            "Error": {"Code": "ValidationException", "Message": "invalid message"}
        }
        mock_q_client.create_o_auth_app_connection.side_effect = ClientError(
            error_response, "create_o_auth_app_connection"
        )

        with pytest.raises(AWSException):
            q_client.create_or_update_auth_application(mock_application_request)

        mock_q_client.create_o_auth_app_connection.assert_called_once()
        assert not mock_q_client.update_o_auth_app_connection.called

    @pytest.mark.parametrize(
        "event_id,payload,client_error,expected_exception",
        [
            # Happy path - successful event sending
            ("Quick Action", '{"test": "data"}', None, None),
            # Test missing event ID
            (None, '{"test": "data"}', None, HTTPException),
            # Test missing payload
            ("Quick Action", None, None, HTTPException),
            # Test AccessDeniedException with retry
            (
                "Quick Action",
                '{"test": "data"}',
                AccessDeniedException(),
                None,
            ),
            # Test other ClientError
            (
                "Quick Action",
                '{"test": "data"}',
                ClientError(
                    error_response={
                        "Error": {"Code": "OtherError", "Message": "Error"}
                    },
                    operation_name="SendEvent",
                ),
                AWSException,
            ),
        ],
    )
    def test_send_event(
        self, amazon_q_client, event_id, payload, client_error, expected_exception
    ):
        """Tests event sending with various scenarios."""
        # Setup mock request
        mock_request = Mock()
        mock_request.payload.model_dump_json.return_value = payload
        mock_request.event_id = event_id
        mock_request.code = "test_code"

        amazon_q_client._retry_send_event = Mock(return_value={"Success": True})

        if client_error:
            # Configure mock to raise exception on first call
            amazon_q_client._send_event = Mock(
                side_effect=[client_error, {"Success": True}]
            )
        else:
            # Configure mock to return successfully
            amazon_q_client._send_event = Mock(return_value={"Success": True})

        if expected_exception:
            with pytest.raises(expected_exception):
                amazon_q_client.send_event(mock_request)
        else:
            # Should not raise any exception
            amazon_q_client.send_event(mock_request)

            if (
                client_error
                and isinstance(client_error, ClientError)
                and client_error.response["Error"]["Code"] == "AccessDeniedException"
            ):
                # Verify _send_event was called first and raised the exception
                amazon_q_client._send_event.assert_called_with(event_id, payload)
                # Verify retry was called with correct parameters
                amazon_q_client._retry_send_event.assert_called_once_with(
                    client_error, mock_request.code, payload, event_id
                )
            else:
                # Verify normal _send_event was called
                amazon_q_client._send_event.assert_called_once_with(event_id, payload)

    def test_generate_code_recommendations(
        self, q_client, mock_q_client, mock_event_request
    ):
        q_client.generate_code_recommendations(
            {"fileContext": {"context": "content"}, "maxResults": 1}
        )
        mock_q_client.generate_code_recommendations.assert_called_once_with(
            fileContext={"context": "content"},
            maxResults=1,
        )

    def test_delete_o_auth_app_connection_success(self, q_client, mock_q_client):
        q_client.delete_o_auth_app_connection()
        mock_q_client.delete_o_auth_app_connection.assert_called_once_with()

    def test_delete_o_auth_app_connection_on_conflict(
        self, q_client, mock_q_client, mock_application_request, params
    ):
        error_response = {
            "Error": {"Code": "ConflictException", "Message": "A conflict occurred"}
        }
        mock_q_client.delete_o_auth_app_connection.side_effect = ClientError(
            error_response, "delete_o_auth_app_connection"
        )

        q_client.delete_o_auth_app_connection()

        mock_q_client.delete_o_auth_app_connection.assert_called_once_with()

    def test_delete_o_auth_app_connection_raises_non_conflict_aws_errors(
        self, q_client, mock_q_client, mock_application_request
    ):
        error_response = {
            "Error": {"Code": "ValidationException", "Message": "invalid message"}
        }
        mock_q_client.delete_o_auth_app_connection.side_effect = ClientError(
            error_response, "delete_o_auth_app_connection"
        )

        with pytest.raises(AWSException):
            q_client.delete_o_auth_app_connection()

        mock_q_client.delete_o_auth_app_connection.assert_called_once()
