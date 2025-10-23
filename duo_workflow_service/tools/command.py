import re
import shlex
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

_DISALLOWED_COMMANDS = ["git"]
_DISALLOWED_OPERATORS = ["&&", "||"]


class RunCommandInput(BaseModel):
    program: str = Field(description="The name of bash program to execute eg: 'cp'")
    args: Optional[str] = Field(
        description="All arguments and flags for the bash program as a single string. "
        "eg: '-v -p source.txt destination.txt'",
        default=None,
    )


class RunCommand(DuoBaseTool):
    name: str = "run_command"
    description: str = (
        "Run a bash command in the current working directory. "
        "This tool should be reserved for cases where specialized tools cannot accomplish the task. "
        f"Following bash commands are not supported: {', '.join(_DISALLOWED_COMMANDS)} "
        "and will result in error. "
        "Pay extra attention to correctly escape special characters like '`'"
    )
    args_schema: Type[BaseModel] = RunCommandInput  # type: ignore

    def _detect_shell_operators(self, args: str) -> bool:
        """Detect if shell operators are present in the arguments."""
        # Operators that require shell execution
        # Removed &> as it's bash-specific and we want to be more conservative
        shell_operators = [r"\|", r">", r">>", r"<", r"2>", r";"]

        # Build regex pattern: operator with word boundary before or after, or at string start/end
        # This reduces (but doesn't eliminate) false positives from filenames
        pattern = r"(?:^|\s)(?:" + "|".join(shell_operators) + r")(?:\s|$)"

        return bool(re.search(pattern, args))

    async def _execute(
        self,
        program: str,
        args: Optional[str] = None,
    ) -> str:
        args = args or ""

        for disallowed_operator in _DISALLOWED_OPERATORS:
            if disallowed_operator in program or disallowed_operator in args:
                # pylint: disable=line-too-long
                return f"""
                    '{disallowed_operator}' operators are not supported with {self.name} tool.
                    Instead of '{disallowed_operator}' please use {self.name} multiple times
                    consecutively to emulate '{disallowed_operator}' behaviour.
                    """

        for disallowed_command in _DISALLOWED_COMMANDS:
            if program.startswith(disallowed_command):
                return f"{disallowed_command} commands are not supported with {self.name} tool."

        # Detect shell operators that require bash execution
        needs_shell = self._detect_shell_operators(args)

        if needs_shell:
            # Use sh -c for maximum portability across environments
            # All operators we support (|, >, <, >>, 2>, ;) are POSIX-compliant
            # sh is guaranteed to exist in minimal containers, CI/CD environments, and all Unix-like systems
            full_command = f"{program} {args}"
            return await _execute_action(
                self.metadata,  # type: ignore
                contract_pb2.Action(
                    runCommand=contract_pb2.RunCommandAction(
                        program="sh",
                        arguments=["-c", full_command],
                        flags=[],
                    )
                ),
            )

        # Direct execution (existing behavior for commands without shell operators)
        # Use shlex.split() to correctly handle quoted arguments.
        try:
            arguments = shlex.split(args)
        except ValueError as e:
            return f"Invalid command arguments: {str(e)}. Check for unclosed quotes or malformed input."

        return await _execute_action(
            self.metadata,  # type: ignore
            contract_pb2.Action(
                runCommand=contract_pb2.RunCommandAction(
                    program=program,
                    arguments=arguments,
                    flags=[],
                )
            ),
        )

    def format_display_message(
        self, args: RunCommandInput, _tool_response: Any = None
    ) -> str:
        command = f"{args.program} {args.args}".strip()
        return f"Run command: {command}"
