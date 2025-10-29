#!/usr/bin/env python3
"""Script to sync foundational agents from GitLab AI Catalog.

Usage:
    python fetch_foundational_agents.py <gitlab_url> <gitlab_token> <foundational_agent_ids> [--output-path <path>]

Arguments:
    gitlab_url: GitLab GraphQL API URL (e.g., http://gdk.test:3000/api/graphql)
    gitlab_token: GitLab API token for authentication
    foundational_agent_ids: Comma-separated list of foundational agent IDs (e.g., "348,349,350")
    --output-path: Optional directory path to save YAML files. If not provided, prints to stdout.
"""

import argparse
import os
import sys

import yaml
from requests import request

OPERATION_NAME = "aiCatalogAgent"
FETCH_AGENT_QUERY = """
query aiCatalogAgent($id: AiCatalogItemID!) {
    aiCatalogItem(id: $id) {
        createdAt
        itemType
        description
        name
        latestVersion {
            ...BaseAiCatalogAgentVersion
        }
    }
}

fragment BaseAiCatalogAgentVersion on AiCatalogAgentVersion {
    versionName
    systemPrompt
    tools {
        nodes {
            name
        }
    }
}
"""


def graphql_request(url, token, query, variables=None):
    """Make a GraphQL request to the GitLab API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {
        "query": query,
        "variables": variables,
        "operationName": OPERATION_NAME,
    }

    response = request("POST", url, headers=headers, json=data, timeout=30)
    response.raise_for_status()
    return response.json()


def create_workflow_definition(agent_data):
    """Create a workflow definition from agent data."""
    agent_name = agent_data["name"]
    agent_id = agent_name.lower().replace(" ", "_")
    prompt_id = f"{agent_id}_prompt"
    system_prompt = agent_data["latestVersion"]["systemPrompt"]
    toolset = [t["name"] for t in agent_data["latestVersion"]["tools"]["nodes"]]

    workflow_def = {
        "version": "v1",
        "environment": "chat-partial",
        "components": [
            {
                "name": agent_id,
                "type": "AgentComponent",
                "prompt_id": prompt_id,
                "inputs": [
                    {"from": "context:goal", "as": "goal"},
                    {"from": "context:project_id", "as": "project_id"},
                ],
                "toolset": toolset,
                "ui_log_events": [],
            }
        ],
        "prompts": [
            {
                "name": agent_name,
                "prompt_id": prompt_id,
                "model": {
                    "params": {"model_class_provider": "anthropic", "max_tokens": 2000}
                },
                "prompt_template": {
                    "system": system_prompt,
                    "user": "{{goal}}",
                    "placeholder": "history",
                },
            }
        ],
        "routers": [],
        "flow": {"entry_point": agent_id},
        "_metadata": {"agent_id": agent_id},
    }

    return workflow_def


def fetch_foundational_agent(gitlab_url, gitlab_token, agent_id):
    """Sync a single foundational agent and return its workflow definition."""
    variables = {"id": f"gid://gitlab/Ai::Catalog::Item/{agent_id}"}

    response = graphql_request(
        f"{gitlab_url.rstrip('/')}/api/graphql",
        gitlab_token,
        FETCH_AGENT_QUERY,
        variables,
    )

    if "errors" in response:
        raise RuntimeError(response["errors"])

    agent_data = response["data"]["aiCatalogItem"]
    return create_workflow_definition(agent_data)


def save_workflow_to_file(workflow_def, output_path):
    """Save a workflow definition to a YAML file."""
    # Remove metadata before saving
    metadata = workflow_def.pop("_metadata", {})
    agent_id = metadata["agent_id"]

    filename = f"{agent_id}.yml"
    filepath = os.path.join(output_path, filename)

    with open(filepath, "w") as f:
        yaml.dump(workflow_def, f, default_flow_style=False, sort_keys=False)
    return filepath


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Sync foundational agents from GitLab AI Catalog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("gitlab_url", help="GitLab GraphQL API URL")
    parser.add_argument("gitlab_token", help="GitLab API token")
    parser.add_argument(
        "foundational_agent_ids", help="Comma-separated list of agent IDs"
    )
    parser.add_argument(
        "--output-path",
        help="Directory path to save YAML files. If not provided, prints to stdout.",
    )

    return parser.parse_args()


def fetch_agents():
    """Main function to parse arguments and sync foundational agents."""
    args = parse_arguments()

    # Parse agent IDs
    try:
        agent_ids = [int(id.strip()) for id in args.foundational_agent_ids.split(",")]
    except ValueError:
        print(
            "Error: foundational_agent_ids must be comma-separated integers",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate output path if provided
    if args.output_path:
        if not os.path.exists(args.output_path):
            raise ValueError(
                f"Output path does not exist: {args.output_path}",
            )

    workflow_definitions = [
        fetch_foundational_agent(args.gitlab_url, args.gitlab_token, agent_id)
        for agent_id in agent_ids
    ]

    if args.output_path:
        # Save to file
        saved_files = [
            save_workflow_to_file(workflow_def, args.output_path)
            for workflow_def in workflow_definitions
        ]

        print(
            f"Successfully saved {len(saved_files)} workflow definition(s)",
            file=sys.stderr,
        )
    else:
        for workflow_def in workflow_definitions:
            print("-----")
            print(yaml.dump(workflow_def, default_flow_style=False, sort_keys=False))
