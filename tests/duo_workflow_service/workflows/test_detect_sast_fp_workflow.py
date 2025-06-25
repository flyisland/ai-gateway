"""Tests for the SAST False Positive Detection Workflow."""

import pytest
from unittest.mock import MagicMock

from duo_workflow_service.entities import WorkflowState, WorkflowStatusEnum
from duo_workflow_service.internal_events.event_enum import CategoryEnum
from duo_workflow_service.workflows.detect_sast_fp.workflow import Workflow


class TestDetectSastFpWorkflow:
    """Test cases for the SAST False Positive Detection Workflow."""

    @pytest.fixture
    def workflow(self):
        """Create a workflow instance for testing."""
        return Workflow(
            workflow_id="test-workflow-id",
            workflow_metadata={},
            workflow_type=CategoryEnum.WORKFLOW_DETECT_SAST_FP,
            context_elements=[],
            invocation_metadata={
                "base_url": "https://gitlab.example.com",
                "gitlab_token": "test-token",
            },
        )

    def test_workflow_type(self, workflow):
        """Test that the workflow has the correct type."""
        assert workflow._workflow_type == CategoryEnum.WORKFLOW_DETECT_SAST_FP

    def test_get_workflow_state_with_vulnerability_id(self, workflow):
        """Test that the workflow state is created correctly with a vulnerability ID."""
        vulnerability_id = "gid://gitlab/Vulnerability/123"
        state = workflow.get_workflow_state(vulnerability_id)

        assert isinstance(state, dict)
        assert state["status"] == WorkflowStatusEnum.NOT_STARTED
        assert len(state["ui_chat_log"]) == 1
        assert (
            "vulnerability ID: gid://gitlab/Vulnerability/123"
            in state["ui_chat_log"][0]["content"]
        )

    def test_get_workflow_state_with_empty_input(self, workflow):
        """Test that the workflow state handles empty input gracefully."""
        state = workflow.get_workflow_state("")

        assert isinstance(state, dict)
        assert state["status"] == WorkflowStatusEnum.NOT_STARTED
        assert len(state["ui_chat_log"]) == 1
        assert "vulnerability ID: Unknown" in state["ui_chat_log"][0]["content"]

    def test_parse_vulnerability_id_valid(self, workflow):
        """Test parsing a valid vulnerability ID."""
        from duo_workflow_service.workflows.detect_sast_fp.workflow import (
            _parse_vulnerability_id,
        )

        vulnerability_id = "gid://gitlab/Vulnerability/123"
        result = _parse_vulnerability_id(vulnerability_id)
        assert result == vulnerability_id

    def test_parse_vulnerability_id_empty(self, workflow):
        """Test parsing an empty vulnerability ID raises an error."""
        from duo_workflow_service.workflows.detect_sast_fp.workflow import (
            _parse_vulnerability_id,
        )

        with pytest.raises(RuntimeError, match="No vulnerability ID provided"):
            _parse_vulnerability_id("")

    def test_parse_vulnerability_id_none(self, workflow):
        """Test parsing a None vulnerability ID raises an error."""
        from duo_workflow_service.workflows.detect_sast_fp.workflow import (
            _parse_vulnerability_id,
        )

        with pytest.raises(RuntimeError, match="No vulnerability ID provided"):
            _parse_vulnerability_id(None)

    def test_extract_vulnerability_id_valid(self, workflow):
        """Test extracting a valid vulnerability ID for logging."""
        from duo_workflow_service.workflows.detect_sast_fp.workflow import (
            _extract_vulnerability_id,
        )

        vulnerability_id = "gid://gitlab/Vulnerability/123"
        result = _extract_vulnerability_id(vulnerability_id)
        assert result == vulnerability_id

    def test_extract_vulnerability_id_empty(self, workflow):
        """Test extracting an empty vulnerability ID returns Unknown."""
        from duo_workflow_service.workflows.detect_sast_fp.workflow import (
            _extract_vulnerability_id,
        )

        result = _extract_vulnerability_id("")
        assert result == "Unknown"

    def test_analysis_tools_include_get_vulnerability(self, workflow):
        """Test that the analysis tools include the required tools for the agent."""
        from duo_workflow_service.workflows.detect_sast_fp.workflow import (
            ANALYSIS_TOOLS,
        )

        # get_vulnerability is no longer in ANALYSIS_TOOLS since it's used deterministically
        assert "read_file" in ANALYSIS_TOOLS
        assert "create_file_with_contents" in ANALYSIS_TOOLS
        assert "find_files" in ANALYSIS_TOOLS
        # Verify get_vulnerability is not in agent tools (it's used deterministically)
        assert "get_vulnerability" not in ANALYSIS_TOOLS
