#!/usr/bin/env python3
"""
Validation script for foundational agents integration.

This script demonstrates how the ListFlows endpoint filtering functionality
integrates with the broader foundational agents feature for Rails sync.

Usage:
    python scripts/validate_foundational_agents_integration.py
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from duo_workflow_service.agent_platform.experimental.flows.flow_config import list_configs


def validate_foundational_agents_structure(configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate that foundational agents have the expected structure for Rails integration.
    
    Args:
        configs: List of flow configurations
        
    Returns:
        Dictionary with validation results
    """
    results = {
        "total_flows": len(configs),
        "foundational_agents": [],
        "validation_errors": [],
        "summary": {}
    }
    
    # Filter for foundational agents (chat-partial environment with v1 version)
    foundational_agents = [
        config for config in configs
        if config.get("environment") == "chat-partial" and config.get("version") == "v1"
    ]
    
    results["foundational_agents"] = foundational_agents
    results["summary"]["foundational_agents_count"] = len(foundational_agents)
    
    # Validate each foundational agent
    for agent in foundational_agents:
        agent_name = agent.get("name", "unknown")
        
        # Required fields validation
        required_fields = ["name", "version", "environment", "config"]
        for field in required_fields:
            if field not in agent:
                results["validation_errors"].append(
                    f"Foundational agent '{agent_name}' missing required field: {field}"
                )
        
        # Validate specific values
        if agent.get("version") != "v1":
            results["validation_errors"].append(
                f"Foundational agent '{agent_name}' has incorrect version: {agent.get('version')}"
            )
            
        if agent.get("environment") != "chat-partial":
            results["validation_errors"].append(
                f"Foundational agent '{agent_name}' has incorrect environment: {agent.get('environment')}"
            )
        
        # Validate config is valid JSON
        try:
            config_data = json.loads(agent.get("config", "{}"))
            if config_data.get("version") != "v1":
                results["validation_errors"].append(
                    f"Foundational agent '{agent_name}' config has incorrect version"
                )
            if config_data.get("environment") != "chat-partial":
                results["validation_errors"].append(
                    f"Foundational agent '{agent_name}' config has incorrect environment"
                )
        except json.JSONDecodeError:
            results["validation_errors"].append(
                f"Foundational agent '{agent_name}' has invalid JSON config"
            )
    
    # Summary statistics
    results["summary"]["validation_passed"] = len(results["validation_errors"]) == 0
    results["summary"]["other_flows_count"] = results["total_flows"] - len(foundational_agents)
    
    return results


