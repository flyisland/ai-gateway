from typing import Optional
from unittest.mock import Mock, patch

import pytest

from duo_workflow_service.gitlab.gitlab_api import Namespace, Project
from duo_workflow_service.gitlab.gitlab_instance_info_service import (
    GitLabInstanceInfoService,
)


class TestGitLabInstanceInfoService:
    """Test cases for GitLabInstanceInfoService."""

    @pytest.fixture
    def project_gitlab_com(self) -> Project:
        """Sample GitLab.com project."""
        return Project(
            id=123,
            name="test-project",
            description="Test project",
            http_url_to_repo="https://gitlab.com/test/project.git",
            web_url="https://gitlab.com/test/project",
            default_branch="main",
            languages=[],
            exclusion_rules=[],
        )

    @pytest.fixture
    def project_self_managed(self) -> Project:
        """Sample self-managed GitLab project."""
        return Project(
            id=456,
            name="self-managed-project",
            description="Self-managed project",
            http_url_to_repo="https://gitlab.example.com/test/project.git",
            web_url="https://gitlab.example.com/test/project",
            default_branch="main",
            languages=[],
            exclusion_rules=[],
        )

    @pytest.fixture
    def project_dedicated(self) -> Project:
        """Sample GitLab Dedicated project."""
        return Project(
            id=789,
            name="dedicated-project",
            description="Dedicated project",
            http_url_to_repo="https://dedicated-example.gitlab.com/test/project.git",
            web_url="https://dedicated-example.gitlab.com/test/project",
            default_branch="main",
            languages=[],
            exclusion_rules=[],
        )

    @pytest.fixture
    def namespace_gitlab_com(self) -> Namespace:
        """Sample GitLab.com namespace."""
        return Namespace(
            id=123,
            name="test-namespace",
            description="Test namespace",
            web_url="https://gitlab.com/test-namespace",
        )

    @pytest.fixture
    def namespace_self_managed(self) -> Namespace:
        """Sample self-managed GitLab namespace."""
        return Namespace(
            id=456,
            name="self-managed-namespace",
            description="Self-managed namespace",
            web_url="https://gitlab.example.com/test-namespace",
        )

    def test_create_from_project_gitlab_com(self, project_gitlab_com):
        """Test creating GitLab instance info from GitLab.com project."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "16.5.0-ee"

            service = GitLabInstanceInfoService()
            result = service.create_from_project(project_gitlab_com)

            assert result.instance_type == "GitLab.com (SaaS)"
            assert result.instance_url == "https://gitlab.com"
            assert result.instance_version == "16.5.0-ee"

    def test_create_from_project_self_managed(self, project_self_managed):
        """Test creating GitLab instance info from self-managed project."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "15.0.0-ee"

            service = GitLabInstanceInfoService()
            result = service.create_from_project(project_self_managed)

            assert result.instance_type == "Self-Managed"
            assert result.instance_url == "https://gitlab.example.com"
            assert result.instance_version == "15.0.0-ee"

    def test_create_from_project_dedicated(self, project_dedicated):
        """Test creating GitLab instance info from GitLab Dedicated project."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "16.0.0-ee"

            service = GitLabInstanceInfoService()
            result = service.create_from_project(project_dedicated)

            assert result.instance_type == "GitLab Dedicated"
            assert result.instance_url == "https://dedicated-example.gitlab.com"
            assert result.instance_version == "16.0.0-ee"

    def test_create_from_namespace_gitlab_com(self, namespace_gitlab_com):
        """Test creating GitLab instance info from GitLab.com namespace."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "16.5.0-ee"

            service = GitLabInstanceInfoService()
            result = service.create_from_namespace(namespace_gitlab_com)

            assert result.instance_type == "GitLab.com (SaaS)"
            assert result.instance_url == "https://gitlab.com"
            assert result.instance_version == "16.5.0-ee"

    def test_create_from_namespace_self_managed(self, namespace_self_managed):
        """Test creating GitLab instance info from self-managed namespace."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "15.0.0-ee"

            service = GitLabInstanceInfoService()
            result = service.create_from_namespace(namespace_self_managed)

            assert result.instance_type == "Self-Managed"
            assert result.instance_url == "https://gitlab.example.com"
            assert result.instance_version == "15.0.0-ee"

    def test_create_from_project_with_version_fallback(self, project_gitlab_com):
        """Test creating GitLab instance info when version is not available."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = None

            service = GitLabInstanceInfoService()
            result = service.create_from_project(project_gitlab_com)

            assert result.instance_type == "GitLab.com (SaaS)"
            assert result.instance_url == "https://gitlab.com"
            assert result.instance_version == "Unknown"

    def test_create_from_project_with_version_exception(self, project_gitlab_com):
        """Test creating GitLab instance info when version retrieval raises exception."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.side_effect = Exception("Version not available")

            service = GitLabInstanceInfoService()
            result = service.create_from_project(project_gitlab_com)

            assert result.instance_type == "GitLab.com (SaaS)"
            assert result.instance_url == "https://gitlab.com"
            assert result.instance_version == "Unknown"

    def test_create_from_project_none(self):
        """Test creating GitLab instance info when project is None."""
        service = GitLabInstanceInfoService()
        result = service.create_from_project(None)

        assert result.instance_type == "Unknown"
        assert result.instance_url == "Unknown"
        assert result.instance_version == "Unknown"

    def test_create_from_namespace_none(self):
        """Test creating GitLab instance info when namespace is None."""
        service = GitLabInstanceInfoService()
        result = service.create_from_namespace(None)

        assert result.instance_type == "Unknown"
        assert result.instance_url == "Unknown"
        assert result.instance_version == "Unknown"

    def test_create_from_project_and_namespace_project_priority(
        self, project_gitlab_com, namespace_self_managed
    ):
        """Test that project takes priority over namespace when both are provided."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "16.5.0-ee"

            service = GitLabInstanceInfoService()
            result = service.create_from_project_and_namespace(
                project_gitlab_com, namespace_self_managed
            )

            # Should use project info, not namespace
            assert result.instance_type == "GitLab.com (SaaS)"
            assert result.instance_url == "https://gitlab.com"
            assert result.instance_version == "16.5.0-ee"

    def test_create_from_project_and_namespace_fallback_to_namespace(
        self, namespace_self_managed
    ):
        """Test that namespace is used when project is None."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "15.0.0-ee"

            service = GitLabInstanceInfoService()
            result = service.create_from_project_and_namespace(
                None, namespace_self_managed
            )

            assert result.instance_type == "Self-Managed"
            assert result.instance_url == "https://gitlab.example.com"
            assert result.instance_version == "15.0.0-ee"

    def test_create_from_project_and_namespace_both_none(self):
        """Test that fallback values are used when both project and namespace are None."""
        service = GitLabInstanceInfoService()
        result = service.create_from_project_and_namespace(None, None)

        assert result.instance_type == "Unknown"
        assert result.instance_url == "Unknown"
        assert result.instance_version == "Unknown"

    @pytest.mark.parametrize(
        "web_url,expected_type",
        [
            ("https://gitlab.com/test/project", "GitLab.com (SaaS)"),
            ("http://gitlab.com/test/project", "GitLab.com (SaaS)"),
            ("https://gitlab.com/", "GitLab.com (SaaS)"),
            ("https://dedicated-example.gitlab.com/test", "GitLab Dedicated"),
            ("https://dedicated-test.gitlab.com/", "GitLab Dedicated"),
            ("https://gitlab.example.com/test", "Self-Managed"),
            ("https://git.company.com/test", "Self-Managed"),
            ("http://192.168.1.100:8080/test", "Self-Managed"),
            ("", "Unknown"),
            ("Unknown", "Unknown"),
            # Edge case: project name contains "dedicated-" but it's on gitlab.com
            ("https://gitlab.com/dedicated-project/smoke-tests", "GitLab.com (SaaS)"),
            ("https://gitlab.com/org/dedicated-something", "GitLab.com (SaaS)"),
            ("https://gitlab.com/dedicated-team/dedicated-repo", "GitLab.com (SaaS)"),
            # Additional edge cases for the regex
            ("https://gitlab.com/user/project-dedicated-name", "GitLab.com (SaaS)"),
            (
                "https://gitlab.com/dedicated-",
                "GitLab.com (SaaS)",
            ),  # Edge case with trailing dash
            (
                "https://dedicated.gitlab.com/test",
                "GitLab.com (SaaS)",
            ),  # Missing dash after dedicated
            (
                "https://not-dedicated-example.gitlab.com/test",
                "GitLab.com (SaaS)",
            ),  # Doesn't start with dedicated-
        ],
    )
    def test_determine_instance_type_from_url(self, web_url, expected_type):
        """Test instance type determination from various URLs."""
        service = GitLabInstanceInfoService()
        result = service._determine_instance_type_from_url(web_url)
        assert result == expected_type

    @pytest.mark.parametrize(
        "web_url,expected_url",
        [
            ("https://gitlab.com/test/project", "https://gitlab.com"),
            ("http://gitlab.com/test/project", "http://gitlab.com"),
            ("https://gitlab.example.com/test/project", "https://gitlab.example.com"),
            ("https://git.company.com:8080/test", "https://git.company.com:8080"),
            ("http://192.168.1.100:8080/test", "http://192.168.1.100:8080"),
            ("", "Unknown"),
            ("Unknown", "Unknown"),
        ],
    )
    def test_extract_base_url_from_web_url(self, web_url, expected_url):
        """Test base URL extraction from various web URLs."""
        service = GitLabInstanceInfoService()
        result = service._extract_base_url_from_web_url(web_url)
        assert result == expected_url

    def test_get_gitlab_version_success(self):
        """Test successful GitLab version retrieval."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = "16.5.0-ee"

            service = GitLabInstanceInfoService()
            result = service._get_gitlab_version()
            assert result == "16.5.0-ee"

    def test_get_gitlab_version_none(self):
        """Test GitLab version retrieval when version is None."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.return_value = None

            service = GitLabInstanceInfoService()
            result = service._get_gitlab_version()
            assert result == "Unknown"

    def test_get_gitlab_version_exception(self):
        """Test GitLab version retrieval when exception is raised."""
        with patch(
            "duo_workflow_service.gitlab.gitlab_instance_info_service.gitlab_version"
        ) as mock_version:
            mock_version.get.side_effect = Exception("Version not available")

            service = GitLabInstanceInfoService()
            result = service._get_gitlab_version()
            assert result == "Unknown"
