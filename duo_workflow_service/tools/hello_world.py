from typing import Any, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class HelloWorldInput(BaseModel):
    message: str = Field(
        default="Hello, World!",
        description="The message to return. Defaults to 'Hello, World!'"
    )


class HelloWorld(DuoBaseTool):
    name: str = "hello_world"
    description: str = """A simple debugging tool that returns a greeting message.
    
    This tool is designed for testing and debugging flows. It simply returns
    the provided message or a default "Hello, World!" greeting.
    
    Use this tool to:
    - Test that tools are working correctly in a flow
    - Debug flow execution and tool calling
    - Verify agent-tool communication
    """
    args_schema: Type[BaseModel] = HelloWorldInput  # type: ignore
    handle_tool_error: bool = True

    async def _arun(self, message: str = "Hello, World!") -> str:
        """Return the provided message or default greeting."""
        return f"🎉 {message}"

    def format_display_message(
        self, args: HelloWorldInput, _tool_response: Any = None
    ) -> str:
        return f"Saying hello with message: '{args.message}'"