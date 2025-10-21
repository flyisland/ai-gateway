"""Test suite for AgentComponent class."""

from typing import Literal
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage

from ai_gateway.model_metadata import ModelMetadata, current_model_metadata_context
from duo_workflow_service.agent_platform.experimental.components.agent.component import (
    AgentComponent,
    RoutingError,
)
from duo_workflow_service.agent_platform.experimental.components.agent.nodes.agent_node import (
    AgentFinalOutput,
)
from duo_workflow_service.agent_platform.experimental.components.agent.ui_log import (
    UILogEventsAgent,
)
from duo_workflow_service.agent_platform.experimental.state import FlowStateKeys
from duo_workflow_service.agent_platform.experimental.state.base import IOKey
from duo_workflow_service.agent_platform.experimental.ui_log import UIHistory


@pytest.fixture(name="prompt_id")
def prompt_id_fixture():
    """Fixture for prompt ID."""
    return "test_prompt_id"


@pytest.fixture(name="prompt_version")
def prompt_version_fixture():
    """Fixture for prompt version."""
    return "v1.0"


@pytest.fixture(name="ui_log_events")
def ui_log_events_fixture():
    return []


@pytest.fixture(name="ui_role_as")
def ui_role_as_fixture() -> Literal["agent", "tool"]:
    return "agent"


@pytest.fixture(name="tool_arguments_binding")
def tool_arguments_binding_fixture():
    """Fixture for tool arguments binding."""
    return []


@pytest.fixture(name="agent_component")
def agent_component_fixture(
    component_name,
    flow_id,
    flow_type,
    prompt_id,
    prompt_version,
    ui_log_events,
    ui_role_as,
    mock_toolset,
    mock_prompt_registry,
    mock_internal_event_client,
    tool_arguments_binding,
):
    """Fixture for AgentComponent instance."""
    return AgentComponent(
        name=component_name,
        flow_id=flow_id,
        flow_type=flow_type,
        inputs=["context:user_input", "context:task_description"],
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        toolset=mock_toolset,
        tool_arguments_binding=tool_arguments_binding,
        prompt_registry=mock_prompt_registry,
        internal_event_client=mock_internal_event_client,
        ui_log_events=ui_log_events,
        ui_role_as=ui_role_as,
    )


@pytest.fixture(name="agent_component_no_output")
def agent_component_no_output_fixture(
    component_name,
    flow_id,
    flow_type,
    prompt_id,
    prompt_version,
    ui_log_events,
    ui_role_as,
    mock_toolset,
    mock_prompt_registry,
    mock_internal_event_client,
    tool_arguments_binding,
):
    """Fixture for AgentComponent instance without output."""
    return AgentComponent(
        name=component_name,
        flow_id=flow_id,
        flow_type=flow_type,
        inputs=["context:user_input", "context:task_description"],
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        toolset=mock_toolset,
        tool_arguments_binding=tool_arguments_binding,
        prompt_registry=mock_prompt_registry,
        internal_event_client=mock_internal_event_client,
        ui_log_events=ui_log_events,
        ui_role_as=ui_role_as,
    )


@pytest.fixture(name="mock_agent_node_cls")
def mock_agent_node_cls_fixture(component_name):
    """Fixture for mocked AgentNode class."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.agent.component.AgentNode"
    ) as mock_cls:
        mock_agent_node = Mock()
        mock_agent_node.name = f"{component_name}#agent"
        mock_cls.return_value = mock_agent_node

        yield mock_cls


@pytest.fixture(name="mock_tool_node_cls")
def mock_tool_node_cls_fixture(component_name):
    """Fixture for mocked ToolNode class."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.agent.component.ToolNode"
    ) as mock_cls:
        mock_tool_node = Mock()
        mock_tool_node.name = f"{component_name}#tools"
        mock_cls.return_value = mock_tool_node

        yield mock_cls


@pytest.fixture(name="mock_final_response_node_cls")
def mock_final_response_node_cls_fixture(component_name):
    """Fixture for mocked FinalResponseNode class."""
    with patch(
        "duo_workflow_service.agent_platform.experimental.components.agent.component.FinalResponseNode"
    ) as mock_cls:
        mock_final_response_node = Mock()
        mock_final_response_node.name = f"{component_name}#final_response"
        mock_cls.return_value = mock_final_response_node

        yield mock_cls


