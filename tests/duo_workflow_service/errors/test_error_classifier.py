"""Tests for error classifier."""

import pytest
from anthropic import APIStatusError
from pydantic import ValidationError
from pydantic_core import ValidationError as PydanticCoreValidationError
from unittest.mock import Mock

from duo_workflow_service.errors.error_classifier import (
    ErrorClassifier,
    classify_workflow_error,
)
from duo_workflow_service.errors.enhanced_error_models import (
    ErrorContext,
    WorkflowErrorCategory,
    WorkflowErrorCode,
    WorkflowErrorSeverity,
)


class TestErrorClassifier:
    """Test error classification functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.classifier = ErrorClassifier()
    
    def test_classify_anthropic_api_error_401(self):
        """Test classification of Anthropic 401 error."""
        # Create mock APIStatusError
        mock_response = Mock()
        mock_response.status_code = 401
        error = APIStatusError("Unauthorized", response=mock_response, body=None)
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.LLM_AUTHENTICATION_ERROR
        assert result.error.severity == WorkflowErrorSeverity.CRITICAL
        assert result.error.category == WorkflowErrorCategory.EXTERNAL_SERVICE
        assert "authentication issue" in result.error.user_friendly.message.lower()
        assert len(result.error.user_friendly.suggestions) > 0
    
    def test_classify_anthropic_api_error_429(self):
        """Test classification of Anthropic 429 rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 429
        error = APIStatusError("Rate limited", response=mock_response, body=None)
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.LLM_RATE_LIMIT
        assert result.error.severity == WorkflowErrorSeverity.MEDIUM
        assert result.error.category == WorkflowErrorCategory.RESOURCE
        assert "rate limit" in result.error.user_friendly.message.lower()
        assert result.error.is_retryable is True
        assert result.error.retry_after == 60
    
    def test_classify_anthropic_api_error_400(self):
        """Test classification of Anthropic 400 bad request error."""
        mock_response = Mock()
        mock_response.status_code = 400
        error = APIStatusError("Bad request", response=mock_response, body=None)
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.LLM_INVALID_REQUEST
        assert result.error.severity == WorkflowErrorSeverity.HIGH
        assert result.error.category == WorkflowErrorCategory.USER_INPUT
        assert "invalid" in result.error.user_friendly.message.lower()
    
    def test_classify_anthropic_api_error_500(self):
        """Test classification of Anthropic 500 server error."""
        mock_response = Mock()
        mock_response.status_code = 500
        error = APIStatusError("Server error", response=mock_response, body=None)
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.LLM_API_ERROR
        assert result.error.severity == WorkflowErrorSeverity.HIGH
        assert result.error.category == WorkflowErrorCategory.EXTERNAL_SERVICE
        assert "unavailable" in result.error.user_friendly.message.lower()
        assert result.error.is_retryable is True
        assert result.error.retry_after == 120
    
    def test_classify_validation_error(self):
        """Test classification of Pydantic validation error."""
        # Create a mock validation error
        try:
            from pydantic import BaseModel, Field
            
            class TestModel(BaseModel):
                required_field: str = Field(..., min_length=1)
            
            TestModel(required_field="")
        except ValidationError as error:
            result = self.classifier.classify_error(error)
            
            assert result.error.code == WorkflowErrorCode.INPUT_VALIDATION_ERROR
            assert result.error.severity == WorkflowErrorSeverity.MEDIUM
            assert result.error.category == WorkflowErrorCategory.USER_INPUT
            assert "validation" in result.error.user_friendly.message.lower()
    
    def test_classify_tool_permission_error(self):
        """Test classification of tool permission error."""
        error = Exception("Permission denied: insufficient privileges")
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.TOOL_PERMISSION_DENIED
        assert result.error.severity == WorkflowErrorSeverity.HIGH
        assert result.error.category == WorkflowErrorCategory.PERMISSION
        assert "permission" in result.error.user_friendly.message.lower()
    
    def test_classify_tool_timeout_error(self):
        """Test classification of tool timeout error."""
        error = Exception("Operation timeout: request took too long")
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.TOOL_TIMEOUT
        assert result.error.severity == WorkflowErrorSeverity.MEDIUM
        assert result.error.category == WorkflowErrorCategory.RESOURCE
        assert "timeout" in result.error.user_friendly.message.lower()
        assert result.error.is_retryable is True
    
    def test_classify_gitlab_401_error(self):
        """Test classification of GitLab authentication error."""
        error = Exception("GitLab API error: 401 Unauthorized")
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.GITLAB_AUTHENTICATION_ERROR
        assert result.error.severity == WorkflowErrorSeverity.CRITICAL
        assert result.error.category == WorkflowErrorCategory.EXTERNAL_SERVICE
        assert "gitlab" in result.error.user_friendly.message.lower()
    
    def test_classify_gitlab_403_error(self):
        """Test classification of GitLab permission error."""
        error = Exception("GitLab API error: 403 Forbidden")
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.GITLAB_PERMISSION_DENIED
        assert result.error.severity == WorkflowErrorSeverity.HIGH
        assert result.error.category == WorkflowErrorCategory.PERMISSION
    
    def test_classify_gitlab_404_error(self):
        """Test classification of GitLab not found error."""
        error = Exception("GitLab resource not found: 404")
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.GITLAB_RESOURCE_NOT_FOUND
        assert result.error.severity == WorkflowErrorSeverity.MEDIUM
        assert result.error.category == WorkflowErrorCategory.USER_INPUT
    
    def test_classify_timeout_error(self):
        """Test classification of generic timeout error."""
        error = Exception("Connection timeout occurred")
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.WORKFLOW_TIMEOUT
        assert result.error.severity == WorkflowErrorSeverity.MEDIUM
        assert result.error.category == WorkflowErrorCategory.RESOURCE
        assert result.error.is_retryable is True
    
    def test_classify_unknown_error(self):
        """Test classification of unknown error."""
        error = Exception("Some unexpected error occurred")
        
        result = self.classifier.classify_error(error)
        
        assert result.error.code == WorkflowErrorCode.UNKNOWN_ERROR
        assert result.error.severity == WorkflowErrorSeverity.HIGH
        assert result.error.category == WorkflowErrorCategory.SYSTEM
        assert "unexpected" in result.error.user_friendly.message.lower()
    
    def test_classify_error_with_context(self):
        """Test error classification with context."""
        error = Exception("Test error")
        context = ErrorContext(
            component="test_component",
            operation="test_operation",
            tool_name="test_tool",
            workflow_id="workflow-123"
        )
        
        result = self.classifier.classify_error(error, context, "corr-456")
        
        assert result.error.context.component == "test_component"
        assert result.error.context.operation == "test_operation"
        assert result.error.context.tool_name == "test_tool"
        assert result.error.context.workflow_id == "workflow-123"
        assert result.ui_chat_log["correlation_id"] == "corr-456"
    
    def test_classify_error_with_technical_details(self):
        """Test that technical details are included."""
        error = ValueError("Test validation error")
        
        result = self.classifier.classify_error(error, correlation_id="test-123")
        
        assert result.error.technical is not None
        assert result.error.technical.exception_type == "ValueError"
        assert result.error.technical.request_id == "test-123"
    
    def test_error_pattern_matching_tool_error(self):
        """Test tool error pattern matching."""
        assert self.classifier._is_tool_error(Exception("tool execution failed"))
        assert self.classifier._is_tool_error(Exception("command failed to run"))
        assert not self.classifier._is_tool_error(Exception("random error"))
    
    def test_error_pattern_matching_gitlab_error(self):
        """Test GitLab error pattern matching."""
        assert self.classifier._is_gitlab_api_error(Exception("gitlab api error"))
        assert self.classifier._is_gitlab_api_error(Exception("http error occurred"))
        assert not self.classifier._is_gitlab_api_error(Exception("random error"))
    
    def test_error_pattern_matching_timeout_error(self):
        """Test timeout error pattern matching."""
        assert self.classifier._is_timeout_error(Exception("connection timeout"))
        assert self.classifier._is_timeout_error(Exception("request timed out"))
        assert not self.classifier._is_timeout_error(Exception("random error"))
    
    def test_error_pattern_matching_permission_error(self):
        """Test permission error pattern matching."""
        assert self.classifier._is_permission_error(Exception("permission denied"))
        assert self.classifier._is_permission_error(Exception("access forbidden"))
        assert not self.classifier._is_permission_error(Exception("random error"))


class TestClassifyWorkflowErrorFunction:
    """Test the convenience function for error classification."""
    
    def test_classify_workflow_error_with_all_context(self):
        """Test classify_workflow_error function with full context."""
        error = Exception("Test error")
        
        result = classify_workflow_error(
            exception=error,
            component="test_component",
            operation="test_operation",
            tool_name="test_tool",
            agent_name="test_agent",
            workflow_id="workflow-123",
            correlation_id="corr-456",
            additional_data={"key": "value"}
        )
        
        assert result.error.context.component == "test_component"
        assert result.error.context.operation == "test_operation"
        assert result.error.context.tool_name == "test_tool"
        assert result.error.context.agent_name == "test_agent"
        assert result.error.context.workflow_id == "workflow-123"
        assert result.error.context.correlation_id == "corr-456"
        assert result.error.context.additional_data == {"key": "value"}
        assert result.ui_chat_log["correlation_id"] == "corr-456"
    
    def test_classify_workflow_error_minimal_context(self):
        """Test classify_workflow_error function with minimal context."""
        error = Exception("Test error")
        
        result = classify_workflow_error(exception=error)
        
        assert result.error.code == WorkflowErrorCode.UNKNOWN_ERROR
        assert result.error.context is not None