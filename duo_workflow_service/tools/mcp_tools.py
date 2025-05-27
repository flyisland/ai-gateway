import json

from langchain.tools import BaseTool, StructuredTool

from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action


def convert_mcp_tools_to_langchain_tools(
    metadata: dict[str, any], tools: list[contract_pb2.McpTool]
) -> dict[str, BaseTool]:
    result = {}

    for tool in tools:

        async def run_tool(
            arguments, tool_name=tool.name
        ):  # Bind tool.name at definition time
            return await _execute_action(
                metadata,  # type: ignore
                contract_pb2.Action(
                    runMCPTool=contract_pb2.RunMCPTool(
                        name=tool_name, args=json.dumps(arguments)
                    )
                ),
            )

        result[tool.name] = StructuredTool.from_function(
            coroutine=run_tool,
            name=tool.name,
            description=tool.description,
            return_direct=False,
        )

    return result
