import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import pytest
import yaml
from requests import HTTPError

from duo_workflow_service.scripts.fetch_foundational_agents import (
    FETCH_AGENT_QUERY,
    OPERATION_NAME,
    create_workflow_definition,
    fetch_agents,
    fetch_foundational_agent,
    graphql_request,
    parse_arguments,
    save_workflow_to_file,
)


class TestGraphQLRequest:
    """Test cases for graphql_request function."""

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.request")
    def test_successful_request(self, mock_request):
        """Test successful GraphQL request."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"test": "value"}}
        mock_request.return_value = mock_response

        result = graphql_request(
            "http://test.com/graphql", "test-token", "query { test }", {"var": "value"}
        )

        assert result == {"data": {"test": "value"}}
        mock_request.assert_called_once_with(
            "POST",
            "http://test.com/graphql",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
            json={
                "query": "query { test }",
                "variables": {"var": "value"},
                "operationName": OPERATION_NAME,
            },
            timeout=30,
        )

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.request")
    def test_request_with_no_variables(self, mock_request):
        """Test GraphQL request without variables."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"test": "value"}}
        mock_request.return_value = mock_response

        graphql_request("http://test.com/graphql", "test-token", "query { test }")

        mock_request.assert_called_once_with(
            "POST",
            "http://test.com/graphql",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
            json={
                "query": "query { test }",
                "variables": None,
                "operationName": OPERATION_NAME,
            },
            timeout=30,
        )

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.request")
    def test_request_raises_http_error(self, mock_request):
        """Test GraphQL request that raises HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = HTTPError("HTTP 404")
        mock_request.return_value = mock_response

        with pytest.raises(HTTPError):
            graphql_request("http://test.com/graphql", "test-token", "query { test }")


class TestCreateWorkflowDefinition:
    """Test cases for create_workflow_definition function."""

    def test_create_workflow_definition_with_mock_data(self):
        """Test workflow definition creation with the provided mock data."""
        agent_data = {
            "name": "Test Agent",
            "latestVersion": {
                "systemPrompt": "Test prompt",
                "tools": {"nodes": [{"name": "create_epic"}]},
            },
        }

        result = create_workflow_definition(agent_data)

        expected = {
            "version": "v1",
            "environment": "chat-partial",
            "components": [
                {
                    "name": "test_agent",
                    "type": "AgentComponent",
                    "prompt_id": "test_agent_prompt",
                    "inputs": [
                        {"from": "context:goal", "as": "goal"},
                        {"from": "context:project_id", "as": "project_id"},
                    ],
                    "toolset": ["create_epic"],
                    "ui_log_events": [],
                }
            ],
            "prompts": [
                {
                    "name": "Test Agent",
                    "prompt_id": "test_agent_prompt",
                    "model": {
                        "params": {
                            "model_class_provider": "anthropic",
                            "max_tokens": 2000,
                        }
                    },
                    "prompt_template": {
                        "system": "Test prompt",
                        "user": "{{goal}}",
                        "placeholder": "history",
                    },
                }
            ],
            "routers": [],
            "flow": {"entry_point": "test_agent"},
            "_metadata": {"agent_id": "test_agent"},
        }

        assert result == expected

    def test_create_workflow_definition_with_multiple_tools(self):
        """Test workflow definition creation with multiple tools."""
        agent_data = {
            "name": "Multi Tool Agent",
            "latestVersion": {
                "systemPrompt": "Test system prompt",
                "tools": {
                    "nodes": [
                        {"name": "create_epic"},
                        {"name": "create_issue"},
                        {"name": "update_merge_request"},
                    ]
                },
            },
        }

        result = create_workflow_definition(agent_data)

        assert result["components"][0]["toolset"] == [
            "create_epic",
            "create_issue",
            "update_merge_request",
        ]
        assert result["components"][0]["name"] == "multi_tool_agent"
        assert result["prompts"][0]["prompt_id"] == "multi_tool_agent_prompt"

    def test_create_workflow_definition_with_no_tools(self):
        """Test workflow definition creation with no tools."""
        agent_data = {
            "name": "Simple Agent",
            "latestVersion": {
                "systemPrompt": "Test system prompt",
                "tools": {"nodes": []},
            },
        }

        result = create_workflow_definition(agent_data)

        assert result["components"][0]["toolset"] == []

    def test_name_normalization(self):
        """Test that agent names are properly normalized to IDs."""
        test_cases = [
            ("Simple Name", "simple_name"),
            ("Complex Agent Name", "complex_agent_name"),
            ("Agent-With-Dashes", "agent-with-dashes"),
            ("Agent_With_Underscores", "agent_with_underscores"),
            ("MixedCaseAgent", "mixedcaseagent"),
        ]

        for name, expected_id in test_cases:
            agent_data = {
                "name": name,
                "latestVersion": {
                    "systemPrompt": "Test prompt",
                    "tools": {"nodes": []},
                },
            }
            result = create_workflow_definition(agent_data)
            assert result["components"][0]["name"] == expected_id
            assert result["flow"]["entry_point"] == expected_id
            assert result["_metadata"]["agent_id"] == expected_id


class TestFetchFoundationalAgent:
    """Test cases for fetch_foundational_agent function."""

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.graphql_request")
    def test_successful_fetch(self, mock_graphql_request):
        """Test successful agent fetch."""
        mock_response = {
            "data": {
                "aiCatalogItem": {
                    "createdAt": "2025-09-30T13:08:41Z",
                    "itemType": "AGENT",
                    "description": "An AI agent that transforms regular text into authentic pirate speak",
                    "name": "Pirate Translator",
                    "latestVersion": {
                        "versionName": "1.0.0",
                        "systemPrompt": "You are a seasoned pirate from the Golden Age of Piracy.",
                        "tools": {"nodes": [{"name": "create_epic"}]},
                    },
                }
            }
        }
        mock_graphql_request.return_value = mock_response

        result = fetch_foundational_agent("http://test.com", "token", 123)

        mock_graphql_request.assert_called_once_with(
            "http://test.com/api/graphql",
            "token",
            FETCH_AGENT_QUERY,
            {"id": "gid://gitlab/Ai::Catalog::Item/123"},
        )

        assert result["components"][0]["name"] == "pirate_translator"
        assert result["_metadata"]["agent_id"] == "pirate_translator"

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.graphql_request")
    def test_fetch_with_trailing_slash_url(self, mock_graphql_request):
        """Test agent fetch with URL that has trailing slash."""
        mock_response = {
            "data": {
                "aiCatalogItem": {
                    "name": "Test Agent",
                    "latestVersion": {
                        "systemPrompt": "Test prompt",
                        "tools": {"nodes": []},
                    },
                }
            }
        }
        mock_graphql_request.return_value = mock_response

        fetch_foundational_agent("http://test.com/", "token", 123)

        # Should strip trailing slash
        mock_graphql_request.assert_called_once_with(
            "http://test.com/api/graphql",
            "token",
            FETCH_AGENT_QUERY,
            {"id": "gid://gitlab/Ai::Catalog::Item/123"},
        )

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.graphql_request")
    def test_fetch_with_graphql_errors(self, mock_graphql_request):
        """Test agent fetch when GraphQL returns errors."""
        mock_response = {"errors": [{"message": "Agent not found"}]}
        mock_graphql_request.return_value = mock_response

        with pytest.raises(RuntimeError) as exc_info:
            fetch_foundational_agent("http://test.com", "token", 123)

        assert exc_info.value.args[0] == [{"message": "Agent not found"}]


class TestSaveWorkflowToFile:
    """Test cases for save_workflow_to_file function."""

    def test_save_workflow_to_file(self):
        """Test saving workflow definition to file."""
        workflow_def = {
            "version": "v1",
            "components": [{"name": "test_agent"}],
            "_metadata": {"agent_id": "test_agent"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            filepath = save_workflow_to_file(workflow_def, temp_dir)

            expected_filepath = os.path.join(temp_dir, "test_agent.yml")
            assert filepath == expected_filepath
            assert os.path.exists(filepath)

            # Verify file contents
            with open(filepath, "r") as f:
                saved_content = yaml.safe_load(f)

            # Metadata should be removed from saved content
            expected_content = {"version": "v1", "components": [{"name": "test_agent"}]}
            assert saved_content == expected_content


class TestParseArguments:
    """Test cases for parse_arguments function."""

    def test_parse_required_arguments(self):
        """Test parsing with only required arguments."""
        test_args = ["http://test.com/graphql", "test-token", "123,456,789"]

        with patch("sys.argv", ["script.py"] + test_args):
            args = parse_arguments()

        assert args.gitlab_url == "http://test.com/graphql"
        assert args.gitlab_token == "test-token"
        assert args.foundational_agent_ids == "123,456,789"
        assert args.output_path is None

    def test_parse_with_output_path(self):
        """Test parsing with optional output path."""
        test_args = [
            "http://test.com/graphql",
            "test-token",
            "123,456,789",
            "--output-path",
            "/tmp/output",
        ]

        with patch("sys.argv", ["script.py"] + test_args):
            args = parse_arguments()

        assert args.gitlab_url == "http://test.com/graphql"
        assert args.gitlab_token == "test-token"
        assert args.foundational_agent_ids == "123,456,789"
        assert args.output_path == "/tmp/output"


class TestFetchAgents:
    """Test cases for fetch_agents main function."""

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.parse_arguments")
    @patch(
        "duo_workflow_service.scripts.fetch_foundational_agents.fetch_foundational_agent"
    )
    @patch("builtins.print")
    def test_fetch_agents_stdout_output(
        self, mock_print, mock_fetch_agent, mock_parse_args
    ):
        """Test fetch_agents with stdout output (no output path)."""
        # Mock arguments
        mock_args = Mock()
        mock_args.gitlab_url = "http://test.com"
        mock_args.gitlab_token = "token"
        mock_args.foundational_agent_ids = "123,456"
        mock_args.output_path = None
        mock_parse_args.return_value = mock_args

        # Mock workflow definitions
        workflow1 = {"name": "agent1", "_metadata": {"agent_id": "agent1"}}
        workflow2 = {"name": "agent2", "_metadata": {"agent_id": "agent2"}}
        mock_fetch_agent.side_effect = [workflow1, workflow2]

        fetch_agents()

        # Verify fetch_foundational_agent was called for each ID
        assert mock_fetch_agent.call_count == 2
        mock_fetch_agent.assert_any_call("http://test.com", "token", 123)
        mock_fetch_agent.assert_any_call("http://test.com", "token", 456)

        # Verify output to stdout - should print separator and YAML for each workflow
        expected_calls = [
            unittest.mock.call("-----"),
            unittest.mock.call(
                yaml.dump(workflow1, default_flow_style=False, sort_keys=False)
            ),
            unittest.mock.call("-----"),
            unittest.mock.call(
                yaml.dump(workflow2, default_flow_style=False, sort_keys=False)
            ),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("duo_workflow_service.scripts.fetch_foundational_agents.parse_arguments")
    @patch(
        "duo_workflow_service.scripts.fetch_foundational_agents.fetch_foundational_agent"
    )
    @patch(
        "duo_workflow_service.scripts.fetch_foundational_agents.save_workflow_to_file"
    )
    @patch("builtins.print")
    @patch("os.path.exists")
    def test_fetch_agents_file_output(
        self,
        mock_exists,
        mock_print,
        mock_save_workflow,
        mock_fetch_agent,
        mock_parse_args,
    ):
        """Test fetch_agents with file output."""
        # Mock arguments
        mock_args = Mock()
        mock_args.gitlab_url = "http://test.com"
        mock_args.gitlab_token = "token"
        mock_args.foundational_agent_ids = "123"
        mock_args.output_path = "/tmp/output"
        mock_parse_args.return_value = mock_args

        # Mock path exists
        mock_exists.return_value = True

        # Mock workflow definition
        workflow = {"name": "agent1", "_metadata": {"agent_id": "agent1"}}
        mock_fetch_agent.return_value = workflow
        mock_save_workflow.return_value = "/tmp/output/agent1.yml"

        fetch_agents()

        # Verify save_workflow_to_file was called
        mock_save_workflow.assert_called_once_with(workflow, "/tmp/output")

        # Verify success message printed to stderr
        mock_print.assert_called_once_with(
            "Successfully saved 1 workflow definition(s)", file=sys.stderr
        )
