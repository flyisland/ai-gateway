import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import astroid
import pylint.testutils
import pytest

from lints import file_naming_for_tests


@pytest.fixture
def node():
    node = astroid.extract_node("def test():\n  pass")
    node.file = f"{os.getcwd()}/tests/path/to/test_filename.py"
    return node


class TestFileNamingForTests(pylint.testutils.CheckerTestCase):

    CHECKER_CLASS = file_naming_for_tests.FileNamingForTests

    @patch("lints.file_naming_for_tests.Path")
    def test_valid_test_file(self, mock_path_class, node):
        """Test that a valid test file doesn't trigger the warning."""
        # Create mock instances for the path operations
        mock_test_file_path = MagicMock(spec=Path)
        mock_relative_path = MagicMock(spec=Path)
        mock_relative_path.as_posix.return_value = "tests/path/to/test_filename.py"

        mock_candidate_1 = MagicMock(spec=Path)
        mock_candidate_1.is_file.return_value = False

        mock_candidate_2 = MagicMock(spec=Path)
        mock_candidate_2.is_file.return_value = True

        # Set up the side effects for Path constructor calls
        mock_path_class.side_effect = [
            mock_test_file_path,  # Path(node.file)
            mock_candidate_1,  # Path("ai_gateway/path/to/filename.py")
            mock_candidate_2,  # Path("./path/to/filename.py")
        ]

        # Set up the relative_to method
        mock_test_file_path.relative_to.return_value = mock_relative_path

        with self.assertNoMessages():
            self.checker.visit_module(node)

        # Verify the expected calls were made
        expected_calls = [
            call(f"{os.getcwd()}/tests/path/to/test_filename.py"),  # Initial path
            call("ai_gateway/path/to/filename.py"),  # First candidate
            call("./path/to/filename.py"),  # Second candidate
        ]
        mock_path_class.assert_has_calls(expected_calls)

    @patch("pathlib.Path.is_file")
    def test_invalid_test_file(self, mock_is_file, node):
        """Test that an invalid test file triggers the warning."""

        with self.assertAddsMessages(
            pylint.testutils.MessageTest(
                msg_id="W5003",
                node=node,
            ),
            ignore_position=True,
        ):
            mock_is_file.return_value = False
            self.checker.visit_module(node)

    @patch("pathlib.Path.is_file")
    def test_excluded_file(self, mock_is_file, node):
        """Test that excluded files don't trigger the warning."""
        node.file = f"{os.getcwd()}/tests/test_structured_logging.py"

        with self.assertNoMessages():
            mock_is_file.return_value = False
            self.checker.visit_module(node)

    @patch("pathlib.Path.is_file")
    def test_non_test_file(self, mock_is_file, node):
        """Test that non-test files don't trigger the warning."""

        node.file = f"{os.getcwd()}/ai_gateway/foo.py"

        with self.assertNoMessages():
            mock_is_file.return_value = False
            self.checker.visit_module(node)
