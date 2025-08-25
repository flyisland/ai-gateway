"""Tests for tool_use_filter module."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from duo_workflow_service.message_filters.tool_use_filter import (
    filter_orphaned_tool_use_blocks,
    apply_tool_use_filter_to_conversation_history,
)


class TestFilterOrphanedToolUseBlocks:
    """Test cases for filter_orphaned_tool_use_blocks function."""

    def test_empty_messages(self):
        """Test with empty message list."""
        result = filter_orphaned_tool_use_blocks([])
        assert result == []

    def test_no_tool_calls(self):
        """Test with messages that have no tool calls."""
        messages = [
            SystemMessage(content="System message"),
            HumanMessage(content="Human message"),
            AIMessage(content="AI response without tools"),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == messages

    def test_valid_tool_use_with_result(self):
        """Test with valid tool_use that has corresponding tool_result."""
        messages = [
            SystemMessage(content="System message"),
            HumanMessage(content="Human message"),
            AIMessage(
                content="I'll use a tool",
                tool_calls=[{"id": "call_123", "name": "test_tool", "args": {}}]
            ),
            ToolMessage(content="Tool result", tool_call_id="call_123"),
            AIMessage(content="Based on the tool result..."),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == messages

    def test_orphaned_tool_use_filtered_out(self):
        """Test that the last orphaned tool_use block is filtered out."""
        messages = [
            SystemMessage(content="System message"),
            HumanMessage(content="Human message"),
            AIMessage(
                content="I'll use a tool",
                tool_calls=[{"id": "call_123", "name": "test_tool", "args": {}}]
            ),
            # No ToolMessage for call_123
            HumanMessage(content="Another human message"),
            AIMessage(content="Regular AI response"),
        ]
        expected = [
            SystemMessage(content="System message"),
            HumanMessage(content="Human message"),
            # AIMessage with orphaned tool_call should be filtered out
            HumanMessage(content="Another human message"),
            AIMessage(content="Regular AI response"),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == expected

    def test_multiple_tool_calls_some_orphaned(self):
        """Test AIMessage with multiple tool_calls where some are orphaned."""
        messages = [
            SystemMessage(content="System message"),
            AIMessage(
                content="I'll use multiple tools",
                tool_calls=[
                    {"id": "call_123", "name": "tool1", "args": {}},
                    {"id": "call_456", "name": "tool2", "args": {}},
                ]
            ),
            ToolMessage(content="Tool1 result", tool_call_id="call_123"),
            # No ToolMessage for call_456 - this makes the tool request orphaned
            AIMessage(content="Regular response"),
        ]
        expected = [
            SystemMessage(content="System message"),
            # AIMessage with mixed tool_calls should be filtered out since not all have responses
            ToolMessage(content="Tool1 result", tool_call_id="call_123"),
            AIMessage(content="Regular response"),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == expected

    def test_multiple_tool_calls_all_have_results(self):
        """Test AIMessage with multiple tool_calls where all have results."""
        messages = [
            SystemMessage(content="System message"),
            AIMessage(
                content="I'll use multiple tools",
                tool_calls=[
                    {"id": "call_123", "name": "tool1", "args": {}},
                    {"id": "call_456", "name": "tool2", "args": {}},
                ]
            ),
            ToolMessage(content="Tool1 result", tool_call_id="call_123"),
            ToolMessage(content="Tool2 result", tool_call_id="call_456"),
            AIMessage(content="Based on both tools..."),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == messages

    def test_tool_call_without_id(self):
        """Test tool_call without id (should raise KeyError)."""
        # Create AIMessage with tool_calls manually to bypass validation
        ai_message = AIMessage(content="I'll use a tool")
        ai_message.tool_calls = [{"name": "test_tool", "args": {}}]  # No id
        
        messages = [
            SystemMessage(content="System message"),
            ai_message,
            AIMessage(content="Regular response"),
        ]
        
        with pytest.raises(KeyError):
            filter_orphaned_tool_use_blocks(messages)

    def test_tool_message_without_tool_call_id(self):
        """Test ToolMessage with mismatched tool_call_id (simulates missing tool_call_id scenario)."""
        messages = [
            SystemMessage(content="System message"),
            AIMessage(
                content="I'll use a tool",
                tool_calls=[{"id": "call_123", "name": "test_tool", "args": {}}]
            ),
            ToolMessage(content="Tool result", tool_call_id="different_id"),  # Mismatched tool_call_id
            AIMessage(content="Regular response"),
        ]
        expected = [
            SystemMessage(content="System message"),
            # AIMessage should be filtered out as its tool_call has no matching result
            ToolMessage(content="Tool result", tool_call_id="different_id"),
            AIMessage(content="Regular response"),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == expected

    def test_complex_conversation_flow_with_last_orphaned(self):
        """Test complex conversation where the last tool request is orphaned."""
        messages = [
            SystemMessage(content="System message"),
            HumanMessage(content="Please help me"),
            
            # Valid tool use
            AIMessage(
                content="I'll search for information",
                tool_calls=[{"id": "call_1", "name": "search", "args": {"query": "test"}}]
            ),
            ToolMessage(content="Search results", tool_call_id="call_1"),
            
            # Another valid tool use
            AIMessage(
                content="Let me get more details",
                tool_calls=[{"id": "call_2", "name": "details", "args": {}}]
            ),
            ToolMessage(content="Detailed info", tool_call_id="call_2"),
            
            # Last tool request is orphaned
            AIMessage(
                content="Let me try one more tool",
                tool_calls=[{"id": "call_3", "name": "analyze", "args": {}}]
            ),
            # No ToolMessage for call_3
            
            AIMessage(content="Based on the information..."),
        ]
        
        expected = [
            SystemMessage(content="System message"),
            HumanMessage(content="Please help me"),
            
            # Valid tool use preserved
            AIMessage(
                content="I'll search for information",
                tool_calls=[{"id": "call_1", "name": "search", "args": {"query": "test"}}]
            ),
            ToolMessage(content="Search results", tool_call_id="call_1"),
            
            # Another valid tool use preserved
            AIMessage(
                content="Let me get more details",
                tool_calls=[{"id": "call_2", "name": "details", "args": {}}]
            ),
            ToolMessage(content="Detailed info", tool_call_id="call_2"),
            
            # Last orphaned tool use filtered out
            
            AIMessage(content="Based on the information..."),
        ]
        
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == expected

    def test_pending_tool_request_at_end(self):
        """Test that a tool request at the end of conversation is preserved (valid pending request)."""
        messages = [
            SystemMessage(content="System message"),
            HumanMessage(content="Please help me"),
            AIMessage(
                content="I'll use a tool to help",
                tool_calls=[{"id": "call_123", "name": "search", "args": {"query": "test"}}]
            ),
            # No ToolMessage yet - this is a valid pending request
        ]
        # Should preserve all messages since the last tool request is pending
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == messages

    def test_earlier_orphaned_tool_preserved_if_last_is_valid(self):
        """Test that earlier orphaned tools are preserved if the last tool request is valid."""
        messages = [
            SystemMessage(content="System message"),
            
            # Earlier orphaned tool use (not the last one)
            AIMessage(
                content="First tool attempt",
                tool_calls=[{"id": "call_1", "name": "tool1", "args": {}}]
            ),
            # No ToolMessage for call_1
            
            HumanMessage(content="Try again"),
            
            # Last tool request is valid
            AIMessage(
                content="Second tool attempt",
                tool_calls=[{"id": "call_2", "name": "tool2", "args": {}}]
            ),
            ToolMessage(content="Tool2 result", tool_call_id="call_2"),
            
            AIMessage(content="Success!"),
        ]
        
        # Should preserve all messages since only the last tool request matters
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == messages

    def test_mismatched_tool_call_id_in_response(self):
        """Test that mismatched tool_call_id in response makes the request orphaned."""
        messages = [
            SystemMessage(content="System message"),
            AIMessage(
                content="I'll use a tool",
                tool_calls=[{"id": "call_123", "name": "test_tool", "args": {}}]
            ),
            ToolMessage(content="Tool result", tool_call_id="call_456"),  # Wrong ID
            AIMessage(content="Regular response"),
        ]
        expected = [
            SystemMessage(content="System message"),
            # AIMessage should be filtered out due to mismatched tool_call_id
            ToolMessage(content="Tool result", tool_call_id="call_456"),
            AIMessage(content="Regular response"),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == expected

    def test_multiple_tool_calls_partial_match(self):
        """Test multiple tool_calls where only one matches the response."""
        messages = [
            SystemMessage(content="System message"),
            AIMessage(
                content="I'll use multiple tools",
                tool_calls=[
                    {"id": "call_123", "name": "tool1", "args": {}},
                    {"id": "call_456", "name": "tool2", "args": {}},
                ]
            ),
            ToolMessage(content="Tool1 result", tool_call_id="call_123"),  # Only matches first tool
            AIMessage(content="Regular response"),
        ]
        expected = [
            SystemMessage(content="System message"),
            # AIMessage should be filtered out since not all tool_calls have responses
            ToolMessage(content="Tool1 result", tool_call_id="call_123"),
            AIMessage(content="Regular response"),
        ]
        result = filter_orphaned_tool_use_blocks(messages)
        assert result == expected


class TestApplyToolUseFilterToConversationHistory:
    """Test cases for apply_tool_use_filter_to_conversation_history function."""

    def test_empty_conversation_history(self):
        """Test with empty conversation history."""
        result = apply_tool_use_filter_to_conversation_history({})
        assert result == {}

    def test_single_agent_conversation(self):
        """Test with single agent conversation."""
        conversation_history = {
            "agent1": [
                SystemMessage(content="System message"),
                AIMessage(
                    content="I'll use a tool",
                    tool_calls=[{"id": "call_123", "name": "test_tool", "args": {}}]
                ),
                # No ToolMessage - should be filtered since it's the last tool request
                AIMessage(content="Regular response"),
            ]
        }
        
        expected = {
            "agent1": [
                SystemMessage(content="System message"),
                # Orphaned AIMessage filtered out
                AIMessage(content="Regular response"),
            ]
        }
        
        result = apply_tool_use_filter_to_conversation_history(conversation_history)
        assert result == expected

    def test_multiple_agents_conversation(self):
        """Test with multiple agents in conversation history."""
        conversation_history = {
            "agent1": [
                SystemMessage(content="Agent1 system"),
                AIMessage(
                    content="Agent1 tool use",
                    tool_calls=[{"id": "call_1", "name": "tool1", "args": {}}]
                ),
                ToolMessage(content="Tool1 result", tool_call_id="call_1"),
                AIMessage(content="Agent1 response"),
            ],
            "agent2": [
                SystemMessage(content="Agent2 system"),
                AIMessage(
                    content="Agent2 orphaned tool use",
                    tool_calls=[{"id": "call_2", "name": "tool2", "args": {}}]
                ),
                # No ToolMessage for call_2 - this is the last tool request so it gets filtered
                AIMessage(content="Agent2 response"),
            ]
        }
        
        expected = {
            "agent1": [
                SystemMessage(content="Agent1 system"),
                AIMessage(
                    content="Agent1 tool use",
                    tool_calls=[{"id": "call_1", "name": "tool1", "args": {}}]
                ),
                ToolMessage(content="Tool1 result", tool_call_id="call_1"),
                AIMessage(content="Agent1 response"),
            ],
            "agent2": [
                SystemMessage(content="Agent2 system"),
                # Orphaned AIMessage filtered out
                AIMessage(content="Agent2 response"),
            ]
        }
        
        result = apply_tool_use_filter_to_conversation_history(conversation_history)
        assert result == expected

    def test_agent_with_empty_messages(self):
        """Test with agent that has empty message list."""
        conversation_history = {
            "agent1": [],
            "agent2": [
                SystemMessage(content="System message"),
                AIMessage(content="Regular response"),
            ]
        }
        
        result = apply_tool_use_filter_to_conversation_history(conversation_history)
        assert result == conversation_history