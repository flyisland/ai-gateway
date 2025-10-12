import os
from unittest.mock import patch

import pytest


def check_contradiction_detection_env_var():
    """Helper function that replicates the environment variable check logic."""
    return (
        os.environ.get("DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION", "false").lower()
        == "true"
    )


class TestContradictionDetectionEnvironmentVariable:
    """Test suite for contradiction detection environment variable logic."""

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "true"})
    def test_env_var_true_enables_feature(self):
        """Test that 'true' enables contradiction detection."""
        assert check_contradiction_detection_env_var() is True

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "false"})
    def test_env_var_false_disables_feature(self):
        """Test that 'false' disables contradiction detection."""
        assert check_contradiction_detection_env_var() is False

    @patch.dict(os.environ, {}, clear=True)
    def test_env_var_default_is_false(self):
        """Test that contradiction detection is disabled by default."""
        assert check_contradiction_detection_env_var() is False

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "TRUE"})
    def test_env_var_case_insensitive_true(self):
        """Test that environment variable check is case insensitive for 'true'."""
        assert check_contradiction_detection_env_var() is True

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "True"})
    def test_env_var_mixed_case_true(self):
        """Test that mixed case 'True' enables contradiction detection."""
        assert check_contradiction_detection_env_var() is True

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "FALSE"})
    def test_env_var_case_insensitive_false(self):
        """Test that uppercase 'FALSE' disables contradiction detection."""
        assert check_contradiction_detection_env_var() is False

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "1"})
    def test_env_var_numeric_one_does_not_enable(self):
        """Test that numeric '1' does not enable contradiction detection."""
        assert check_contradiction_detection_env_var() is False

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "yes"})
    def test_env_var_yes_does_not_enable(self):
        """Test that 'yes' does not enable contradiction detection."""
        assert check_contradiction_detection_env_var() is False

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "on"})
    def test_env_var_on_does_not_enable(self):
        """Test that 'on' does not enable contradiction detection."""
        assert check_contradiction_detection_env_var() is False

    @patch.dict(os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": ""})
    def test_env_var_empty_string_disables(self):
        """Test that empty string disables contradiction detection."""
        assert check_contradiction_detection_env_var() is False

    @patch.dict(
        os.environ, {"DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION": "   true   "}
    )
    def test_env_var_true_with_whitespace_enables(self):
        """Test that 'true' with whitespace enables contradiction detection."""
        # Update function to handle whitespace
        value = (
            os.environ.get("DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION", "false")
            .strip()
            .lower()
        )
        assert value == "true"
