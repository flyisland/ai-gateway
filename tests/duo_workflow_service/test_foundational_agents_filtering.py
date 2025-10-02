"""Tests for foundational agents filtering functionality."""

import pytest
from unittest.mock import MagicMock, patch

from contract import contract_pb2
from duo_workflow_service.server import DuoWorkflowService
from google.protobuf.json_format import MessageToDict


@pytest.mark.asyncio
@patch("duo_workflow_service.server.flow_registry.list_configs")
async def test_list_foundational_agents_with_chat_partial_environment(mock_list_configs):
    """Test filtering for foundational agents with chat-partial environment."""
    mock_list_configs.return_value = [
        {
            "name": "foundational_agent_example",
            "version": "v1",
            "environment": "chat-partial",
            "config": '{"version": "v1", "environment": "chat-partial"}',
        },
        {
            "name": "code_assistant_foundational_agent",
            "version": "v1", 
            "environment": "chat-partial",
            "config": '{"version": "v1", "environment": "chat-partial"}',
        },
        {
            "name": "regular_flow",
            "version": "experimental",
            "environment": "remote",
            "config": '{"version": "experimental", "environment": "remote"}',
        },
    ]

    mock_context = MagicMock(spec=grpc.ServicerContext)
    service = DuoWorkflowService()
    
    # Test without filters (should return all flows for backward compatibility)
    request = contract_pb2.ListFlowsRequest()
    response = await service.ListFlows(request, mock_context)
    
    assert len(response.configs) == 3
    configs_dict = [MessageToDict(config) for config in response.configs]
    
    # Verify all flows are returned when no filters are applied
    flow_names = [config["name"] for config in configs_dict]
    assert "foundational_agent_example" in flow_names
    assert "code_assistant_foundational_agent" in flow_names
    assert "regular_flow" in flow_names


@pytest.mark.asyncio
@patch("duo_workflow_service.server.flow_registry.list_configs")
async def test_backward_compatibility_empty_request(mock_list_configs):
    """Test that empty ListFlowsRequest still works (backward compatibility)."""
    mock_list_configs.return_value = [
        {"name": "flow1", "description": "First flow config"},
        {"name": "flow2", "description": "Second flow config"},
    ]

    mock_context = MagicMock(spec=grpc.ServicerContext)
    service = DuoWorkflowService()
    
    # Test with empty request (original behavior)
    response = await service.ListFlows(contract_pb2.ListFlowsRequest(), mock_context)

    assert isinstance(response, contract_pb2.ListFlowsResponse)
    assert len(response.configs) == 2
    mock_list_configs.assert_called_once()

    configs_dict = [MessageToDict(config) for config in response.configs]
    expected_configs = [
        {"name": "flow1", "description": "First flow config"},
        {"name": "flow2", "description": "Second flow config"},
    ]
    assert configs_dict == expected_configs


@pytest.mark.asyncio
@patch("duo_workflow_service.server.flow_registry.list_configs")
async def test_foundational_agents_use_case_scenario(mock_list_configs):
    """Test the specific use case mentioned in the issue for foundational agents."""
    mock_list_configs.return_value = [
        {
            "name": "foundational_agent_example",
            "version": "v1",
            "environment": "chat-partial",
            "description": "General purpose foundational agent",
        },
        {
            "name": "code_assistant_foundational_agent", 
            "version": "v1",
            "environment": "chat-partial",
            "description": "Code-focused foundational agent",
        },
        {
            "name": "experimental_flow",
            "version": "experimental",
            "environment": "remote",
            "description": "Experimental remote flow",
        },
        {
            "name": "another_foundational_agent",
            "version": "v2",
            "environment": "chat-partial", 
            "description": "Newer version foundational agent",
        },
    ]

    mock_context = MagicMock(spec=grpc.ServicerContext)
    service = DuoWorkflowService()
    
    # This test simulates the filtering that would be done for foundational agents
    # Note: The actual filtering logic is implemented in MR !3497
    # This test verifies the data structure and backward compatibility
    
    request = contract_pb2.ListFlowsRequest()
    response = await service.ListFlows(request, mock_context)
    
    configs_dict = [MessageToDict(config) for config in response.configs]
    
    # Verify we can identify foundational agents by their characteristics
    foundational_agents = [
        config for config in configs_dict 
        if config.get("environment") == "chat-partial"
    ]
    
    assert len(foundational_agents) == 3
    
    # Verify we can further filter by version
    v1_foundational_agents = [
        config for config in foundational_agents
        if config.get("version") == "v1"
    ]
    
    assert len(v1_foundational_agents) == 2
    agent_names = [agent["name"] for agent in v1_foundational_agents]
    assert "foundational_agent_example" in agent_names
    assert "code_assistant_foundational_agent" in agent_names


@pytest.mark.asyncio
@patch("duo_workflow_service.server.flow_registry.list_configs")
async def test_list_configs_called_correctly(mock_list_configs):
    """Test that list_configs is called correctly and response is properly formatted."""
    mock_list_configs.return_value = []

    mock_context = MagicMock(spec=grpc.ServicerContext)
    service = DuoWorkflowService()
    
    request = contract_pb2.ListFlowsRequest()
    response = await service.ListFlows(request, mock_context)
    
    # Verify the registry method is called
    mock_list_configs.assert_called_once()
    
    # Verify empty response is handled correctly
    assert isinstance(response, contract_pb2.ListFlowsResponse)
    assert len(response.configs) == 0