class TestAgentComponentInitialization:
    """Test suite for AgentComponent initialization."""

    @pytest.mark.parametrize(
        ("input_output"),
        [
            "context:user_input",
            "conversation_history:agent_component",
            "status",
            "ui_chat_log",
        ],
    )
    def test_allowed_targets_through_validation(
        self,
        component_name,
        flow_id,
        flow_type,
        prompt_id,
        prompt_version,
        mock_toolset,
        mock_prompt_registry,
        mock_internal_event_client,
        input_output,
    ):
        """Test that component validates input targets correctly."""
        # This should succeed without raising an exception
        AgentComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=[input_output],
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            toolset=mock_toolset,
            tool_arguments_binding=[],
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
        )

    def test_tool_arguments_binding_defaults_to_empty_list(
        self,
        component_name,
        flow_id,
        flow_type,
        prompt_id,
        prompt_version,
        mock_toolset,
        mock_prompt_registry,
        mock_internal_event_client,
    ):
        """Test that tool_arguments_binding defaults to empty list."""
        component = AgentComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=["context:user_input"],
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            toolset=mock_toolset,
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
        )

        assert component.tool_arguments_binding == []

    def test_tool_arguments_binding_calls_parse_keys_and_assigns_result(
        self,
        component_name,
        flow_id,
        flow_type,
        prompt_id,
        prompt_version,
        mock_toolset,
        mock_prompt_registry,
        mock_internal_event_client,
    ):
        """Test that component calls IOKey.parse_keys and assigns the result."""
        binding_config = [
            "context:project_id",
            {"from": "context:branch_name", "as": "ref"},
        ]

        component = AgentComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=["context:user_input"],
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            toolset=mock_toolset,
            tool_arguments_binding=binding_config,
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
        )

        # Verify component stored the parsed IOKey instances
        assert len(component.tool_arguments_binding) == 2
        
        # Verify first binding (simple string format)
        assert isinstance(component.tool_arguments_binding[0], IOKey)
        assert component.tool_arguments_binding[0].target == "context"
        assert component.tool_arguments_binding[0].subkeys == ["project_id"]
        assert component.tool_arguments_binding[0].alias is None
        
        # Verify second binding (dict format with alias)
        assert isinstance(component.tool_arguments_binding[1], IOKey)
        assert component.tool_arguments_binding[1].target == "context"
        assert component.tool_arguments_binding[1].subkeys == ["branch_name"]
        assert component.tool_arguments_binding[1].alias == "ref"

    def test_tool_arguments_binding_not_parsed_when_not_provided(
        self,
        component_name,
        flow_id,
        flow_type,
        prompt_id,
        prompt_version,
        mock_toolset,
        mock_prompt_registry,
        mock_internal_event_client,
    ):
        """Test that tool_arguments_binding defaults to empty list when not provided."""
        component = AgentComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=["context:user_input"],
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            toolset=mock_toolset,
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
        )

        # Verify default empty list for tool_arguments_binding
        assert component.tool_arguments_binding == []


class TestAgentComponentEntryHook:
    """Test suite for AgentComponent entry hook."""

    def test_entry_hook_returns_correct_node_name(
        self, agent_component, component_name
    ):
        """Test that __entry_hook__ returns the correct node name."""
        expected_entry_node = f"{component_name}#agent"
        assert agent_component.__entry_hook__() == expected_entry_node


