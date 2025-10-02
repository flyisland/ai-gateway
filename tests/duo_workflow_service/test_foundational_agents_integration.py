"""Integration tests for foundational agents filtering with specific criteria from issue #1530."""

import pytest
from unittest.mock import MagicMock, patch

from contract import contract_pb2
from duo_workflow_service.server import DuoWorkflowService
from google.protobuf.json_format import MessageToDict


class TestFoundationalAgentsIntegration:
    """Integration tests for foundational agents filtering functionality."""

    @pytest.fixture
    def sample_flows_data(self):
        """Sample flow data that includes foundational agents and other flows."""
        return [
            # Foundational agents (custom agent flows with chat-partial environment)
            {
                "name": "foundational_agent_example",
                "version": "v1",
                "environment": "chat-partial",
                "description": "General purpose foundational agent",
                "config": '{"version": "v1", "environment": "chat-partial", "components": [{"type": "AgentComponent"}]}',
            },
            {
                "name": "code_assistant_foundational_agent",
                "version": "v1", 
                "environment": "chat-partial",
                "description": "Code-focused foundational agent",
                "config": '{"version": "v1", "environment": "chat-partial", "components": [{"type": "AgentComponent"}]}',
            },
            # Non-foundational flows
            {
                "name": "code_review",
                "version": "experimental",
                "environment": "remote",
                "description": "Code review workflow",
                "config": '{"version": "experimental", "environment": "remote"}',
            },
            {
                "name": "fix_pipeline",
                "version": "experimental", 
                "environment": "remote",
                "description": "Pipeline fixing workflow",
                "config": '{"version": "experimental", "environment": "remote"}',
            },
            # Edge cases
            {
                "name": "chat_partial_v2",
                "version": "v2",
                "environment": "chat-partial",
                "description": "Newer version foundational agent",
                "config": '{"version": "v2", "environment": "chat-partial"}',
            },
            {
                "name": "v1_remote_flow",
                "version": "v1",
                "environment": "remote", 
                "description": "V1 flow but not chat-partial",
                "config": '{"version": "v1", "environment": "remote"}',
            },
        ]

    @pytest.mark.asyncio
    @patch("duo_workflow_service.server.flow_registry.list_configs")
    async def test_foundational_agents_filtering_criteria(self, mock_list_configs, sample_flows_data):
        """Test filtering with the exact criteria mentioned in issue #1530."""
        mock_list_configs.return_value = sample_flows_data

        mock_context = MagicMock(spec=grpc.ServicerContext)
        service = DuoWorkflowService()
        
        # Test the basic ListFlows functionality (no filtering)
        request = contract_pb2.ListFlowsRequest()
        response = await service.ListFlows(request, mock_context)
        
        configs_dict = [MessageToDict(config) for config in response.configs]
        
        # Verify all flows are returned
        assert len(configs_dict) == 6
        
        # Simulate the filtering that would be applied for foundational agents
        # Filter for: environment='chat-partial' AND version='v1'
        foundational_agents = [
            config for config in configs_dict
            if config.get("environment") == "chat-partial" and config.get("version") == "v1"
        ]
        
        # Should match exactly 2 foundational agents
        assert len(foundational_agents) == 2
        
        agent_names = {agent["name"] for agent in foundational_agents}
        expected_names = {"foundational_agent_example", "code_assistant_foundational_agent"}
        assert agent_names == expected_names
        
        # Verify they all have the correct characteristics
        for agent in foundational_agents:
            assert agent["environment"] == "chat-partial"
            assert agent["version"] == "v1"
            assert "foundational" in agent["name"] or "agent" in agent["name"]

    @pytest.mark.asyncio
    @patch("duo_workflow_service.server.flow_registry.list_configs")
    async def test_foundational_agents_sync_with_rails_scenario(self, mock_list_configs, sample_flows_data):
        """Test the scenario where Rails would sync foundational agents from the workflow service."""
        mock_list_configs.return_value = sample_flows_data

        mock_context = MagicMock(spec=grpc.ServicerContext)
        service = DuoWorkflowService()
        
        request = contract_pb2.ListFlowsRequest()
        response = await service.ListFlows(request, mock_context)
        
        configs_dict = [MessageToDict(config) for config in response.configs]
        
        # Simulate Rails filtering for foundational agents
        # This would be the filtering logic that Rails would apply
        def is_foundational_agent(flow_config):
            """Determine if a flow config represents a foundational agent."""
            return (
                flow_config.get("environment") == "chat-partial" and
                flow_config.get("version") == "v1" and
                ("agent" in flow_config.get("name", "").lower() or 
                 "foundational" in flow_config.get("name", "").lower())
            )
        
        foundational_agents = [
            config for config in configs_dict
            if is_foundational_agent(config)
        ]
        
        # Verify the expected foundational agents are identified
        assert len(foundational_agents) == 2
        
        # Verify each foundational agent has the required structure for Rails integration
        for agent in foundational_agents:
            assert "name" in agent
            assert "version" in agent
            assert "environment" in agent
            assert "config" in agent
            assert agent["environment"] == "chat-partial"
            assert agent["version"] == "v1"

    @pytest.mark.asyncio
    @patch("duo_workflow_service.server.flow_registry.list_configs")
    async def test_filtering_edge_cases(self, mock_list_configs, sample_flows_data):
        """Test edge cases for foundational agents filtering."""
        mock_list_configs.return_value = sample_flows_data

        mock_context = MagicMock(spec=grpc.ServicerContext)
        service = DuoWorkflowService()
        
        request = contract_pb2.ListFlowsRequest()
        response = await service.ListFlows(request, mock_context)
        
        configs_dict = [MessageToDict(config) for config in response.configs]
        
        # Test filtering by environment only
        chat_partial_flows = [
            config for config in configs_dict
            if config.get("environment") == "chat-partial"
        ]
        assert len(chat_partial_flows) == 3  # v1 and v2 versions
        
        # Test filtering by version only
        v1_flows = [
            config for config in configs_dict
            if config.get("version") == "v1"
        ]
        assert len(v1_flows) == 3  # chat-partial and remote environments
        
        # Test filtering by both (foundational agents)
        foundational_agents = [
            config for config in configs_dict
            if config.get("environment") == "chat-partial" and config.get("version") == "v1"
        ]
        assert len(foundational_agents) == 2

    @pytest.mark.asyncio
    @patch("duo_workflow_service.server.flow_registry.list_configs")
    async def test_empty_results_scenario(self, mock_list_configs):
        """Test scenario where no foundational agents exist."""
        # Mock data with no foundational agents
        mock_list_configs.return_value = [
            {
                "name": "regular_flow",
                "version": "experimental",
                "environment": "remote",
                "description": "Regular workflow",
            }
        ]

        mock_context = MagicMock(spec=grpc.ServicerContext)
        service = DuoWorkflowService()
        
        request = contract_pb2.ListFlowsRequest()
        response = await service.ListFlows(request, mock_context)
        
        configs_dict = [MessageToDict(config) for config in response.configs]
        
        # Simulate filtering for foundational agents
        foundational_agents = [
            config for config in configs_dict
            if config.get("environment") == "chat-partial" and config.get("version") == "v1"
        ]
        
        # Should return empty list when no foundational agents exist
        assert len(foundational_agents) == 0
        
        # But original response should still contain the regular flow
        assert len(configs_dict) == 1
        assert configs_dict[0]["name"] == "regular_flow"

    @pytest.mark.asyncio
    @patch("duo_workflow_service.server.flow_registry.list_configs")
    async def test_foundational_agents_config_structure(self, mock_list_configs, sample_flows_data):
        """Test that foundational agents have the expected configuration structure."""
        mock_list_configs.return_value = sample_flows_data

        mock_context = MagicMock(spec=grpc.ServicerContext)
        service = DuoWorkflowService()
        
        request = contract_pb2.ListFlowsRequest()
        response = await service.ListFlows(request, mock_context)
        
        configs_dict = [MessageToDict(config) for config in response.configs]
        
        # Filter for foundational agents
        foundational_agents = [
            config for config in configs_dict
            if config.get("environment") == "chat-partial" and config.get("version") == "v1"
        ]
        
        # Verify each foundational agent has the expected structure
        for agent in foundational_agents:
            # Required fields for foundational agents
            assert "name" in agent
            assert "version" in agent
            assert "environment" in agent
            assert "config" in agent
            
            # Specific values for foundational agents
            assert agent["version"] == "v1"
            assert agent["environment"] == "chat-partial"
            
            # Config should be valid JSON string
            import json
            config_data = json.loads(agent["config"])
            assert config_data["version"] == "v1"
            assert config_data["environment"] == "chat-partial"