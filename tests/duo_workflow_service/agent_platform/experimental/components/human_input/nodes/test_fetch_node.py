from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from duo_workflow_service.agent_platform.experimental.components.human_input.nodes.fetch_node import (
    FetchNode,
)
from duo_workflow_service.agent_platform.experimental.state import FlowStateKeys, IOKey
from duo_workflow_service.agent_platform.experimental.state.base import FlowEventType
from duo_workflow_service.entities.state import WorkflowStatusEnum


class TestFetchNode:
    """Test suite for FetchNode."""

    @pytest.fixture
    def fetch_node(self):
        """Create FetchNode instance for testing."""
        return FetchNode(
            name="test_component#fetch",
            component_name="test_component",
            responds_to="target_agent",
            output=IOKey(target="context", subkeys=["test_component", "approval"]),
        )

    @pytest.fixture
    def sample_state(self):
        """Create sample FlowState for testing."""
        return {
            "status": WorkflowStatusEnum.INPUT_REQUIRED,
            "conversation_history": {},
            "ui_chat_log": [],
            "context": {},
        }

    @pytest.mark.asyncio
    async def test_interrupt_handling_response_event(self, fetch_node, sample_state):
        """Test successful interrupt handling with RESPONSE event."""
        mock_event = {
            "event_type": FlowEventType.RESPONSE,
            "message": "User input response",
        }

        with patch(
            "duo_workflow_service.agent_platform.experimental.components.human_input.nodes.fetch_node.interrupt",
            return_value=mock_event,
        ):
            result = await fetch_node.run(sample_state)

            # Verify status transition to EXECUTION
            assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.EXECUTION.value

            # Verify conversation history contains HumanMessage
            assert FlowStateKeys.CONVERSATION_HISTORY in result
            conversation = result[FlowStateKeys.CONVERSATION_HISTORY]
            assert "target_agent" in conversation
            assert len(conversation["target_agent"]) == 1

            message = conversation["target_agent"][0]
            assert isinstance(message, HumanMessage)
            assert message.content == "User input response"

    @pytest.mark.asyncio
    async def test_interrupt_handling_approve_event(self, fetch_node, sample_state):
        """Test that APPROVE event stores approval in context."""
        mock_event = {
            "event_type": FlowEventType.APPROVE,
        }

        with patch(
            "duo_workflow_service.agent_platform.experimental.components.human_input.nodes.fetch_node.interrupt",
            return_value=mock_event,
        ):
            result = await fetch_node.run(sample_state)

            # Verify status transition to EXECUTION
            assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.EXECUTION.value

            # Verify approval is stored in context
            assert "context" in result
            assert "test_component" in result["context"]
            assert result["context"]["test_component"]["approval"] == "approve"

    @pytest.mark.asyncio
    async def test_interrupt_handling_reject_event(self, fetch_node, sample_state):
        """Test that REJECT event stores rejection in context and adds HumanMessage if message present."""
        mock_event = {
            "event_type": FlowEventType.REJECT,
            "message": "User rejected with reason",
        }

        with patch(
            "duo_workflow_service.agent_platform.experimental.components.human_input.nodes.fetch_node.interrupt",
            return_value=mock_event,
        ):
            result = await fetch_node.run(sample_state)

            # Verify status transition to EXECUTION
            assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.EXECUTION.value

            # Verify rejection is stored in context
            assert "context" in result
            assert "test_component" in result["context"]
            assert result["context"]["test_component"]["approval"] == "reject"

            # Verify HumanMessage is added to conversation history for REJECT with message
            assert FlowStateKeys.CONVERSATION_HISTORY in result
            conversation = result[FlowStateKeys.CONVERSATION_HISTORY]
            assert "target_agent" in conversation
            assert len(conversation["target_agent"]) == 1

            message = conversation["target_agent"][0]
            assert isinstance(message, HumanMessage)
            assert message.content == "User rejected with reason"

    @pytest.mark.asyncio
    async def test_interrupt_handling_reject_event_without_message(
        self, fetch_node, sample_state
    ):
        """Test that REJECT event without message stores rejection in context but no HumanMessage."""
        mock_event = {
            "event_type": FlowEventType.REJECT,
        }

        with patch(
            "duo_workflow_service.agent_platform.experimental.components.human_input.nodes.fetch_node.interrupt",
            return_value=mock_event,
        ):
            result = await fetch_node.run(sample_state)

            # Verify status transition to EXECUTION
            assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.EXECUTION.value

            # Verify rejection is stored in context
            assert "context" in result
            assert "test_component" in result["context"]
            assert result["context"]["test_component"]["approval"] == "reject"

            # Verify no conversation history is added when no message
            assert FlowStateKeys.CONVERSATION_HISTORY not in result

    @pytest.mark.asyncio
    async def test_interrupt_handling_unknown_event(self, fetch_node, sample_state):
        """Test interrupt handling with unknown event type raises ValueError."""
        mock_event = {
            "event_type": "UNKNOWN_EVENT_TYPE",
        }

        with patch(
            "duo_workflow_service.agent_platform.experimental.components.human_input.nodes.fetch_node.interrupt",
            return_value=mock_event,
        ):
            with pytest.raises(
                ValueError, match="Unknown event type: UNKNOWN_EVENT_TYPE"
            ):
                await fetch_node.run(sample_state)

    @pytest.mark.asyncio
    async def test_interrupt_message_format(self, fetch_node, sample_state):
        """Test that interrupt is called with correct message format."""
        mock_event = {
            "event_type": FlowEventType.RESPONSE,
            "message": "User response",
        }

        with patch(
            "duo_workflow_service.agent_platform.experimental.components.human_input.nodes.fetch_node.interrupt",
            return_value=mock_event,
        ) as mock_interrupt:
            await fetch_node.run(sample_state)

            # Verify interrupt was called with expected message
            mock_interrupt.assert_called_once_with(
                "Workflow interrupted; waiting for user input."
            )
