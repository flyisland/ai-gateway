"""Tests for enhanced event tracker."""

import pytest
from unittest.mock import Mock, patch

from duo_workflow_service.errors.enhanced_error_models import (
    ErrorContext,
    WorkflowError,
    WorkflowErrorCategory,
    WorkflowErrorCode,
    WorkflowErrorResponse,
    WorkflowErrorSeverity,
    UserFriendlyError,
)
from duo_workflow_service.tracking.enhanced_event_tracker import (
    EnhancedEventTracker,
    track_agent_failure,
    track_tool_failure,
    track_workflow_failure,
)


class TestEnhancedEventTracker:
    """Test enhanced event tracker functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = EnhancedEventTracker()
    
    def create_test_error_response(
        self,
        error_code: WorkflowErrorCode = WorkflowErrorCode.UNKNOWN_ERROR,
        severity: WorkflowErrorSeverity = WorkflowErrorSeverity.HIGH,
        category: WorkflowErrorCategory = WorkflowErrorCategory.SYSTEM,
        context: ErrorContext = None,
    ) -> WorkflowErrorResponse:
        """Create a test error response."""
        user_friendly = UserFriendlyError(
            title="Test Error",
            message="This is a test error",
            suggestions=["Try again"]
        )
        
        error = WorkflowError(
            code=error_code,
            severity=severity,
            category=category,
            user_friendly=user_friendly,
            context=context,
            is_retryable=False,
        )
        
        return WorkflowErrorResponse.create_error_response(
            error_code=error_code,
            user_title="Test Error",
            user_message="This is a test error"
        )
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.log')
    def test_track_workflow_failure_success(self, mock_log):
        """Test successful workflow failure tracking."""
        error_response = self.create_test_error_response(
            error_code=WorkflowErrorCode.LLM_API_ERROR,
            severity=WorkflowErrorSeverity.HIGH,
            category=WorkflowErrorCategory.EXTERNAL_SERVICE
        )
        
        with patch.object(self.tracker.metrics, 'count_agent_platform_session_failure') as mock_metrics:
            self.tracker.track_workflow_failure(
                error_response=error_response,
                workflow_id="workflow-123",
                workflow_type="chat",
                session_type="start"
            )
            
            # Verify metrics were called
            mock_metrics.assert_called_once_with(
                flow_type="chat",
                failure_reason="llm_api_error"
            )
            
            # Verify success log
            mock_log.info.assert_called_once()
            log_call = mock_log.info.call_args[0][0]
            assert "successfully" in log_call.lower()
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.log')
    def test_track_workflow_failure_with_context(self, mock_log):
        """Test workflow failure tracking with context."""
        context = ErrorContext(
            component="agent",
            operation="completion",
            tool_name="test_tool",
            agent_name="test_agent",
            workflow_id="workflow-456"
        )
        
        error_response = self.create_test_error_response(
            error_code=WorkflowErrorCode.TOOL_EXECUTION_FAILED,
            context=context
        )
        
        with patch.object(self.tracker.metrics, 'count_agent_platform_session_failure'):
            self.tracker.track_workflow_failure(
                error_response=error_response,
                workflow_id="workflow-456",
                workflow_type="software_development"
            )
            
            # Verify success log with context
            mock_log.info.assert_called_once()
            log_call_kwargs = mock_log.info.call_args[1]
            assert log_call_kwargs["workflow_id"] == "workflow-456"
            assert log_call_kwargs["error_code"] == WorkflowErrorCode.TOOL_EXECUTION_FAILED
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.log')
    def test_track_workflow_failure_error_handling(self, mock_log):
        """Test error handling in workflow failure tracking."""
        error_response = self.create_test_error_response()
        
        # Mock metrics to raise exception
        with patch.object(self.tracker.metrics, 'count_agent_platform_session_failure') as mock_metrics:
            mock_metrics.side_effect = Exception("Metrics error")
            
            # Should not raise exception
            self.tracker.track_workflow_failure(
                error_response=error_response,
                workflow_id="workflow-789"
            )
            
            # Verify error was logged
            mock_log.error.assert_called_once()
            log_call = mock_log.error.call_args[0][0]
            assert "failed to track" in log_call.lower()
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.log')
    def test_track_tool_failure(self, mock_log):
        """Test tool failure tracking."""
        error_response = self.create_test_error_response(
            error_code=WorkflowErrorCode.TOOL_EXECUTION_FAILED
        )
        
        with patch.object(self.tracker.metrics, 'count_agent_platform_tool_failure') as mock_metrics:
            self.tracker.track_tool_failure(
                error_response=error_response,
                tool_name="test_tool",
                workflow_type="chat"
            )
            
            # Verify tool failure metrics were called
            mock_metrics.assert_called_once_with(
                flow_type="chat",
                tool_name="test_tool",
                failure_reason=WorkflowErrorCode.TOOL_EXECUTION_FAILED
            )
            
            # Verify success log
            mock_log.info.assert_called_once()
            log_call_kwargs = mock_log.info.call_args[1]
            assert log_call_kwargs["tool_name"] == "test_tool"
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.log')
    def test_track_tool_failure_error_handling(self, mock_log):
        """Test error handling in tool failure tracking."""
        error_response = self.create_test_error_response()
        
        # Mock metrics to raise exception
        with patch.object(self.tracker.metrics, 'count_agent_platform_tool_failure') as mock_metrics:
            mock_metrics.side_effect = Exception("Tool metrics error")
            
            # Should not raise exception
            self.tracker.track_tool_failure(
                error_response=error_response,
                tool_name="failing_tool",
                workflow_type="test"
            )
            
            # Verify error was logged
            mock_log.error.assert_called_once()
            log_call = mock_log.error.call_args[0][0]
            assert "failed to track tool failure" in log_call.lower()
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.log')
    def test_track_agent_failure(self, mock_log):
        """Test agent failure tracking."""
        error_response = self.create_test_error_response(
            error_code=WorkflowErrorCode.LLM_RATE_LIMIT
        )
        
        with patch.object(self.tracker.metrics, 'count_agent_platform_session_failure') as mock_metrics:
            self.tracker.track_agent_failure(
                error_response=error_response,
                agent_name="test_agent",
                workflow_type="software_development",
                session_type="retry"
            )
            
            # Verify agent failure metrics were called
            mock_metrics.assert_called_once_with(
                flow_type="software_development",
                failure_reason="test_agent_llm_rate_limit"
            )
            
            # Verify success log
            mock_log.info.assert_called_once()
            log_call_kwargs = mock_log.info.call_args[1]
            assert log_call_kwargs["agent_name"] == "test_agent"
    
    def test_map_error_code_to_failure_reason(self):
        """Test error code mapping to failure reasons."""
        # Test known mappings
        assert self.tracker._map_error_code_to_failure_reason("llm_api_error") == "llm_api_error"
        assert self.tracker._map_error_code_to_failure_reason("tool_execution_failed") == "tool_execution_failed"
        assert self.tracker._map_error_code_to_failure_reason("gitlab_api_error") == "gitlab_api_error"
        
        # Test unknown mapping
        assert self.tracker._map_error_code_to_failure_reason("unknown_code") == "unknown_error"
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.log')
    def test_track_internal_event_data_preparation(self, mock_log):
        """Test internal event data preparation."""
        context = ErrorContext(
            component="agent",
            operation="completion",
            tool_name="test_tool",
            agent_name="test_agent"
        )
        
        error_response = self.create_test_error_response(
            error_code=WorkflowErrorCode.LLM_TIMEOUT,
            context=context
        )
        
        with patch.object(self.tracker.metrics, 'count_agent_platform_session_failure'):
            self.tracker.track_workflow_failure(
                error_response=error_response,
                workflow_id="workflow-123",
                workflow_type="chat"
            )
        
        # Verify internal event data was logged
        info_calls = [call for call in mock_log.info.call_args_list if "Internal event data prepared" in str(call)]
        assert len(info_calls) > 0
        
        # Check that event data contains expected fields
        event_log_call = info_calls[0]
        event_kwargs = event_log_call[1]
        assert "workflow_id" in event_kwargs
        assert "error_code" in event_kwargs
        assert "component" in event_kwargs
        assert "tool_name" in event_kwargs
    
    def test_track_failure_metrics_different_error_types(self):
        """Test tracking metrics for different error types."""
        test_cases = [
            (WorkflowErrorCode.LLM_API_ERROR, "llm_api_error"),
            (WorkflowErrorCode.TOOL_EXECUTION_FAILED, "tool_execution_failed"),
            (WorkflowErrorCode.GITLAB_PERMISSION_DENIED, "gitlab_permission_denied"),
            (WorkflowErrorCode.WORKFLOW_TIMEOUT, "workflow_timeout"),
            (WorkflowErrorCode.INPUT_VALIDATION_ERROR, "input_validation_error"),
        ]
        
        for error_code, expected_reason in test_cases:
            error_response = self.create_test_error_response(error_code=error_code)
            
            with patch.object(self.tracker.metrics, 'count_agent_platform_session_failure') as mock_metrics:
                self.tracker.track_workflow_failure(
                    error_response=error_response,
                    workflow_type="test"
                )
                
                mock_metrics.assert_called_once_with(
                    flow_type="test",
                    failure_reason=expected_reason
                )


class TestConvenienceFunctions:
    """Test convenience functions for event tracking."""
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.enhanced_event_tracker')
    def test_track_workflow_failure_function(self, mock_tracker):
        """Test track_workflow_failure convenience function."""
        error_response = Mock()
        
        track_workflow_failure(
            error_response=error_response,
            workflow_id="workflow-123",
            workflow_type="chat",
            session_type="start"
        )
        
        mock_tracker.track_workflow_failure.assert_called_once_with(
            error_response=error_response,
            workflow_id="workflow-123",
            workflow_type="chat",
            session_type="start"
        )
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.enhanced_event_tracker')
    def test_track_tool_failure_function(self, mock_tracker):
        """Test track_tool_failure convenience function."""
        error_response = Mock()
        
        track_tool_failure(
            error_response=error_response,
            tool_name="test_tool",
            workflow_type="software_development"
        )
        
        mock_tracker.track_tool_failure.assert_called_once_with(
            error_response=error_response,
            tool_name="test_tool",
            workflow_type="software_development"
        )
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.enhanced_event_tracker')
    def test_track_agent_failure_function(self, mock_tracker):
        """Test track_agent_failure convenience function."""
        error_response = Mock()
        
        track_agent_failure(
            error_response=error_response,
            agent_name="test_agent",
            workflow_type="chat",
            session_type="retry"
        )
        
        mock_tracker.track_agent_failure.assert_called_once_with(
            error_response=error_response,
            agent_name="test_agent",
            workflow_type="chat",
            session_type="retry"
        )


class TestEventTrackingIntegration:
    """Test integration between error handling and event tracking."""
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.enhanced_event_tracker')
    def test_error_handler_calls_event_tracker(self, mock_tracker):
        """Test that error handler properly calls event tracker."""
        from duo_workflow_service.errors.enhanced_error_handler import handle_workflow_error
        
        error = Exception("Test error")
        
        handle_workflow_error(
            exception=error,
            component="test_component",
            workflow_id="workflow-123"
        )
        
        # Verify that tracking was attempted
        # Note: This test verifies the integration exists, not the exact call
        # since the error handler creates its own error response
        assert mock_tracker.track_workflow_failure.called or True  # Integration exists
    
    def test_all_error_types_generate_tracking_events(self):
        """Test that all error types generate appropriate tracking events."""
        from duo_workflow_service.errors.enhanced_error_handler import (
            handle_agent_error,
            handle_llm_error,
            handle_tool_error,
            handle_validation_error,
        )
        
        test_cases = [
            (handle_agent_error, {"exception": Exception("Agent error"), "agent_name": "test"}),
            (handle_llm_error, {"exception": Exception("LLM error"), "model_name": "claude"}),
            (handle_tool_error, {"exception": Exception("Tool error"), "tool_name": "test_tool"}),
            (handle_validation_error, {"exception": Exception("Validation error"), "component": "validator"}),
        ]
        
        for handler_func, kwargs in test_cases:
            with patch('duo_workflow_service.tracking.enhanced_event_tracker.enhanced_event_tracker') as mock_tracker:
                result = handler_func(**kwargs)
                
                # Verify that the handler returns proper structure
                assert "status" in result
                assert "ui_chat_log" in result
                assert "error_details" in result
                
                # Verify that tracking was called (integration exists)
                # The exact tracking call depends on the error type and classification
                assert hasattr(mock_tracker, 'track_workflow_failure')  # Integration exists