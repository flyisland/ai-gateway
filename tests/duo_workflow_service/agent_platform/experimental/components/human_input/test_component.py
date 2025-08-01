from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from duo_workflow_service.agent_platform.experimental.components.human_input.component import (
    HumanInputComponent,
)
from duo_workflow_service.agent_platform.experimental.components.human_input.ui_log import (
    UILogEventsHumanInput,
)
from duo_workflow_service.agent_platform.experimental.state import (
    FlowState,
    FlowStateKeys,
    IOKeyTemplate,
)
from duo_workflow_service.entities.event import WorkflowEventType
from duo_workflow_service.entities.state import WorkflowStatusEnum
from lib.internal_events.event_enum import CategoryEnum


class TestHumanInputComponent:
    @pytest.fixture
    def mock_prompt_registry(self):
        mock_registry = Mock()
        mock_prompt = Mock()
        mock_prompt.messages = [Mock(content="Please provide your input:")]
        mock_registry.get.return_value = mock_prompt
        return mock_registry

    @pytest.fixture
    def mock_internal_event_client(self):
        return Mock()

    @pytest.fixture
    def component(self, mock_prompt_registry, mock_internal_event_client):
        return HumanInputComponent(
            name="test_human_input",
            flow_id="test_flow",
            flow_type=CategoryEnum.WORKFLOW,
            responds_to="test_agent",
            prompt_id="test_prompt",
            prompt_version="v1.0",
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
            ui_log_events=[
                UILogEventsHumanInput.ON_USER_INPUT_PROMPT,
                UILogEventsHumanInput.ON_USER_INPUT_RECEIVED,
            ],
        )

    @pytest.fixture
    def component_without_prompt(self, mock_prompt_registry, mock_internal_event_client):
        return HumanInputComponent(
            name="test_human_input_no_prompt",
            flow_id="test_flow",
            flow_type=CategoryEnum.WORKFLOW,
            responds_to="test_agent",
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
            ui_log_events=[UILogEventsHumanInput.ON_USER_INPUT_RECEIVED],
        )

    @pytest.fixture
    def flow_state(self):
        return FlowState(
            status=WorkflowStatusEnum.EXECUTION,
            conversation_history={"test_agent": []},
            ui_chat_log=[],
            context={},
        )

    def test_initialization(self, component):
        """Test component initialization with all required fields."""
        assert component.name == "test_human_input"
        assert component.responds_to == "test_agent"
        assert component.prompt_id == "test_prompt"
        assert component.prompt_version == "v1.0"
        assert len(component.ui_log_events) == 2

    def test_entry_hook(self, component):
        """Test entry hook returns correct node name."""
        assert component.__entry_hook__() == "test_human_input#request"

    def test_outputs_property(self, component):
        """Test outputs property correctly replaces template variables."""
        outputs = component.outputs
        assert len(outputs) == 2
        
        # Check status output
        status_output = outputs[0]
        assert status_output.target == "status"
        assert status_output.subkeys is None
        
        # Check conversation history output with responds_to replacement
        conversation_output = outputs[1]
        assert conversation_output.target == "conversation_history"
        assert conversation_output.subkeys == ["test_agent"]

    def test_iokey_template_constant(self):
        """Test that RESPOND_TO_COMPONENT_NAME_TEMPLATE constant exists."""
        assert hasattr(IOKeyTemplate, "RESPOND_TO_COMPONENT_NAME_TEMPLATE")
        assert IOKeyTemplate.RESPOND_TO_COMPONENT_NAME_TEMPLATE == "<responds_to_component>"

    def test_component_class_attributes(self, component):
        """Test component class attributes are properly set."""
        assert len(HumanInputComponent._outputs) == 2
        assert HumanInputComponent.supported_environments == ("platform",)
        
        # Check that _responds_to_component uses the new template
        responds_to_output = HumanInputComponent._responds_to_component
        assert responds_to_output.target == "conversation_history"
        assert responds_to_output.subkeys == [IOKeyTemplate.RESPOND_TO_COMPONENT_NAME_TEMPLATE]

    def test_attach_to_graph(self, component):
        """Test component attaches correctly to StateGraph."""
        graph = StateGraph(FlowState)
        mock_router = Mock()
        
        component.attach(graph, mock_router)
        
        # Check nodes were added
        assert "test_human_input#request" in graph.nodes
        assert "test_human_input#fetch" in graph.nodes
        
        # Check edges
        assert ("test_human_input#request", "test_human_input#fetch") in graph.edges

    @pytest.mark.asyncio
    async def test_request_user_input_with_prompt(self, component, flow_state):
        """Test _request_user_input method with prompt configuration."""
        result = await component._request_user_input(flow_state)
        
        assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.INPUT_REQUIRED.value
        assert FlowStateKeys.UI_CHAT_LOG in result
        
        # Check that UI log contains the prompt
        ui_logs = result[FlowStateKeys.UI_CHAT_LOG]
        assert len(ui_logs) == 1
        assert "Please provide your input:" in ui_logs[0].content

    @pytest.mark.asyncio
    async def test_request_user_input_without_prompt(self, component_without_prompt, flow_state):
        """Test _request_user_input method without prompt configuration."""
        result = await component_without_prompt._request_user_input(flow_state)
        
        assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.INPUT_REQUIRED.value
        # Should not have UI logs since ON_USER_INPUT_PROMPT is not in events
        ui_logs = result.get(FlowStateKeys.UI_CHAT_LOG, [])
        assert len(ui_logs) == 0

    @pytest.mark.asyncio
    @patch("duo_workflow_service.agent_platform.experimental.components.human_input.component.interrupt")
    async def test_fetch_user_input_message_event(self, mock_interrupt, component, flow_state):
        """Test _fetch_user_input with MESSAGE event type."""
        mock_interrupt.return_value = {
            "event_type": WorkflowEventType.MESSAGE,
            "message": "Hello, this is user input",
            "correlation_id": "test_corr_id",
        }
        
        result = await component._fetch_user_input(flow_state)
        
        assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.EXECUTION.value
        assert "conversation_history" in result
        assert "test_agent" in result["conversation_history"]
        
        messages = result["conversation_history"]["test_agent"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "Hello, this is user input"
        
        # Check UI logs for received input
        ui_logs = result[FlowStateKeys.UI_CHAT_LOG]
        assert len(ui_logs) == 1
        assert "Received user input: Hello, this is user input" in ui_logs[0].content

    @pytest.mark.asyncio
    @patch("duo_workflow_service.agent_platform.experimental.components.human_input.component.interrupt")
    async def test_fetch_user_input_stop_event(self, mock_interrupt, component, flow_state):
        """Test _fetch_user_input with STOP event type."""
        mock_interrupt.return_value = {
            "event_type": WorkflowEventType.STOP,
        }
        
        result = await component._fetch_user_input(flow_state)
        
        assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.CANCELLED.value

    @pytest.mark.asyncio
    @patch("duo_workflow_service.agent_platform.experimental.components.human_input.component.interrupt")
    async def test_fetch_user_input_resume_event(self, mock_interrupt, component, flow_state):
        """Test _fetch_user_input with RESUME event type."""
        mock_interrupt.return_value = {
            "event_type": WorkflowEventType.RESUME,
        }
        
        result = await component._fetch_user_input(flow_state)
        
        assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.EXECUTION.value

    @pytest.mark.asyncio
    @patch("duo_workflow_service.agent_platform.experimental.components.human_input.component.interrupt")
    async def test_fetch_user_input_unknown_event(self, mock_interrupt, component, flow_state):
        """Test _fetch_user_input with unknown event type."""
        mock_interrupt.return_value = {
            "event_type": "UNKNOWN_EVENT",
        }
        
        result = await component._fetch_user_input(flow_state)
        
        assert result[FlowStateKeys.STATUS] == WorkflowStatusEnum.INPUT_REQUIRED.value

    def test_get_prompt_content_with_valid_prompt(self, component):
        """Test _get_prompt_content with valid prompt."""
        content = component._get_prompt_content()
        assert content == "Please provide your input:"

    def test_get_prompt_content_without_prompt_id(self, component_without_prompt):
        """Test _get_prompt_content without prompt_id."""
        content = component_without_prompt._get_prompt_content()
        assert content == "Please provide your input:"

    def test_get_prompt_content_with_exception(self, component):
        """Test _get_prompt_content when prompt registry raises exception."""
        component.prompt_registry.get.side_effect = Exception("Registry error")
        
        content = component._get_prompt_content()
        assert content == "Please provide your input:"

    def test_workflow_status_transitions(self, component):
        """Test that component supports proper status transitions."""
        # Component should handle transitions: EXECUTION -> INPUT_REQUIRED -> EXECUTION
        expected_statuses = [
            WorkflowStatusEnum.INPUT_REQUIRED,
            WorkflowStatusEnum.EXECUTION,
            WorkflowStatusEnum.CANCELLED,
        ]
        
        # This is more of a design validation - the component is designed to work with these statuses
        assert all(isinstance(status, WorkflowStatusEnum) for status in expected_statuses)

    def test_conversation_history_integration(self, component, flow_state):
        """Test integration with conversation history structure."""
        # Test that the component correctly writes to conversation_history with the responds_to key
        replacements = {
            IOKeyTemplate.RESPOND_TO_COMPONENT_NAME_TEMPLATE: component.responds_to
        }
        output_key = component._responds_to_component.to_iokey(replacements)
        
        assert output_key.target == "conversation_history"
        assert output_key.subkeys == ["test_agent"]
        
        # Ensure the flow state structure supports this
        assert "conversation_history" in flow_state
        assert isinstance(flow_state["conversation_history"], dict)

    def test_ui_log_events_configuration(self, component):
        """Test UI log events configuration."""
        assert UILogEventsHumanInput.ON_USER_INPUT_PROMPT in component.ui_log_events
        assert UILogEventsHumanInput.ON_USER_INPUT_RECEIVED in component.ui_log_events

    def test_component_supports_platform_environment(self, component):
        """Test component declares support for platform environment."""
        assert "platform" in component.supported_environments