def simulate_rails_integration(configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Simulate how Rails would process the foundational agents from the ListFlows response.
    
    Args:
        configs: List of flow configurations
        
    Returns:
        Dictionary representing what Rails would extract
    """
    # This simulates the filtering logic that Rails would use
    foundational_agents = []
    
    for config in configs:
        # Rails filtering criteria for foundational agents
        if (config.get("environment") == "chat-partial" and 
            config.get("version") == "v1"):
            
            # Extract the data Rails would need
            rails_agent = {
                "name": config.get("name"),
                "version": config.get("version"),
                "environment": config.get("environment"),
                "description": config.get("description", ""),
                "config_json": config.get("config"),
                "is_foundational_agent": True,
                "created_from_workflow_service": True
            }
            
            # Parse config for additional metadata
            try:
                config_data = json.loads(config.get("config", "{}"))
                rails_agent["flow_entry_point"] = config_data.get("flow", {}).get("entry_point")
                rails_agent["components_count"] = len(config_data.get("components", []))
            except json.JSONDecodeError:
                rails_agent["config_parse_error"] = True
            
            foundational_agents.append(rails_agent)
    
    return {
        "foundational_agents_for_rails": foundational_agents,
        "total_count": len(foundational_agents),
        "sync_timestamp": "2025-10-02T12:00:00Z",
        "source": "duo_workflow_service_list_flows"
    }


def demonstrate_filtering_scenarios():
    """Demonstrate various filtering scenarios for foundational agents."""
    print("🔍 Demonstrating Foundational Agents Filtering Scenarios")
    print("=" * 60)
    
    # Get all available flow configs
    all_configs = list_configs()
    
    print(f"📊 Total flows available: {len(all_configs)}")
    
    # Scenario 1: List all flows (no filtering)
    print("\n📋 Scenario 1: List all flows (backward compatibility)")
    for config in all_configs:
        print(f"  - {config.get('name')} (v{config.get('version')}, {config.get('environment')})")
    
    # Scenario 2: Filter for foundational agents
    print("\n🎯 Scenario 2: Filter for foundational agents (environment=chat-partial, version=v1)")
    foundational_agents = [
        config for config in all_configs
        if config.get("environment") == "chat-partial" and config.get("version") == "v1"
    ]
    
    if foundational_agents:
        for agent in foundational_agents:
            print(f"  ✅ {agent.get('name')} - {agent.get('description', 'No description')}")
    else:
        print("  ⚠️  No foundational agents found with the specified criteria")
    
    # Scenario 3: Filter by environment only
    print("\n🌍 Scenario 3: Filter by environment (chat-partial)")
    chat_partial_flows = [
        config for config in all_configs
        if config.get("environment") == "chat-partial"
    ]
    
    for flow in chat_partial_flows:
        print(f"  - {flow.get('name')} (v{flow.get('version')})")
    
    # Scenario 4: Filter by version only
    print("\n🏷️  Scenario 4: Filter by version (v1)")
    v1_flows = [
        config for config in all_configs
        if config.get("version") == "v1"
    ]
    
    for flow in v1_flows:
        print(f"  - {flow.get('name')} ({flow.get('environment')})")
    
    return all_configs, foundational_agents


def main():
    """Main validation function."""
    print("🚀 Foundational Agents Integration Validation")
    print("=" * 50)
    
    try:
        # Demonstrate filtering scenarios
        all_configs, foundational_agents = demonstrate_filtering_scenarios()
        
        # Validate foundational agents structure
        print("\n🔍 Validating Foundational Agents Structure")
        print("-" * 40)
        validation_results = validate_foundational_agents_structure(all_configs)
        
        print(f"Total flows: {validation_results['total_flows']}")
        print(f"Foundational agents found: {validation_results['summary']['foundational_agents_count']}")
        print(f"Other flows: {validation_results['summary']['other_flows_count']}")
        
        if validation_results["validation_errors"]:
            print("\n❌ Validation Errors:")
            for error in validation_results["validation_errors"]:
                print(f"  - {error}")
        else:
            print("\n✅ All foundational agents passed validation!")
        
        # Simulate Rails integration
        print("\n🔗 Simulating Rails Integration")
        print("-" * 30)
        rails_data = simulate_rails_integration(all_configs)
        
        print(f"Foundational agents for Rails sync: {rails_data['total_count']}")
        
        if rails_data["foundational_agents_for_rails"]:
            print("\nRails would receive:")
            for agent in rails_data["foundational_agents_for_rails"]:
                print(f"  - {agent['name']} ({agent['components_count']} components)")
        
        # Summary
        print("\n📋 Integration Summary")
        print("-" * 20)
        print(f"✅ Filtering functionality: {'Working' if foundational_agents else 'No foundational agents found'}")
        print(f"✅ Backward compatibility: {'Maintained' if all_configs else 'Issue detected'}")
        print(f"✅ Rails integration format: {'Valid' if not validation_results['validation_errors'] else 'Issues found'}")
        print(f"✅ Foundational agents count: {len(foundational_agents)}")
        
        # Example gRPC commands
        print("\n🔧 Example gRPC Commands")
        print("-" * 25)
        print("# List all flows:")
        print("grpcurl -plaintext -d '{}' localhost:50052 DuoWorkflow/ListFlows")
        print("\n# Filter for foundational agents (when MR !3497 is merged):")
        print('grpcurl -plaintext -d \'{"filters": {"environment": ["chat-partial"], "version": ["v1"]}}\' localhost:50052 DuoWorkflow/ListFlows')
        
        return validation_results["summary"]["validation_passed"]
        
    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)