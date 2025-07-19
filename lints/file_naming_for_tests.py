import os
from pathlib import Path

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

# DO NOT ADD FILES FROM THE ai_gateway MODULE
EXCLUDED_FILES = {
    "tests/test_structured_logging.py",
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
        """Validate that a test file name matches the file it is testing.

        A *unit-test* file must follow this naming convention::

            tests/path/to/test_<filename>.py  ->  path/to/<filename>.py

        Additionally, historical tests may target files in the ``ai_gateway``
        package, so we also consider that folder when looking for the matching
        source file.  The checker therefore builds two candidate paths and
        deems the test valid as soon as **any** of them exists on disk.
        """
        # Make the incoming path relative to the repository root.
        file_path = Path(node.file).relative_to(os.getcwd()).as_posix()

        # Early-return for excluded or plainly irrelevant files.
        if file_path in EXCLUDED_FILES:
            return
        if not file_path.startswith("tests/") or "test_" not in file_path:
            return

        # Strip the leading ``tests/`` segment and ``test_`` prefix to obtain the
        # candidate source filename e.g. ``path/to/filename.py``.
        relative_test_path = file_path.replace("tests/", "", 1).replace("test_", "", 1)

        # Compose candidate locations – one inside *ai_gateway* (legacy) and one
        # relative to the repo root (current).
        candidate_paths = [
            f"ai_gateway/{relative_test_path}",
            f"./{relative_test_path}",
        ]

        # If **none** of the candidates exists, emit a warning.
        if not any(Path(p).is_file() for p in candidate_paths):
            self.add_message("W5003", node=node)


def register(linter: "PyLinter") -> None:
    linter.register_checker(FileNamingForTests(linter))
