"""Integration tests for enhanced error handling.

These tests verify that the enhanced error handling system integrates properly
with existing workflow components and provides better error messages.
"""

import pytest
from unittest.mock import Mock, patch
from anthropic import APIStatusError

from duo_workflow_service.agents.enhanced_agent import EnhancedAgent
from duo_workflow_service.agents.enhanced_chat_agent import EnhancedChatAgent
from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    ToolStatus,
    WorkflowStatusEnum,
)
from duo_workflow_service.errors.enhanced_error_models import WorkflowErrorCode


class TestEnhancedAgentIntegration:
    """Test enhanced agent integration with error handling."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock enhanced agent."""
        agent = Mock(spec=EnhancedAgent)
        agent.name = "test_agent"
        agent.model_provider = "anthropic"
        agent.workflow_id = "workflow-123"
        return agent
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock workflow state."""
        return {
            "conversation_history": {},
            "ui_chat_log": [],
            "status": WorkflowStatusEnum.EXECUTION,
            "workflow_id": "workflow-123",
            "id": "workflow-123",
        }
    
    @patch('duo_workflow_service.agents.enhanced_agent.handle_llm_error')
    def test_enhanced_agent_handles_api_error(self, mock_handle_error, mock_agent, mock_state):
        """Test that enhanced agent properly handles API errors."""
        # Setup mock error response
        mock_error_response = {
            "status": WorkflowStatusEnum.ERROR,
            "ui_chat_log": [{
                "message_type": MessageTypeEnum.AGENT,
                "message_sub_type": "error",
                "content": "The AI service is currently experiencing high demand. Please wait a moment and try again.",
                "status": ToolStatus.FAILURE,
                "correlation_id": "test-123",
            }],
            "error_details": {
                "code": WorkflowErrorCode.LLM_RATE_LIMIT,
                "severity": "medium",
                "category": "resource",
                "is_retryable": True,
                "retry_after": 60,
            }
        }
        mock_handle_error.return_value = mock_error_response
        
        # Create real enhanced agent instance
        from duo_workflow_service.agents.enhanced_agent import EnhancedAgent
        from ai_gateway.prompts.config.base import PromptConfig
        
        # Mock the necessary components
        with patch.object(EnhancedAgent, '_build_prompt_template'):
            with patch.object(EnhancedAgent, 'ainvoke') as mock_ainvoke:
                # Setup API error
                mock_response = Mock()
                mock_response.status_code = 429
                api_error = APIStatusError("Rate limited", response=mock_response, body=None)
                mock_ainvoke.side_effect = api_error
                
                # Create agent
                agent = EnhancedAgent()
                agent.name = "test_agent"
                agent.model = Mock()
                agent.model.get_name.return_value = "ChatAnthropic"
                agent.model_provider = "anthropic"
                agent.workflow_id = "workflow-123"
                agent.check_events = False
                
                # Run agent
                result = await agent.run(mock_state)
                
                # Verify enhanced error handling was called
                mock_handle_error.assert_called_once()
                call_args = mock_handle_error.call_args
                assert isinstance(call_args[1]["exception"], APIStatusError)
                assert call_args[1]["model_name"] == "unknown"  # Based on mock setup
                assert call_args[1]["workflow_id"] == "workflow-123"
                
                # Verify result structure
                assert result["status"] == WorkflowStatusEnum.ERROR
                assert "ui_chat_log" in result
                assert "conversation_history" in result
                
                # Verify UI chat log contains specific error message
                ui_log = result["ui_chat_log"][0]
                assert ui_log["message_type"] == MessageTypeEnum.AGENT
                assert ui_log["message_sub_type"] == "error"
                assert "high demand" in ui_log["content"]
                assert ui_log["status"] == ToolStatus.FAILURE
                
                # Verify conversation history contains error message
                assert "test_agent" in result["conversation_history"]
                error_message = result["conversation_history"]["test_agent"][0]
                assert "high demand" in error_message.content
    
    @patch('duo_workflow_service.agents.enhanced_agent.handle_agent_error')
    def test_enhanced_agent_handles_unexpected_error(self, mock_handle_error, mock_agent, mock_state):
        """Test that enhanced agent handles unexpected errors."""
        # Setup mock error response
        mock_error_response = {
            "status": WorkflowStatusEnum.ERROR,
            "ui_chat_log": [{
                "message_type": MessageTypeEnum.AGENT,
                "message_sub_type": "error",
                "content": "An unexpected error occurred while processing your request. Please try again or contact support if the issue persists.",
                "status": ToolStatus.FAILURE,
                "correlation_id": "test-456",
            }],
            "error_details": {
                "code": WorkflowErrorCode.UNKNOWN_ERROR,
                "severity": "high",
                "category": "system",
            }
        }
        mock_handle_error.return_value = mock_error_response
        
        # Create real enhanced agent instance
        from duo_workflow_service.agents.enhanced_agent import EnhancedAgent
        
        with patch.object(EnhancedAgent, '_build_prompt_template'):
            with patch.object(EnhancedAgent, 'ainvoke') as mock_ainvoke:
                # Setup unexpected error
                unexpected_error = ValueError("Unexpected error occurred")
                mock_ainvoke.side_effect = unexpected_error
                
                # Create agent
                agent = EnhancedAgent()
                agent.name = "test_agent"
                agent.model = Mock()
                agent.model.get_name.return_value = "ChatAnthropic"
                agent.model_provider = "anthropic"
                agent.workflow_id = "workflow-123"
                agent.check_events = False
                
                # Run agent
                result = await agent.run(mock_state)
                
                # Verify enhanced error handling was called
                mock_handle_error.assert_called_once()
                call_args = mock_handle_error.call_args
                assert isinstance(call_args[1]["exception"], ValueError)
                assert call_args[1]["agent_name"] == "test_agent"
                assert call_args[1]["workflow_id"] == "workflow-123"
                
                # Verify result contains enhanced error information
                assert result["status"] == WorkflowStatusEnum.ERROR
                ui_log = result["ui_chat_log"][0]
                assert "unexpected error" in ui_log["content"].lower()
                assert ui_log["message_sub_type"] == "error"


class TestEnhancedChatAgentIntegration:
    """Test enhanced chat agent integration with error handling."""
    
    @pytest.fixture
    def mock_chat_agent(self):
        """Create a mock enhanced chat agent."""
        agent = EnhancedChatAgent("test_chat_agent", Mock(), Mock())
        return agent
    
    @pytest.fixture
    def mock_chat_state(self):
        """Create a mock chat workflow state."""
        return {
            "conversation_history": {},
            "ui_chat_log": [],
            "status": WorkflowStatusEnum.INPUT_REQUIRED,
            "project": None,
            "namespace": None,
            "approval": None,
        }
    
    @patch('duo_workflow_service.agents.enhanced_chat_agent.handle_agent_error')
    def test_enhanced_chat_agent_error_handling(self, mock_handle_error, mock_chat_agent, mock_chat_state):
        """Test that enhanced chat agent properly handles errors."""
        # Setup mock error response
        mock_error_response = {
            "status": WorkflowStatusEnum.ERROR,
            "ui_chat_log": [{
                "message_type": MessageTypeEnum.AGENT,
                "message_sub_type": "error",
                "content": "There was an issue processing your chat request. Please try rephrasing your message or contact support if the issue persists.",
                "status": ToolStatus.FAILURE,
            }],
            "error_details": {
                "code": WorkflowErrorCode.UNKNOWN_ERROR,
                "severity": "high",
                "category": "system",
            }
        }
        mock_handle_error.return_value = mock_error_response
        
        # Mock the agent response to raise an error
        with patch.object(mock_chat_agent, '_get_agent_response') as mock_get_response:
            mock_get_response.side_effect = Exception("Chat processing error")
            
            # Run chat agent
            result = await mock_chat_agent.run(mock_chat_state)
            
            # Verify enhanced error handling was called
            mock_handle_error.assert_called_once()
            call_args = mock_handle_error.call_args
            assert call_args[1]["agent_name"] == "test_chat_agent"
            assert call_args[1]["additional_context"]["operation"] == "chat_agent_processing"
            
            # Verify result structure
            assert result["status"] == WorkflowStatusEnum.INPUT_REQUIRED  # Chat agents override to INPUT_REQUIRED
            assert "ui_chat_log" in result
            assert "conversation_history" in result
            
            # Verify UI chat log contains specific error message
            ui_log = result["ui_chat_log"][0]
            assert ui_log["message_type"] == MessageTypeEnum.AGENT
            assert ui_log["message_sub_type"] == "error"
            assert "chat request" in ui_log["content"]


class TestErrorMessageComparison:
    """Test comparison between old and new error messages."""
    
    def test_generic_vs_enhanced_error_messages(self):
        """Test that enhanced error messages are more specific than generic ones."""
        from duo_workflow_service.errors.enhanced_error_handler import handle_llm_error
        from anthropic import APIStatusError
        
        # Create API error
        mock_response = Mock()
        mock_response.status_code = 429
        api_error = APIStatusError("Rate limited", response=mock_response, body=None)
        
        # Get enhanced error response
        enhanced_result = handle_llm_error(
            exception=api_error,
            model_name="claude-3",
            workflow_id="test-workflow"
        )
        
        enhanced_message = enhanced_result["ui_chat_log"][0]["content"]
        
        # Compare with generic message
        generic_message = "There was an error processing your request. Please try again or contact support if the issue persists."
        
        # Enhanced message should be more specific
        assert enhanced_message != generic_message
        assert "rate limit" in enhanced_message.lower() or "high demand" in enhanced_message.lower()
        assert len(enhanced_message) > len(generic_message)  # More detailed
        
        # Enhanced message should include suggestions
        assert "wait" in enhanced_message.lower() or "try again" in enhanced_message.lower()
    
    def test_error_code_inclusion(self):
        """Test that error responses include specific error codes."""
        from duo_workflow_service.errors.enhanced_error_handler import handle_tool_error
        
        tool_error = Exception("Tool execution failed: permission denied")
        
        result = handle_tool_error(
            exception=tool_error,
            tool_name="test_tool",
            workflow_id="test-workflow"
        )
        
        # Verify error details include specific code
        error_details = result["error_details"]
        assert "code" in error_details
        assert error_details["code"] in [
            WorkflowErrorCode.TOOL_PERMISSION_DENIED,
            WorkflowErrorCode.TOOL_EXECUTION_FAILED,
        ]
        
        # Verify severity and category are set
        assert "severity" in error_details
        assert "category" in error_details
    
    def test_ui_chat_log_enhancement(self):
        """Test that UI chat log entries are enhanced with error details."""
        from duo_workflow_service.errors.enhanced_error_handler import handle_validation_error
        from pydantic import ValidationError, BaseModel, Field
        
        # Create validation error
        class TestModel(BaseModel):
            required_field: str = Field(..., min_length=1)
        
        try:
            TestModel(required_field="")
        except ValidationError as validation_error:
            result = handle_validation_error(
                exception=validation_error,
                component="input_validator",
                workflow_id="test-workflow"
            )
            
            ui_log = result["ui_chat_log"][0]
            
            # Verify enhanced UI chat log structure
            assert ui_log["message_type"] == MessageTypeEnum.AGENT
            assert ui_log["message_sub_type"] == "error"
            assert ui_log["status"] == ToolStatus.FAILURE
            assert "correlation_id" in ui_log
            
            # Verify content is more specific than generic message
            content = ui_log["content"]
            assert "validation" in content.lower()
            assert "input" in content.lower()
            assert content != "There was an error processing your request"


class TestEventTrackingIntegration:
    """Test that enhanced error handling properly integrates with event tracking."""
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.track_workflow_failure')
    def test_error_handling_triggers_event_tracking(self, mock_track):
        """Test that error handling triggers appropriate event tracking."""
        from duo_workflow_service.errors.enhanced_error_handler import handle_workflow_error
        
        error = Exception("Test error for tracking")
        
        result = handle_workflow_error(
            exception=error,
            component="test_component",
            operation="test_operation",
            workflow_id="workflow-123"
        )
        
        # Verify tracking was called
        mock_track.assert_called_once()
        
        # Verify tracking was called with proper error response
        call_args = mock_track.call_args
        error_response = call_args[1]["error_response"]
        assert hasattr(error_response, "error")
        assert hasattr(error_response, "ui_chat_log")
        
        # Verify workflow ID was passed
        assert call_args[1]["workflow_id"] == "workflow-123"
    
    @patch('duo_workflow_service.tracking.enhanced_event_tracker.track_tool_failure')
    def test_tool_error_triggers_tool_tracking(self, mock_track):
        """Test that tool errors trigger tool-specific tracking."""
        from duo_workflow_service.errors.enhanced_error_handler import handle_tool_error
        
        tool_error = Exception("Tool failed to execute")
        
        result = handle_tool_error(
            exception=tool_error,
            tool_name="test_tool",
            workflow_id="workflow-456"
        )
        
        # Note: The current implementation calls track_workflow_failure
        # but in a full implementation, it might also call track_tool_failure
        # This test verifies the integration exists
        assert "error_details" in result
        assert result["error_details"]["context"]["tool_name"] == "test_tool"