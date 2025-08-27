"""
Tests for GitLab Context Service.

This module tests the GitLabContextService class which provides
GitLab-specific information for billing events.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from lib.internal_events.gitlab_context import GitLabContextService


class TestGitLabContextService:
    """Test cases for GitLabContextService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = GitLabContextService()
        # Clear any cached values
        self.service._cached_seat_ids = None
        self.service._cached_unique_instance_id = None
        self.service._cached_root_namespace_id = None
    
    def test_get_seat_ids_from_environment(self):
        """Test getting seat IDs from environment variable."""
        with patch.dict(os.environ, {"GITLAB_SEAT_IDS": "seat-1,seat-2,seat-3"}):
            seat_ids = self.service.get_seat_ids()
            assert seat_ids == ["seat-1", "seat-2", "seat-3"]
    
    def test_get_seat_ids_with_user_id_fallback(self):
        """Test generating seat ID when user ID is provided."""
        seat_ids = self.service.get_seat_ids(user_id="user123")
        assert len(seat_ids) == 1
        assert seat_ids[0].startswith("seat-user123")
    
    def test_get_seat_ids_without_user_id_fallback(self):
        """Test generating seat ID when no user ID is provided."""
        seat_ids = self.service.get_seat_ids()
        assert len(seat_ids) == 1
        assert seat_ids[0].startswith("seat-")
        assert len(seat_ids[0]) > 8  # Should be longer than just "seat-"
    
    def test_get_seat_ids_caching(self):
        """Test that seat IDs are cached after first retrieval."""
        with patch.dict(os.environ, {"GITLAB_SEAT_IDS": "seat-1"}):
            # First call should set cache
            seat_ids1 = self.service.get_seat_ids()
            assert seat_ids1 == ["seat-1"]
            
            # Clear environment to test caching
            with patch.dict(os.environ, {}, clear=True):
                seat_ids2 = self.service.get_seat_ids()
                assert seat_ids2 == ["seat-1"]  # Should use cached value
    
    def test_get_unique_instance_id_from_environment(self):
        """Test getting unique instance ID from environment variable."""
        with patch.dict(os.environ, {"GITLAB_UNIQUE_INSTANCE_ID": "instance-abc123"}):
            instance_id = self.service.get_unique_instance_id()
            assert instance_id == "instance-abc123"
    
    def test_get_unique_instance_id_from_gitlab_instance_id(self):
        """Test getting unique instance ID from GitLab instance ID."""
        with patch.dict(os.environ, {"GITLAB_INSTANCE_ID": "gitlab-instance-456"}):
            instance_id = self.service.get_unique_instance_id()
            assert instance_id == "gitlab-instance-456"
    
    def test_get_unique_instance_id_fallback(self):
        """Test generating fallback unique instance ID."""
        instance_id = self.service.get_unique_instance_id()
        assert instance_id.startswith("instance-")
        assert len(instance_id) > 12  # Should be longer than just "instance-"
    
    def test_get_unique_instance_id_caching(self):
        """Test that unique instance ID is cached after first retrieval."""
        with patch.dict(os.environ, {"GITLAB_UNIQUE_INSTANCE_ID": "instance-xyz"}):
            # First call should set cache
            instance_id1 = self.service.get_unique_instance_id()
            assert instance_id1 == "instance-xyz"
            
            # Clear environment to test caching
            with patch.dict(os.environ, {}, clear=True):
                instance_id2 = self.service.get_unique_instance_id()
                assert instance_id2 == "instance-xyz"  # Should use cached value
    
    def test_get_root_namespace_id_from_environment(self):
        """Test getting root namespace ID from environment variable."""
        with patch.dict(os.environ, {"GITLAB_ROOT_NAMESPACE_ID": "123"}):
            root_ns_id = self.service.get_root_namespace_id()
            assert root_ns_id == 123
    
    def test_get_root_namespace_id_with_namespace_id_fallback(self):
        """Test using provided namespace ID as fallback."""
        root_ns_id = self.service.get_root_namespace_id(namespace_id=456)
        assert root_ns_id == 456
    
    def test_get_root_namespace_id_none_when_not_available(self):
        """Test returning None when no namespace information is available."""
        root_ns_id = self.service.get_root_namespace_id()
        assert root_ns_id is None
    
    def test_get_root_namespace_id_invalid_environment_value(self):
        """Test handling invalid environment variable value."""
        with patch.dict(os.environ, {"GITLAB_ROOT_NAMESPACE_ID": "invalid"}):
            root_ns_id = self.service.get_root_namespace_id()
            assert root_ns_id is None
    
    def test_get_root_namespace_id_caching(self):
        """Test that root namespace ID is cached after first retrieval."""
        with patch.dict(os.environ, {"GITLAB_ROOT_NAMESPACE_ID": "789"}):
            # First call should set cache
            root_ns_id1 = self.service.get_root_namespace_id()
            assert root_ns_id1 == 789
            
            # Clear environment to test caching
            with patch.dict(os.environ, {}, clear=True):
                root_ns_id2 = self.service.get_root_namespace_id()
                assert root_ns_id2 == 789  # Should use cached value
    
    def test_get_gitlab_billing_context_complete(self):
        """Test getting complete GitLab billing context."""
        with patch.dict(os.environ, {
            "GITLAB_SEAT_IDS": "seat-1,seat-2",
            "GITLAB_UNIQUE_INSTANCE_ID": "instance-xyz",
            "GITLAB_ROOT_NAMESPACE_ID": "123"
        }):
            context = self.service.get_gitlab_billing_context(
                user_id="user456",
                namespace_id=789
            )
            
            assert context["seat_ids"] == ["seat-1", "seat-2"]
            assert context["unique_instance_id"] == "instance-xyz"
            assert context["root_namespace_id"] == 123
    
    def test_get_gitlab_billing_context_with_fallbacks(self):
        """Test getting GitLab billing context with fallback values."""
        context = self.service.get_gitlab_billing_context(
            user_id="user789",
            namespace_id=456
        )
        
        assert len(context["seat_ids"]) == 1
        assert context["seat_ids"][0].startswith("seat-user789")
        assert context["unique_instance_id"].startswith("instance-")
        assert context["root_namespace_id"] == 456
    
    def test_get_gitlab_billing_context_no_user_or_namespace(self):
        """Test getting GitLab billing context without user or namespace."""
        context = self.service.get_gitlab_billing_context()
        
        assert len(context["seat_ids"]) == 1
        assert context["seat_ids"][0].startswith("seat-")
        assert context["unique_instance_id"].startswith("instance-")
        assert context["root_namespace_id"] is None
    
    def test_error_handling_in_get_seat_ids(self):
        """Test error handling in get_seat_ids method."""
        with patch('uuid.uuid4', side_effect=Exception("UUID error")):
            seat_ids = self.service.get_seat_ids()
            assert seat_ids == []
    
    def test_error_handling_in_get_unique_instance_id(self):
        """Test error handling in get_unique_instance_id method."""
        with patch('uuid.uuid4', side_effect=Exception("UUID error")):
            instance_id = self.service.get_unique_instance_id()
            assert instance_id.startswith("instance-")
    
    def test_error_handling_in_get_root_namespace_id(self):
        """Test error handling in get_root_namespace_id method."""
        with patch('os.getenv', side_effect=Exception("Environment error")):
            root_ns_id = self.service.get_root_namespace_id()
            assert root_ns_id is None
