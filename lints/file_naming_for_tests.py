import os
from pathlib import Path

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

# DO NOT ADD FILES FROM THE ai_gateway MODULE
EXCLUDED_FILES = {
    "tests/test_structured_logging.py",
    "tests/searches/test_search_container.py",
    "tests/code_suggestions/test_instrumentators.py",
    "tests/code_suggestions/test_engine.py",
    "tests/code_suggestions/test_processing.py",
    "tests/code_suggestions/test_logging.py",
    "tests/code_suggestions/test_authentication.py",
    "tests/prompts/test_litellm_prompt.py",
}


class FileNamingForTests(BaseChecker):
    name = "file-naming-for-tests"
    msgs = {
        "W5003": (
            "Test file name does not match the file it is testing.",
            "file-naming-for-tests",
            "Test files must be name to the file they are testing: tests/path/to/test_filename.py must "
            "test path/to/filename.py. See https://docs.gitlab.com/development/python_guide/styleguide/",
        )
    }

    def visit_module(self, node: nodes.Module) -> None:
        # Normalize the file path by removing the workspace root and any leading/trailing slashes
        file_path = node.file.replace(os.getcwd(), "").strip("/")

        # Check if the file should be excluded
        if file_path in EXCLUDED_FILES:
            return

        if not file_path.startswith("tests/") or "test_" not in file_path:
            return

        expected_path = (
            f"ai_gateway/{file_path.replace('tests/', '').replace('test_', '')}"
        )

        if not any(
            Path(f"{source_dir}/{relative_test_path}").is_file()
            for source_dir in SOURCE_DIRS
        ):
            self.add_message(
                "W5003",
                node=node,
            )


def register(linter: "PyLinter") -> None:
    linter.register_checker(FileNamingForTests(linter))
