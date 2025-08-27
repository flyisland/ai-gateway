"""
GitLab Context Service for providing GitLab-specific information for billing events.

This service provides the missing fields needed for complete billing event context:
- seat_ids: List of seat IDs associated with the user
- unique_instance_id: Unique identifier for the GitLab instance
- root_namespace_id: Ultimate parent namespace ID
"""

import os
import uuid
from typing import List, Optional
import structlog

log = structlog.stdlib.get_logger(__name__)


class GitLabContextService:
    """Service for providing GitLab-specific context information."""
    
    def __init__(self):
        self._cached_seat_ids: Optional[List[str]] = None
        self._cached_unique_instance_id: Optional[str] = None
        self._cached_root_namespace_id: Optional[int] = None
    
    def get_seat_ids(self, user_id: Optional[str] = None) -> List[str]:
        """
        Get seat IDs associated with the user.
        
        Args:
            user_id: Optional user ID to get specific seat information
            
        Returns:
            List of seat IDs, or empty list if not available
        """
        if self._cached_seat_ids is not None:
            return self._cached_seat_ids
            
        try:
            # Try to get seat IDs from environment variable
            seat_ids_env = os.getenv("GITLAB_SEAT_IDS")
            if seat_ids_env:
                seat_ids = [seat_id.strip() for seat_id in seat_ids_env.split(",") if seat_id.strip()]
                self._cached_seat_ids = seat_ids
                return seat_ids
            
            # Fallback: generate a default seat ID based on user or instance
            if user_id:
                default_seat_id = f"seat-{user_id}"
            else:
                default_seat_id = f"seat-{uuid.uuid4().hex[:8]}"
            
            self._cached_seat_ids = [default_seat_id]
            log.info("Generated default seat ID", seat_id=default_seat_id)
            return self._cached_seat_ids
            
        except Exception as e:
            log.warning("Failed to get seat IDs", error=str(e))
            self._cached_seat_ids = []
            return []
    
    def get_unique_instance_id(self) -> str:
        """
        Get unique instance ID for the GitLab instance.
        
        Returns:
            Unique instance identifier
        """
        if self._cached_unique_instance_id is not None:
            return self._cached_unique_instance_id
            
        try:
            # Try to get from environment variable
            instance_id = os.getenv("GITLAB_UNIQUE_INSTANCE_ID")
            if instance_id:
                self._cached_unique_instance_id = instance_id
                return instance_id
            
            # Try to get from GitLab instance ID
            gitlab_instance_id = os.getenv("GITLAB_INSTANCE_ID")
            if gitlab_instance_id:
                self._cached_unique_instance_id = gitlab_instance_id
                return gitlab_instance_id
            
            # Fallback: generate a unique instance ID
            fallback_id = f"instance-{uuid.uuid4().hex[:12]}"
            self._cached_unique_instance_id = fallback_id
            log.info("Generated fallback unique instance ID", instance_id=fallback_id)
            return fallback_id
            
        except Exception as e:
            log.warning("Failed to get unique instance ID", error=str(e))
            fallback_id = f"instance-{uuid.uuid4().hex[:12]}"
            self._cached_unique_instance_id = fallback_id
            return fallback_id
    
    def get_root_namespace_id(self, namespace_id: Optional[int] = None) -> Optional[int]:
        """
        Get the ultimate parent namespace ID.
        
        Args:
            namespace_id: Current namespace ID to find parent for
            
        Returns:
            Root namespace ID, or None if not available
        """
        if self._cached_root_namespace_id is not None:
            return self._cached_root_namespace_id
            
        try:
            # Try to get from environment variable
            root_ns_env = os.getenv("GITLAB_ROOT_NAMESPACE_ID")
            if root_ns_env:
                try:
                    root_ns_id = int(root_ns_env)
                    self._cached_root_namespace_id = root_ns_id
                    return root_ns_id
                except ValueError:
                    log.warning("Invalid GITLAB_ROOT_NAMESPACE_ID", value=root_ns_env)
            
            # If we have a namespace_id, we could potentially traverse up the hierarchy
            # For now, return the namespace_id as fallback
            if namespace_id:
                self._cached_root_namespace_id = namespace_id
                return namespace_id
            
            # No namespace information available
            self._cached_root_namespace_id = None
            return None
            
        except Exception as e:
            log.warning("Failed to get root namespace ID", error=str(e))
            self._cached_root_namespace_id = None
            return None
    
    def get_gitlab_billing_context(
        self, 
        user_id: Optional[str] = None, 
        namespace_id: Optional[int] = None
    ) -> dict:
        """
        Get complete GitLab billing context information.
        
        Args:
            user_id: Optional user ID for seat information
            namespace_id: Optional namespace ID for hierarchy information
            
        Returns:
            Dictionary with GitLab billing context fields
        """
        return {
            "seat_ids": self.get_seat_ids(user_id),
            "unique_instance_id": self.get_unique_instance_id(),
            "root_namespace_id": self.get_root_namespace_id(namespace_id)
        }


# Global instance for easy access
gitlab_context_service = GitLabContextService()
