"""Tests for enhanced error handler."""

import pytest
from unittest.mock import Mock, patch
from anthropic import APIStatusError

from duo_workflow_service.entities.state import WorkflowStatusEnum
from duo_workflow_service.errors.enhanced_error_handler import (
    EnhancedErrorHandler,
    handle_agent_error,
    handle_llm_error,
    handle_tool_error,
    handle_validation_error,
    handle_workflow_error,
)
from duo_workflow_service.errors.enhanced_error_models import (
    WorkflowErrorCode,
    WorkflowErrorSeverity,
)


class TestEnhancedErrorHandler:
    """Test enhanced error handler functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.handler = EnhancedErrorHandler()
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure')
    def test_handle_workflow_error_basic(self, mock_track):
        """Test basic workflow error handling."""
        error = Exception("Test error")
        
        result = self.handler.handle_workflow_error(
            exception=error,
            component="test_component",
            operation="test_operation"
        )
        
        assert result["status"] == WorkflowStatusEnum.ERROR
        assert "ui_chat_log" in result
        assert len(result["ui_chat_log"]) == 1
        assert "error_details" in result
        
        # Verify tracking was called
        mock_track.assert_called_once()
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure')
    def test_handle_agent_error(self, mock_track):
        """Test agent-specific error handling."""
        error = Exception("Agent failed")
        
        result = self.handler.handle_agent_error(
            exception=error,
            agent_name="test_agent",
            workflow_id="workflow-123"
        )
        
        assert result["status"] == WorkflowStatusEnum.ERROR
        assert result["ui_chat_log"][0]["content"] != "There was an error processing your request"
        
        # Verify tracking was called
        mock_track.assert_called_once()
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure')
    def test_handle_tool_error(self, mock_track):
        """Test tool-specific error handling."""
        error = Exception("Tool execution failed")
        
        result = self.handler.handle_tool_error(
            exception=error,
            tool_name="test_tool",
            workflow_id="workflow-456"
        )
        
        assert result["status"] == WorkflowStatusEnum.ERROR
        assert "test_tool" in result["error_details"]["context"]["tool_name"]
        
        # Verify tracking was called
        mock_track.assert_called_once()
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure')
    def test_handle_llm_error(self, mock_track):
        """Test LLM-specific error handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        error = APIStatusError("Rate limited", response=mock_response, body=None)
        
        result = self.handler.handle_llm_error(
            exception=error,
            model_name="claude-3",
            workflow_id="workflow-789"
        )
        
        assert result["status"] == WorkflowStatusEnum.ERROR
        assert result["error_details"]["code"] == WorkflowErrorCode.LLM_RATE_LIMIT
        assert result["error_details"]["is_retryable"] is True
        
        # Verify tracking was called
        mock_track.assert_called_once()
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure')
    def test_handle_validation_error(self, mock_track):
        """Test validation error handling."""
        from pydantic import ValidationError, BaseModel, Field
        
        class TestModel(BaseModel):
            required_field: str = Field(..., min_length=1)
        
        try:
            TestModel(required_field="")
        except ValidationError as error:
            result = self.handler.handle_validation_error(
                exception=error,
                component="input_validator",
                workflow_id="workflow-abc"
            )
            
            assert result["status"] == WorkflowStatusEnum.ERROR
            assert result["error_details"]["code"] == WorkflowErrorCode.INPUT_VALIDATION_ERROR
            assert result["error_details"]["category"] == "user_input"
            
            # Verify tracking was called
            mock_track.assert_called_once()
    
    @patch('uuid.uuid4')
    def test_correlation_id_generation(self, mock_uuid):
        """Test correlation ID generation when not present."""
        mock_uuid.return_value = Mock()
        mock_uuid.return_value.__str__ = Mock(return_value="generated-uuid")
        
        correlation_id = self.handler._get_or_generate_correlation_id()
        
        assert correlation_id == "generated-uuid"
        mock_uuid.assert_called_once()
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.log')
    def test_error_logging(self, mock_log):
        """Test that errors are logged appropriately."""
        error = Exception("Test error")
        
        with patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure'):
            self.handler.handle_workflow_error(
                exception=error,
                component="test_component"
            )
        
        # Verify logging was called
        assert mock_log.error.called or mock_log.warning.called or mock_log.info.called
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure')
    def test_tracking_failure_handling(self, mock_track):
        """Test that tracking failures don't break error handling."""
        mock_track.side_effect = Exception("Tracking failed")
        error = Exception("Test error")
        
        # Should not raise exception even if tracking fails
        result = self.handler.handle_workflow_error(
            exception=error,
            component="test_component"
        )
        
        assert result["status"] == WorkflowStatusEnum.ERROR
        assert "ui_chat_log" in result
    
    def test_workflow_response_structure(self):
        """Test that workflow response has correct structure."""
        error = Exception("Test error")
        
        with patch('duo_workflow_service.errors.enhanced_error_handler.track_workflow_failure'):
            result = self.handler.handle_workflow_error(
                exception=error,
                component="test_component"
            )
        
        # Check required fields
        assert "status" in result
        assert "ui_chat_log" in result
        assert "error_details" in result
        
        # Check ui_chat_log structure
        ui_log = result["ui_chat_log"][0]
        assert "message_type" in ui_log
        assert "content" in ui_log
        assert "status" in ui_log
        assert "timestamp" in ui_log
        
        # Check error_details structure
        error_details = result["error_details"]
        assert "code" in error_details
        assert "severity" in error_details
        assert "category" in error_details
        assert "user_friendly" in error_details


