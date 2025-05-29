from unittest.mock import MagicMock, patch

from duo_workflow_service.executor.client import ExecutorClient
from duo_workflow_service.gitlab.direct_http_client import DirectGitLabHttpClient
from duo_workflow_service.gitlab.executor_http_client import ExecutorGitLabHttpClient
from duo_workflow_service.gitlab.http_client_factory import get_http_client


def test_get_http_client_custom_gitlab(queues):
    """Test that get_http_client returns ExecutorGitLabHttpClient for custom GitLab instances."""
    executor_client = MagicMock(spec=ExecutorClient)
    base_url = "https://custom.gitlab.example.com"
    gitlab_token = "test-token"

    client = get_http_client(executor_client, base_url, gitlab_token)

    assert isinstance(client, ExecutorGitLabHttpClient)
    assert client.executor_client == executor_client


def test_get_http_client_with_env_var(queues):
    """Test that the factory respects the DUO_WORKFLOW_DIRECT_CONNECTION_BASE_URL environment variable."""
    executor_client = MagicMock(spec=ExecutorClient)
    custom_base_url = "https://custom.direct.gitlab"
    gitlab_token = "test-token"

    with patch.dict(
        "os.environ", {"DUO_WORKFLOW_DIRECT_CONNECTION_BASE_URL": custom_base_url}
    ):
        # Should return DirectGitLabHttpClient when base_url matches env var
        client = get_http_client(executor_client, custom_base_url, gitlab_token)
        assert isinstance(client, DirectGitLabHttpClient)
        assert client.base_url == custom_base_url
        assert client.gitlab_token == gitlab_token

        # Should return ExecutorGitLabHttpClient for other URLs
        other_url = "https://other.gitlab"
        client = get_http_client(executor_client, other_url, gitlab_token)
        assert isinstance(client, ExecutorGitLabHttpClient)
        assert client.executor_client == executor_client
