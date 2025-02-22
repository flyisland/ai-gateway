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
        mock_request.code = "test_code"

        # Configure mocks for event_id resolution
        amazon_q_client._resolve_event_id = Mock(return_value=event_id)
        amazon_q_client._get_payload = Mock(return_value=payload)
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

    @pytest.mark.parametrize(
        "event_request,expected_event_id",
        [
            ("event_request_hook", SYSTEM_HOOK_EVENT_MAP.get("merge_request")),
            ("event_request_merge", QUICK_ACTION_EVENT_ID),
            ("event_request_issue", QUICK_ACTION_EVENT_ID),
        ],
    )
    def test_resolve_event_id(
        self, amazon_q_client, event_request, expected_event_id, request
    ):
        """Tests event ID resolution for different payload types."""
        # Get the actual fixture from the request
        event_request = request.getfixturevalue(event_request)
        result = amazon_q_client._resolve_event_id(event_request)
        assert result == expected_event_id

    @pytest.mark.parametrize(
        "event_request_fixture,expected_result,exclude_attrs",
        [
            # Test EventHookPayload with data to exclude
            (
                "event_request_hook",
                {
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
                    },
                },
                ["object_kind"],  # Exclude 'object_kind' from the result
            ),
            # Test EventHookPayload with no exclusions
            (
                "event_request_hook",
                {
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
                    },
                },
                [],  # No exclusions
            ),
            # Test MergeRequestPayload with none values
            (
                "event_request_merge",
                {
                    "source": "merge_request",
                    "merge_request_id": "1",
                    "merge_request_iid": "1",
                    "command": "dev",
                    "project_path": "a/b/c",
                    "project_id": "123",
                    "note_id": "1",
                    "discussion_id": "1",
                    "source_branch": "dev",
                    "target_branch": "main",
                    "last_commit_id": "123",
                },
                None,  # Not used for MergeRequestPayload
            ),
            # Test IssuePayload with none values
            (
                "event_request_issue",
                {
                    "source": "issue",
                    "issue_id": "1",
                    "issue_iid": "1",
                    "command": "dev",
                    "project_path": "a/b/c",
                    "project_id": "123",
                    "note_id": "1",
                    "discussion_id": "1",
                },
                None,  # Not used for IssuePayload
            ),
            # Test unknown payload type
            ("event_request_unknown", None, None),  # Need to create this fixture
        ],
    )
    def test_get_payload_processing(
        self,
        amazon_q_client,
        event_request_fixture,
        expected_result,
        exclude_attrs,
        request,
        monkeypatch,
    ):
        try:
            event_request = request.getfixturevalue(event_request_fixture)
        except pytest.FixtureLookupError:
            if event_request_fixture == "event_request_unknown":
                # Create a mock unknown payload type
                mock_payload = Mock()
                mock_payload.__class__.__name__ = "UnknownPayloadType"
                event_request = Mock()
                event_request.payload = mock_payload
            else:
                raise

        # Set exclude attributes
        if exclude_attrs is not None:
            monkeypatch.setattr(
                "ai_gateway.integrations.amazon_q.client.EXCLUDE_EVENT_ATTRIBUTES",
                exclude_attrs,
            )

        # Mock request_log to capture warnings
        mock_logger = Mock()
        monkeypatch.setattr(
            "ai_gateway.integrations.amazon_q.client.request_log", mock_logger
        )

        # Process the payload
        result = amazon_q_client._get_payload(event_request)

        # Verify the result
        assert result == expected_result

        # Verify warning log for unknown payload type
        if event_request_fixture == "event_request_unknown":
            mock_logger.warn.assert_called_once_with("Unknown event payload, ignore")