class TestAgentComponentAttachNodes:
    """Test suite for AgentComponent attach method."""

    @pytest.mark.parametrize(
        ("ui_log_events", "ui_role_as"),
        [
            ([], "agent"),
            # Default values
            ([UILogEventsAgent.ON_AGENT_FINAL_ANSWER], "agent"),
            # Custom events, default role
            ([], "tool"),
            # Default events, custom role
            (
                [
                    UILogEventsAgent.ON_AGENT_FINAL_ANSWER,
                    UILogEventsAgent.ON_TOOL_EXECUTION_SUCCESS,
                ],
                "tool",
            ),
            # Custom values
        ],
    )
    def test_attach_creates_nodes_with_correct_parameters(
        self,
        mock_final_response_node_cls,
        mock_tool_node_cls,
        mock_agent_node_cls,
        agent_component,
        mock_state_graph,
        mock_router,
        component_name,
        flow_id,
        flow_type,
        inputs,
        mock_toolset,
        mock_internal_event_client,
        mock_prompt_registry,
        prompt_id,
        prompt_version,
        ui_log_events,
        ui_role_as,
    ):
        """Test that nodes are created with correct parameters."""
        agent_component.attach(mock_state_graph, mock_router)

        # Verify prompt registry is called with correct parameters
        mock_prompt_registry.get.assert_called_once()
        call_args = mock_prompt_registry.get.call_args

        assert call_args[0][0] == prompt_id
        assert call_args[0][1] == prompt_version

        # Check that tools include both toolset.bindable and AgentFinalOutput
        expected_tools = mock_toolset.bindable + [AgentFinalOutput]
        assert call_args[1]["tools"] == expected_tools
        assert call_args[1]["tool_choice"] == "any"

        # Verify AgentNode creation
        mock_agent_node_cls.assert_called_once()
        agent_call_kwargs = mock_agent_node_cls.call_args[1]
        assert agent_call_kwargs["name"] == f"{component_name}#agent"
        assert agent_call_kwargs["component_name"] == component_name
        assert agent_call_kwargs["prompt"] == mock_prompt_registry.get.return_value
        assert agent_call_kwargs["inputs"] == inputs
        assert agent_call_kwargs["flow_id"] == flow_id
        assert agent_call_kwargs["flow_type"] == flow_type
        assert agent_call_kwargs["internal_event_client"] == mock_internal_event_client

        # Verify ToolNode creation
        mock_tool_node_cls.assert_called_once()
        tool_call_kwargs = mock_tool_node_cls.call_args[1]
        assert tool_call_kwargs["name"] == f"{component_name}#tools"
        assert tool_call_kwargs["component_name"] == component_name
        assert tool_call_kwargs["toolset"] == mock_toolset
        assert tool_call_kwargs["tool_arguments_binding"] == []
        assert tool_call_kwargs["flow_id"] == flow_id
        assert tool_call_kwargs["flow_type"] == flow_type
        assert tool_call_kwargs["internal_event_client"] == mock_internal_event_client

        # Tool Node UI logging
        assert "ui_history" in tool_call_kwargs
        assert isinstance(tool_call_kwargs["ui_history"], UIHistory)
        assert tool_call_kwargs["ui_history"].events == ui_log_events

        # Verify FinalResponseNode creation
        mock_final_response_node_cls.assert_called_once()
        final_call_kwargs = mock_final_response_node_cls.call_args[1]
        assert final_call_kwargs["name"] == f"{component_name}#final_response"
        assert final_call_kwargs["component_name"] == component_name
        assert final_call_kwargs["output"] == IOKey(
            target="context", subkeys=[component_name, "final_answer"]
        )

        # FinalResponse Node UI logging
        assert "ui_history" in final_call_kwargs
        assert isinstance(final_call_kwargs["ui_history"], UIHistory)
        assert final_call_kwargs["ui_history"].events == ui_log_events


