"""
Constants for SAST False Positive Detection Workflow.

This module contains all constants, enums, and configuration values
used throughout the SAST false positive detection workflow.
"""

from enum import StrEnum

# Agent name
AGENT_NAME = "sast_analyzer_agent"

# Tool names used by the SAST analyzer
GET_VULNERABILITY_TOOL = "get_vulnerability"
READ_FILE_TOOL = "read_file"
CREATE_FILE_TOOL = "create_file_with_contents"
FIND_FILES_TOOL = "find_files"

# Analysis tools list (agent tools - excludes get_vulnerability since it's called deterministically)
ANALYSIS_TOOLS = [READ_FILE_TOOL, CREATE_FILE_TOOL, FIND_FILES_TOOL]


class Routes(StrEnum):
    """Workflow routing decisions."""

    CONTINUE = "continue"
    END = "end"
    AGENT = "agent" 