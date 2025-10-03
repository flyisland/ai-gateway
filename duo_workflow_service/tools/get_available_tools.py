import json
from typing import Any

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class GetAvailableTools(DuoBaseTool):
    name: str = "get_available_tools"
    description: str = """Get the list of available tools to a new agent, including the id and the description of each tool

    For example:
        get_available_tools()
    """

    async def _arun(self, **kwargs: Any) -> str:
        from duo_workflow_service.components import tools_registry

        tools = [tool for tool in tools_registry.ALL_TOOLS]
        return json.dumps(
            {
                "tools": [
                    {"name": tool.name, "description": tool.description}
                    for tool in tools
                ]
            }
        )

    def format_display_message(self, _, _tool_response: Any = None) -> str:
        return f"Getting list of tools that the agent can use"