class TestAgentComponentAttachEdges:
    """Test suite for AgentComponent routing behavior through graph execution."""

    def test_routing_with_final_tool_call_goes_to_final_response(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        base_flow_state,
        component_name,
        mock_final_tool_call,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that final tool call routes to final response node."""
        # Create state with final tool call
        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_final_tool_call]

        state_with_final_tool = base_flow_state.copy()
        state_with_final_tool[FlowStateKeys.CONVERSATION_HISTORY] = {
            component_name: [mock_message]
        }

        agent_component.attach(mock_state_graph, mock_router)

        # Get the router function that was passed to add_conditional_edges
        router_calls = mock_state_graph.add_conditional_edges.call_args_list
        agent_router_call = next(
            call for call in router_calls if call[0][0] == f"{component_name}#agent"
        )
        router_function = agent_router_call[0][1]

        # Test the routing behavior
        result = router_function(state_with_final_tool)
        expected = f"{component_name}#final_response"
        assert result == expected

    def test_routing_with_other_tool_calls_goes_to_tools(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        base_flow_state,
        component_name,
        mock_other_tool_call,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that non-final tool calls route to tools node."""
        # Create state with other tool call
        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_other_tool_call]

        state_with_other_tool = base_flow_state.copy()
        state_with_other_tool[FlowStateKeys.CONVERSATION_HISTORY] = {
            component_name: [mock_message]
        }

        agent_component.attach(mock_state_graph, mock_router)

        # Get the router function that was passed to add_conditional_edges
        router_calls = mock_state_graph.add_conditional_edges.call_args_list
        agent_router_call = next(
            call for call in router_calls if call[0][0] == f"{component_name}#agent"
        )
        router_function = agent_router_call[0][1]

        # Test the routing behavior
        result = router_function(state_with_other_tool)
        expected = f"{component_name}#tools"
        assert result == expected

    def test_routing_with_mixed_tool_calls_prioritizes_final_response(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        base_flow_state,
        component_name,
        mock_final_tool_call,
        mock_other_tool_call,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that mixed tool calls prioritize final response routing."""
        # Create state with mixed tool calls
        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_other_tool_call, mock_final_tool_call]

        state_with_mixed_tools = base_flow_state.copy()
        state_with_mixed_tools[FlowStateKeys.CONVERSATION_HISTORY] = {
            component_name: [mock_message]
        }

        agent_component.attach(mock_state_graph, mock_router)

        # Get the router function that was passed to add_conditional_edges
        router_calls = mock_state_graph.add_conditional_edges.call_args_list
        agent_router_call = next(
            call for call in router_calls if call[0][0] == f"{component_name}#agent"
        )
        router_function = agent_router_call[0][1]

        # Test the routing behavior
        result = router_function(state_with_mixed_tools)
        expected = f"{component_name}#final_response"
        assert result == expected

    def test_routing_with_without_conversation_history(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        base_flow_state,
        component_name,
        mock_final_tool_call,
        mock_other_tool_call,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that mixed tool calls prioritize final response routing."""
        # Create state with mixed tool calls
        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = [mock_other_tool_call, mock_final_tool_call]

        state_with_mixed_tools = base_flow_state.copy()
        state_with_mixed_tools[FlowStateKeys.CONVERSATION_HISTORY] = {}

        agent_component.attach(mock_state_graph, mock_router)

        # Get the router function that was passed to add_conditional_edges
        router_calls = mock_state_graph.add_conditional_edges.call_args_list
        agent_router_call = next(
            call for call in router_calls if call[0][0] == f"{component_name}#agent"
        )
        router_function = agent_router_call[0][1]

        # Test the routing behavior - should raise RoutingError
        with pytest.raises(
            RoutingError, match=f"Conversation history not found for {component_name}"
        ):
            router_function(base_flow_state)

    def test_routing_with_non_ai_message_raises_error(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        base_flow_state,
        component_name,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that non-AIMessage raises RoutingError."""
        # Create state with non-AIMessage
        mock_message = Mock()  # Not an AIMessage

        state_with_non_ai_message = base_flow_state.copy()
        state_with_non_ai_message[FlowStateKeys.CONVERSATION_HISTORY] = {
            component_name: [mock_message]
        }

        agent_component.attach(mock_state_graph, mock_router)

        # Get the router function that was passed to add_conditional_edges
        router_calls = mock_state_graph.add_conditional_edges.call_args_list
        agent_router_call = next(
            call for call in router_calls if call[0][0] == f"{component_name}#agent"
        )
        router_function = agent_router_call[0][1]

        # Test the routing behavior - should raise RoutingError
        with pytest.raises(
            RoutingError,
            match=f"Last message is not AIMessage for component {component_name}",
        ):
            router_function(state_with_non_ai_message)

    def test_routing_with_no_tool_calls_raises_error(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        base_flow_state,
        component_name,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that messages with no tool calls raise RoutingError."""
        # Create state with AIMessage but no tool calls
        mock_message = Mock(spec=AIMessage)
        mock_message.tool_calls = []

        state_with_no_tools = base_flow_state.copy()
        state_with_no_tools[FlowStateKeys.CONVERSATION_HISTORY] = {
            component_name: [mock_message]
        }

        agent_component.attach(mock_state_graph, mock_router)

        # Get the router function that was passed to add_conditional_edges
        router_calls = mock_state_graph.add_conditional_edges.call_args_list
        agent_router_call = next(
            call for call in router_calls if call[0][0] == f"{component_name}#agent"
        )
        router_function = agent_router_call[0][1]

        # Test the routing behavior - should raise RoutingError
        with pytest.raises(
            RoutingError, match=f"Tool calls not found for component {component_name}"
        ):
            router_function(state_with_no_tools)


class TestAgentComponentModelMetadata:
    """Test suite for AgentComponent model metadata handling."""

    def test_attach_passes_model_metadata_from_context_to_prompt_registry(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        mock_prompt_registry,
        prompt_id,
        prompt_version,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        mock_model_metadata = ModelMetadata(
            name="gpt_5",
            provider="gitlab",
            friendly_name="OpenAI GPT-5",
        )

        metadata_token = current_model_metadata_context.set(mock_model_metadata)

        try:
            agent_component.attach(mock_state_graph, mock_router)

            mock_prompt_registry.get.assert_called_once()
            call_kwargs = mock_prompt_registry.get.call_args[1]

            assert "model_metadata" in call_kwargs
            assert call_kwargs["model_metadata"] == mock_model_metadata
        finally:
            current_model_metadata_context.reset(metadata_token)

    def test_attach_passes_none_when_no_model_metadata_in_context(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        mock_prompt_registry,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
    ):
        metadata_token = current_model_metadata_context.set(None)

        try:
            agent_component.attach(mock_state_graph, mock_router)

            mock_prompt_registry.get.assert_called_once()
            call_kwargs = mock_prompt_registry.get.call_args[1]

            assert "model_metadata" in call_kwargs
            assert call_kwargs["model_metadata"] is None
        finally:
            current_model_metadata_context.reset(metadata_token)


class TestAgentComponentToolArgumentsBinding:
    """Test suite for AgentComponent tool_arguments_binding feature."""

    @pytest.fixture(name="agent_component_with_binding")
    def agent_component_with_binding_fixture(
        self,
        component_name,
        flow_id,
        flow_type,
        prompt_id,
        prompt_version,
        mock_toolset,
        mock_prompt_registry,
        mock_internal_event_client,
    ):
        """Fixture for AgentComponent with tool_arguments_binding."""
        return AgentComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=["context:user_input"],
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            toolset=mock_toolset,
            tool_arguments_binding=[
                "context:project_id",
                {"from": "context:branch_name", "as": "ref"},
            ],
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
        )

    def test_attach_passes_tool_arguments_binding_to_tool_node(
        self,
        component_name,
        flow_id,
        flow_type,
        prompt_id,
        prompt_version,
        mock_toolset,
        mock_prompt_registry,
        mock_internal_event_client,
        mock_state_graph,
        mock_router,
        mock_tool_node_cls,
        mock_agent_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that tool_arguments_binding is passed to ToolNode during attach."""
        binding_config = [
            "context:project_id",
            {"from": "context:branch_name", "as": "ref"},
        ]

        component = AgentComponent(
            name=component_name,
            flow_id=flow_id,
            flow_type=flow_type,
            inputs=["context:user_input"],
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            toolset=mock_toolset,
            tool_arguments_binding=binding_config,
            prompt_registry=mock_prompt_registry,
            internal_event_client=mock_internal_event_client,
        )

        component.attach(mock_state_graph, mock_router)

        # Verify ToolNode was created with the parsed IOKey instances
        mock_tool_node_cls.assert_called_once()
        tool_call_kwargs = mock_tool_node_cls.call_args[1]

        assert "tool_arguments_binding" in tool_call_kwargs
        bindings = tool_call_kwargs["tool_arguments_binding"]
        assert len(bindings) == 2
        
        # Verify the bindings are IOKey instances with correct properties
        assert isinstance(bindings[0], IOKey)
        assert bindings[0].target == "context"
        assert bindings[0].subkeys == ["project_id"]
        
        assert isinstance(bindings[1], IOKey)
        assert bindings[1].target == "context"
        assert bindings[1].subkeys == ["branch_name"]
        assert bindings[1].alias == "ref"

    def test_tool_arguments_binding_empty_list_passed_to_tool_node(
        self,
        agent_component,
        mock_state_graph,
        mock_router,
        mock_tool_node_cls,
        mock_agent_node_cls,
        mock_final_response_node_cls,
    ):
        """Test that empty tool_arguments_binding list is passed to ToolNode."""
        agent_component.attach(mock_state_graph, mock_router)

        # Verify ToolNode was created with empty list
        mock_tool_node_cls.assert_called_once()
        tool_call_kwargs = mock_tool_node_cls.call_args[1]

        assert "tool_arguments_binding" in tool_call_kwargs
        assert tool_call_kwargs["tool_arguments_binding"] == []

    def test_tool_arguments_binding_integration_with_graph_building(
        self,
        agent_component_with_binding,
        mock_state_graph,
        mock_router,
        mock_agent_node_cls,
        mock_tool_node_cls,
        mock_final_response_node_cls,
        component_name,
    ):
        """Test complete integration of tool_arguments_binding in graph building."""
        agent_component_with_binding.attach(mock_state_graph, mock_router)

        # Verify all three nodes were added to the graph
        assert mock_state_graph.add_node.call_count == 3

        # Verify node names
        added_nodes = [call[0][0] for call in mock_state_graph.add_node.call_args_list]
        assert f"{component_name}#agent" in added_nodes
        assert f"{component_name}#tools" in added_nodes
        assert f"{component_name}#final_response" in added_nodes

        # Verify ToolNode received bindings (whatever was stored in component)
        tool_call_kwargs = mock_tool_node_cls.call_args[1]
        # The component's tool_arguments_binding should be passed through
        assert "tool_arguments_binding" in tool_call_kwargs
        assert (
            tool_call_kwargs["tool_arguments_binding"]
            == agent_component_with_binding.tool_arguments_binding
        )
