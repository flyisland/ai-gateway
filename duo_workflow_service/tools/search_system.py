from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action
from duo_workflow_service.tools.filesystem import _format_no_matches_message
from typing import Optional, Type
from pydantic import BaseModel, Field
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class StandardGrepInput(BaseModel):
    search_directory: Optional[str] = Field(
        default=".",
        description="The relative path of directory in which to search. Defaults to current directory.",
    )
    pattern: str = Field(description="The PATTERN to search for")
    case_insensitive: bool = Field(
        default=False,
        description="Ignore case distinctions (equivalent to -i flag)",
    )
    fixed_strings: bool = Field(
        default=False,
        description="Interpret patterns as fixed strings, not regular expressions (equivalent to -F flag)",
    )
    files_with_matches: bool = Field(
        default=False,
        description="Show only filenames that contain matches (equivalent to -l flag)",
    )
    files_without_match: bool = Field(
        default=False,
        description="Show only filenames that don't contain matches (equivalent to -L flag)",
    )


class StandardGrep(DuoBaseTool):
    name: str = "standard_grep"
    description: str = """Search for text patterns in files using the standard grep command.
    This tool uses the standard grep command (NOT git grep) to search through all files, respecting .gitignore rules.

    IMPORTANT: This tool automatically:
    - Includes all files (tracked and untracked)
    - Respects .gitignore rules
    - Searches recursively by default

    Examples:
    - Search for "TODO" in all files: standard_grep(pattern="TODO")
    - Case-insensitive search: standard_grep(pattern="error", case_insensitive=True)
    - Search in specific directory: standard_grep(pattern="bug", search_directory="src/")
    - Fixed string pattern (not regex): standard_grep(pattern="<!-- tags:", fixed_strings=True)
    - Find only filenames with matches: standard_grep(pattern="TODO", files_with_matches=True)
    - Find only filenames without matches: standard_grep(pattern="TODO", files_without_match=True)
    """
    args_schema: Type[BaseModel] = StandardGrepInput  # type: ignore

    async def _arun(
        self,
        pattern: str,
        search_directory: str = ".",
        case_insensitive: bool = False,
        fixed_strings: bool = False,
        files_with_matches: bool = False,
        files_without_match: bool = False,
    ) -> str:
        """
        Execute the standard grep command with the specified parameters.
        """
        if search_directory and ".." in search_directory:
            return "Searching above the current directory is not allowed"

        # Pass the parameters directly to the action
        result = await _execute_action(
            self.metadata,  # type: ignore
            contract_pb2.Action(
                standardGrep=contract_pb2.StandardGrep(
                    pattern=pattern,
                    search_directory=search_directory,
                    case_insensitive=case_insensitive,
                    fixed_strings=fixed_strings,
                    files_with_matches=files_with_matches,
                    files_without_match=files_without_match,
                )
            ),
        )

        if "No such file or directory" in result or "exit status 1" in result:
            return _format_no_matches_message(pattern, search_directory)

        return result

    def format_display_message(self, args: StandardGrepInput) -> str:
        message = f"Search for '{args.pattern}' in files in '{args.search_directory}'"
        return message
