"""Enhanced event tracking for Duo Workflow Service errors.

This module provides reliable event tracking for workflow failures with detailed
error information to improve monitoring and debugging capabilities.
"""

from typing import Any, Dict, Optional

import structlog

from duo_workflow_service.errors.enhanced_error_models import WorkflowErrorResponse
from duo_workflow_service.tracking.duo_workflow_metrics import duo_workflow_metrics
from lib.internal_events.event_enum import EventEnum, EventLabelEnum, EventPropertyEnum

log = structlog.stdlib.get_logger("enhanced_event_tracker")


class EnhancedEventTracker:
    """Enhanced event tracker for workflow failures."""
    
    def __init__(self):
        self.metrics = duo_workflow_metrics
    
    def track_workflow_failure(
        self,
        error_response: WorkflowErrorResponse,
        workflow_id: Optional[str] = None,
        workflow_type: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> None:
        """Track a workflow failure event with detailed error information."""
        
        error_info = error_response.error
        
        try:
            # Track metrics
            self._track_failure_metrics(error_info, workflow_type, session_type)
            
            # Track internal event
            self._track_internal_event(error_info, workflow_id, workflow_type)
            
            log.info(
                "Workflow failure event tracked successfully",
                workflow_id=workflow_id,
                error_code=error_info.code,
                error_category=error_info.category,
                error_severity=error_info.severity,
            )
            
        except Exception as e:
            log.error(
                "Failed to track workflow failure event",
                error=str(e),
                workflow_id=workflow_id,
                error_code=error_info.code,
                exc_info=True,
            )
    
    def track_tool_failure(
        self,
        error_response: WorkflowErrorResponse,
        tool_name: str,
        workflow_type: Optional[str] = None,
    ) -> None:
        """Track a tool-specific failure event."""
        
        error_info = error_response.error
        
        try:
            # Track tool failure metrics
            self.metrics.count_agent_platform_tool_failure(
                flow_type=workflow_type or "unknown",
                tool_name=tool_name,
                failure_reason=error_info.code,
            )
            
            log.info(
                "Tool failure event tracked successfully",
                tool_name=tool_name,
                error_code=error_info.code,
                workflow_type=workflow_type,
            )
            
        except Exception as e:
            log.error(
                "Failed to track tool failure event",
                error=str(e),
                tool_name=tool_name,
                error_code=error_info.code,
                exc_info=True,
            )
    
    def track_agent_failure(
        self,
        error_response: WorkflowErrorResponse,
        agent_name: str,
        workflow_type: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> None:
        """Track an agent-specific failure event."""
        
        error_info = error_response.error
        
        try:
            # Track agent failure metrics
            self.metrics.count_agent_platform_session_failure(
                flow_type=workflow_type or "unknown",
                failure_reason=f"{agent_name}_{error_info.code}",
            )
            
            log.info(
                "Agent failure event tracked successfully",
                agent_name=agent_name,
                error_code=error_info.code,
                workflow_type=workflow_type,
            )
            
        except Exception as e:
            log.error(
                "Failed to track agent failure event",
                error=str(e),
                agent_name=agent_name,
                error_code=error_info.code,
                exc_info=True,
            )
    
    def _track_failure_metrics(
        self,
        error_info,
        workflow_type: Optional[str],
        session_type: Optional[str],
    ) -> None:
        """Track failure metrics in Prometheus."""
        
        # Map error codes to failure reasons for metrics
        failure_reason = self._map_error_code_to_failure_reason(error_info.code)
        
        # Track session failure
        self.metrics.count_agent_platform_session_failure(
            flow_type=workflow_type or "unknown",
            failure_reason=failure_reason,
        )
    
    def _track_internal_event(
        self,
        error_info,
        workflow_id: Optional[str],
        workflow_type: Optional[str],
    ) -> None:
        """Track internal event for the failure."""
        
        # For now, we'll log the event details
        # In a full implementation, this would integrate with the internal events system
        event_data = {
            "event": EventEnum.WORKFLOW_FINISH_FAILURE,
            "label": EventLabelEnum.WORKFLOW_FINISH_LABEL,
            "workflow_id": workflow_id,
            "workflow_type": workflow_type,
            "error_code": error_info.code,
            "error_category": error_info.category,
            "error_severity": error_info.severity,
            "error_message": error_info.user_friendly.message,
            "is_retryable": error_info.is_retryable,
        }
        
        if error_info.context:
            event_data.update({
                "component": error_info.context.component,
                "operation": error_info.context.operation,
                "tool_name": error_info.context.tool_name,
                "agent_name": error_info.context.agent_name,
            })
        
        log.info("Internal event data prepared", **event_data)
    
    def _map_error_code_to_failure_reason(self, error_code: str) -> str:
        """Map error codes to failure reasons for metrics."""
        
        # Group similar error codes for better metrics aggregation
        error_code_mapping = {
            # LLM errors
            "llm_api_error": "llm_api_error",
            "llm_rate_limit": "llm_rate_limit",
            "llm_authentication_error": "llm_authentication_error",
            "llm_invalid_request": "llm_invalid_request",
            "llm_context_too_large": "llm_context_too_large",
            "llm_timeout": "llm_timeout",
            
            # Tool errors
            "tool_execution_failed": "tool_execution_failed",
            "tool_validation_error": "tool_validation_error",
            "tool_permission_denied": "tool_permission_denied",
            "tool_timeout": "tool_timeout",
            "tool_not_found": "tool_not_found",
            
            # GitLab errors
            "gitlab_api_error": "gitlab_api_error",
            "gitlab_authentication_error": "gitlab_authentication_error",
            "gitlab_permission_denied": "gitlab_permission_denied",
            "gitlab_resource_not_found": "gitlab_resource_not_found",
            "gitlab_rate_limit": "gitlab_rate_limit",
            
            # Workflow errors
            "workflow_state_invalid": "workflow_state_invalid",
            "workflow_cancelled": "workflow_cancelled",
            "workflow_timeout": "workflow_timeout",
            
            # Input errors
            "input_validation_error": "input_validation_error",
            "goal_disambiguation_failed": "goal_disambiguation_failed",
            
            # System errors
            "internal_error": "internal_error",
            "service_unavailable": "service_unavailable",
            "configuration_error": "configuration_error",
            
            # Unknown
            "unknown_error": "unknown_error",
        }
        
        return error_code_mapping.get(error_code, "unknown_error")


# Global enhanced event tracker instance
enhanced_event_tracker = EnhancedEventTracker()


def track_workflow_failure(
    error_response: WorkflowErrorResponse,
    workflow_id: Optional[str] = None,
    workflow_type: Optional[str] = None,
    session_type: Optional[str] = None,
) -> None:
    """Convenience function to track workflow failures."""
    
    enhanced_event_tracker.track_workflow_failure(
        error_response=error_response,
        workflow_id=workflow_id,
        workflow_type=workflow_type,
        session_type=session_type,
    )


def track_tool_failure(
    error_response: WorkflowErrorResponse,
    tool_name: str,
    workflow_type: Optional[str] = None,
) -> None:
    """Convenience function to track tool failures."""
    
    enhanced_event_tracker.track_tool_failure(
        error_response=error_response,
        tool_name=tool_name,
        workflow_type=workflow_type,
    )


def track_agent_failure(
    error_response: WorkflowErrorResponse,
    agent_name: str,
    workflow_type: Optional[str] = None,
    session_type: Optional[str] = None,
) -> None:
    """Convenience function to track agent failures."""
    
    enhanced_event_tracker.track_agent_failure(
        error_response=error_response,
        agent_name=agent_name,
        workflow_type=workflow_type,
        session_type=session_type,
    )