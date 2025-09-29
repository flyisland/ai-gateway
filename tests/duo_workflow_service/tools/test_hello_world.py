import pytest

from duo_workflow_service.tools.hello_world import HelloWorld, HelloWorldInput


class TestHelloWorld:
    @pytest.fixture
    def hello_world_tool(self):
        return HelloWorld()

    @pytest.mark.asyncio
    async def test_hello_world_default_message(self, hello_world_tool):
        """Test hello_world tool with default message."""
        result = await hello_world_tool._arun()
        assert result == "🎉 Hello, World!"

    @pytest.mark.asyncio
    async def test_hello_world_custom_message(self, hello_world_tool):
        """Test hello_world tool with custom message."""
        custom_message = "Testing the flow!"
        result = await hello_world_tool._arun(message=custom_message)
        assert result == f"🎉 {custom_message}"

    def test_format_display_message(self, hello_world_tool):
        """Test the display message formatting."""
        args = HelloWorldInput(message="Debug test")
        display_message = hello_world_tool.format_display_message(args)
        assert display_message == "Saying hello with message: 'Debug test'"

    def test_format_display_message_default(self, hello_world_tool):
        """Test the display message formatting with default message."""
        args = HelloWorldInput()  # Uses default message
        display_message = hello_world_tool.format_display_message(args)
        assert display_message == "Saying hello with message: 'Hello, World!'"

    def test_tool_properties(self, hello_world_tool):
        """Test that the tool has the correct properties."""
        assert hello_world_tool.name == "hello_world"
        assert "debugging tool" in hello_world_tool.description.lower()
        assert hello_world_tool.args_schema == HelloWorldInput
        assert hello_world_tool.handle_tool_error is True