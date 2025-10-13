"""Tests for enhanced error models."""

import pytest
from datetime import datetime, timezone

from duo_workflow_service.errors.enhanced_error_models import (
    ErrorContext,
    ErrorResponseBuilder,
    TechnicalError,
    UserFriendlyError,
    WorkflowError,
    WorkflowErrorCategory,
    WorkflowErrorCode,
    WorkflowErrorResponse,
    WorkflowErrorSeverity,
)
from duo_workflow_service.entities.state import MessageTypeEnum, ToolStatus


class TestWorkflowErrorModels:
    """Test workflow error model classes."""
    
    def test_user_friendly_error_creation(self):
        """Test creating a user-friendly error."""
        error = UserFriendlyError(
            title="Test Error",
            message="This is a test error message",
            suggestions=["Try again", "Contact support"],
            documentation_url="https://docs.example.com/error"
        )
        
        assert error.title == "Test Error"
        assert error.message == "This is a test error message"
        assert len(error.suggestions) == 2
        assert error.documentation_url == "https://docs.example.com/error"
    
    def test_technical_error_creation(self):
        """Test creating a technical error."""
        error = TechnicalError(
            exception_type="ValueError",
            stack_trace="Traceback...",
            request_id="req-123"
        )
        
        assert error.exception_type == "ValueError"
        assert error.stack_trace == "Traceback..."
        assert error.request_id == "req-123"
        assert isinstance(error.timestamp, datetime)
    
    def test_error_context_creation(self):
        """Test creating error context."""
        context = ErrorContext(
            component="agent",
            operation="llm_request",
            tool_name="test_tool",
            agent_name="test_agent",
            workflow_id="workflow-123",
            correlation_id="corr-456",
            additional_data={"key": "value"}
        )
        
        assert context.component == "agent"
        assert context.operation == "llm_request"
        assert context.tool_name == "test_tool"
        assert context.agent_name == "test_agent"
        assert context.workflow_id == "workflow-123"
        assert context.correlation_id == "corr-456"
        assert context.additional_data == {"key": "value"}
    
    def test_workflow_error_creation(self):
        """Test creating a complete workflow error."""
        user_friendly = UserFriendlyError(
            title="API Error",
            message="The API request failed",
            suggestions=["Try again later"]
        )
        
        technical = TechnicalError(
            exception_type="APIError",
            request_id="req-123"
        )
        
        context = ErrorContext(
            component="llm",
            operation="api_request"
        )
        
        error = WorkflowError(
            code=WorkflowErrorCode.LLM_API_ERROR,
            severity=WorkflowErrorSeverity.HIGH,
            category=WorkflowErrorCategory.EXTERNAL_SERVICE,
            user_friendly=user_friendly,
            technical=technical,
            context=context,
            retry_after=60,
            is_retryable=True
        )
        
        assert error.code == WorkflowErrorCode.LLM_API_ERROR
        assert error.severity == WorkflowErrorSeverity.HIGH
        assert error.category == WorkflowErrorCategory.EXTERNAL_SERVICE
        assert error.user_friendly.title == "API Error"
        assert error.technical.exception_type == "APIError"
        assert error.context.component == "llm"
        assert error.retry_after == 60
        assert error.is_retryable is True
        assert isinstance(error.created_at, datetime)


class TestWorkflowErrorResponse:
    """Test workflow error response creation."""
    
    def test_create_error_response(self):
        """Test creating a complete error response."""
        response = WorkflowErrorResponse.create_error_response(
            error_code=WorkflowErrorCode.TOOL_EXECUTION_FAILED,
            user_title="Tool Failed",
            user_message="The tool execution failed",
            severity=WorkflowErrorSeverity.HIGH,
            category=WorkflowErrorCategory.SYSTEM,
            suggestions=["Try again", "Use alternative approach"],
            correlation_id="corr-123"
        )
        
        assert response.error.code == WorkflowErrorCode.TOOL_EXECUTION_FAILED
        assert response.error.user_friendly.title == "Tool Failed"
        assert response.error.user_friendly.message == "The tool execution failed"
        assert len(response.error.user_friendly.suggestions) == 2
        
        # Check UI chat log
        assert response.ui_chat_log["message_type"] == MessageTypeEnum.AGENT
        assert response.ui_chat_log["message_sub_type"] == "error"
        assert response.ui_chat_log["content"] == "The tool execution failed"
        assert response.ui_chat_log["status"] == ToolStatus.FAILURE
        assert response.ui_chat_log["correlation_id"] == "corr-123"
    
    def test_create_error_response_with_context(self):
        """Test creating error response with context."""
        context = ErrorContext(
            component="tool",
            operation="file_read",
            tool_name="read_file"
        )
        
        technical = TechnicalError(
            exception_type="FileNotFoundError",
            request_id="req-456"
        )
        
        response = WorkflowErrorResponse.create_error_response(
            error_code=WorkflowErrorCode.TOOL_EXECUTION_FAILED,
            user_title="File Not Found",
            user_message="The requested file could not be found",
            context=context,
            technical=technical,
            is_retryable=False
        )
        
        assert response.error.context.component == "tool"
        assert response.error.context.tool_name == "read_file"
        assert response.error.technical.exception_type == "FileNotFoundError"
        assert response.error.is_retryable is False