class TestConvenienceFunctions:
    """Test convenience functions for error handling."""
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.enhanced_error_handler')
    def test_handle_workflow_error_function(self, mock_handler):
        """Test handle_workflow_error convenience function."""
        error = Exception("Test error")
        mock_handler.handle_workflow_error.return_value = {"status": "error"}
        
        result = handle_workflow_error(
            exception=error,
            component="test_component",
            tool_name="test_tool"
        )
        
        mock_handler.handle_workflow_error.assert_called_once_with(
            exception=error,
            component="test_component",
            operation=None,
            tool_name="test_tool",
            agent_name=None,
            workflow_id=None,
            additional_context=None
        )
        assert result == {"status": "error"}
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.enhanced_error_handler')
    def test_handle_agent_error_function(self, mock_handler):
        """Test handle_agent_error convenience function."""
        error = Exception("Agent error")
        mock_handler.handle_agent_error.return_value = {"status": "error"}
        
        result = handle_agent_error(
            exception=error,
            agent_name="test_agent",
            workflow_id="workflow-123"
        )
        
        mock_handler.handle_agent_error.assert_called_once_with(
            exception=error,
            agent_name="test_agent",
            workflow_id="workflow-123",
            additional_context=None
        )
        assert result == {"status": "error"}
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.enhanced_error_handler')
    def test_handle_tool_error_function(self, mock_handler):
        """Test handle_tool_error convenience function."""
        error = Exception("Tool error")
        mock_handler.handle_tool_error.return_value = {"status": "error"}
        
        result = handle_tool_error(
            exception=error,
            tool_name="test_tool",
            additional_context={"key": "value"}
        )
        
        mock_handler.handle_tool_error.assert_called_once_with(
            exception=error,
            tool_name="test_tool",
            workflow_id=None,
            additional_context={"key": "value"}
        )
        assert result == {"status": "error"}
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.enhanced_error_handler')
    def test_handle_llm_error_function(self, mock_handler):
        """Test handle_llm_error convenience function."""
        error = Exception("LLM error")
        mock_handler.handle_llm_error.return_value = {"status": "error"}
        
        result = handle_llm_error(
            exception=error,
            model_name="claude-3",
            workflow_id="workflow-456"
        )
        
        mock_handler.handle_llm_error.assert_called_once_with(
            exception=error,
            model_name="claude-3",
            workflow_id="workflow-456",
            additional_context=None
        )
        assert result == {"status": "error"}
    
    @patch('duo_workflow_service.errors.enhanced_error_handler.enhanced_error_handler')
    def test_handle_validation_error_function(self, mock_handler):
        """Test handle_validation_error convenience function."""
        error = Exception("Validation error")
        mock_handler.handle_validation_error.return_value = {"status": "error"}
        
        result = handle_validation_error(
            exception=error,
            component="validator",
            workflow_id="workflow-789"
        )
        
        mock_handler.handle_validation_error.assert_called_once_with(
            exception=error,
            component="validator",
            workflow_id="workflow-789",
            additional_context=None
        )
        assert result == {"status": "error"}