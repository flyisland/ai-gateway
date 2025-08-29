import json
from typing import Any, Literal, Optional, Type

from pydantic import BaseModel, Field

from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class RunTestsInput(BaseModel):
    language: Literal["go", "python", "npm"] = Field(
        description="The language/framework of the test to run."
    )
    args: Optional[str] = Field(
        default="./...", description="Optional arguments to pass to the test runner."
    )


class RunTests(DuoBaseTool):
    name: str = "run_tests"
    description: str = (
        "Runs the test suite for a given language. This is the only tool that can execute tests."
    )
    args_schema: Type[BaseModel] = RunTestsInput

    async def _arun(
        self,
        language: Literal["go", "python", "npm"],
        args: str = "./...",
        **kwargs: Any,
    ) -> str:
        program = ""
        command_args = ""

        if language == "go":
            program = "go"
            command_args = f"test {args}"
        elif language == "python":
            program = "pytest"
            command_args = args
        elif language == "npm":
            program = "npm"
            command_args = f"test -- {args}"
        else:
            return json.dumps(
                {"error": f"Unsupported language for testing: {language}"}
            )

        return await _execute_action(
            self.metadata,  # type: ignore
            contract_pb2.Action(
                runCommand=contract_pb2.RunCommandAction(
                    program=program,
                    arguments=command_args.split(),
                    flags=[],
                )
            ),
        )

    def format_display_message(
        self, args: RunTestsInput, _tool_response: Any = None
    ) -> str:
        return f"Running {args.language} tests with arguments: {args.args}"
