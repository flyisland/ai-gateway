import json
from typing import Any

from langchain.tools import BaseTool

from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action


class AdditionalTool(BaseTool):
    source: str | None = None

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("This tool can only be run asynchronously")

    async def _arun(self, **arguments):
        if self.metadata is None:
            raise RuntimeError("metadata is not set")

        return await _execute_action(
            self.metadata,
            contract_pb2.Action(
                runTool=contract_pb2.RunTool(name=self.name, args=json.dumps(arguments))
            ),
        )

    def format_display_message(self, arguments) -> str:
        return f"Run tool {self.name}: {arguments}"


def convert_additional_tools_to_langchain_tools(
    metadata: dict[str, Any], tools: list[contract_pb2.Tool]
) -> list[BaseTool]:
    result: list[BaseTool] = []

    for tool in tools:
        try:
            args_schema = json.loads(tool.inputSchema)
        except json.JSONDecodeError:
            args_schema = {}

        additional_tool = AdditionalTool(
            name=tool.name,
            description=tool.description,
            metadata=metadata,
            args_schema=args_schema,
        )
        additional_tool.source = tool.source
        result.append(additional_tool)

    return result