class TestErrorResponseBuilder:
    """Test error response builder."""
    
    def test_builder_basic_usage(self):
        """Test basic builder usage."""
        response = (
            ErrorResponseBuilder()
            .with_code(WorkflowErrorCode.LLM_RATE_LIMIT)
            .with_severity(WorkflowErrorSeverity.MEDIUM)
            .with_category(WorkflowErrorCategory.RESOURCE)
            .with_user_message("Rate Limited", "Too many requests")
            .with_suggestions(["Wait and retry"])
            .with_correlation_id("corr-789")
            .build()
        )
        
        assert response.error.code == WorkflowErrorCode.LLM_RATE_LIMIT
        assert response.error.severity == WorkflowErrorSeverity.MEDIUM
        assert response.error.category == WorkflowErrorCategory.RESOURCE
        assert response.error.user_friendly.title == "Rate Limited"
        assert response.error.user_friendly.message == "Too many requests"
        assert response.error.user_friendly.suggestions == ["Wait and retry"]
        assert response.ui_chat_log["correlation_id"] == "corr-789"
    
    def test_builder_with_all_options(self):
        """Test builder with all options."""
        context = ErrorContext(component="agent", operation="completion")
        technical = TechnicalError(exception_type="TimeoutError")
        
        response = (
            ErrorResponseBuilder()
            .with_code(WorkflowErrorCode.LLM_TIMEOUT)
            .with_severity(WorkflowErrorSeverity.MEDIUM)
            .with_category(WorkflowErrorCategory.RESOURCE)
            .with_user_message("Timeout", "Request timed out")
            .with_suggestions(["Try again", "Reduce request size"])
            .with_context(context)
            .with_technical_details(technical)
            .with_retry_info(30, True)
            .with_correlation_id("corr-abc")
            .build()
        )
        
        assert response.error.code == WorkflowErrorCode.LLM_TIMEOUT
        assert response.error.context.component == "agent"
        assert response.error.technical.exception_type == "TimeoutError"
        assert response.error.retry_after == 30
        assert response.error.is_retryable is True
    
    def test_builder_validation_error_code_required(self):
        """Test that builder requires error code."""
        with pytest.raises(ValueError, match="Error code is required"):
            ErrorResponseBuilder().with_user_message("Title", "Message").build()
    
    def test_builder_validation_user_message_required(self):
        """Test that builder requires user message."""
        with pytest.raises(ValueError, match="User title and message are required"):
            ErrorResponseBuilder().with_code(WorkflowErrorCode.UNKNOWN_ERROR).build()
    
    def test_builder_chaining(self):
        """Test that builder methods return self for chaining."""
        builder = ErrorResponseBuilder()
        
        assert builder.with_code(WorkflowErrorCode.UNKNOWN_ERROR) is builder
        assert builder.with_severity(WorkflowErrorSeverity.LOW) is builder
        assert builder.with_category(WorkflowErrorCategory.SYSTEM) is builder
        assert builder.with_user_message("Title", "Message") is builder
        assert builder.with_suggestions(["suggestion"]) is builder
        assert builder.with_correlation_id("corr-123") is builder


class TestErrorEnums:
    """Test error enumeration values."""
    
    def test_error_codes_exist(self):
        """Test that all expected error codes exist."""
        expected_codes = [
            "llm_api_error",
            "llm_rate_limit",
            "tool_execution_failed",
            "gitlab_api_error",
            "workflow_timeout",
            "input_validation_error",
            "internal_error",
            "unknown_error",
        ]
        
        for code in expected_codes:
            assert hasattr(WorkflowErrorCode, code.upper())
    
    def test_error_severities_exist(self):
        """Test that all expected severities exist."""
        expected_severities = ["low", "medium", "high", "critical"]
        
        for severity in expected_severities:
            assert hasattr(WorkflowErrorSeverity, severity.upper())
    
    def test_error_categories_exist(self):
        """Test that all expected categories exist."""
        expected_categories = [
            "user_input",
            "external_service",
            "system",
            "permission",
            "resource",
        ]
        
        for category in expected_categories:
            assert hasattr(WorkflowErrorCategory, category.upper())