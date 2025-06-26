import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain.tools import BaseTool

from contract import contract_pb2
from duo_workflow_service.tools.additional_tools import (
    AdditionalTool,
    convert_additional_tools_to_langchain_tools,
)


@pytest.mark.asyncio
async def test_convert_additional_tools_to_langchain_tools():
    metadata = {"outbox": AsyncMock()}
    additional_tools = [
        contract_pb2.Tool(
            name="tool1",
            source="tool-source",
            description="Tool 1 description",
            inputSchema="{}",
        ),
        contract_pb2.Tool(
            name="tool2",
            source="tool-source",
            description="Tool 2 description",
            inputSchema='{"properties":{}}',
        ),
    ]
    with patch(
        "duo_workflow_service.tools.additional_tools._execute_action",
        new_callable=AsyncMock,
    ) as mock_execute_action:
        mock_execute_action.return_value = "Tool execution result"
        result = convert_additional_tools_to_langchain_tools(metadata, additional_tools)

        assert len(result) == 2
        assert all(isinstance(tool, AdditionalTool) for tool in result)
        assert all(isinstance(tool, BaseTool) for tool in result)

        assert result[0].name == "tool1"
        assert result[0].description == "Tool 1 description"
        assert result[0].metadata == metadata
        assert result[0].source == "tool-source"
        assert result[0].args_schema == {}

        assert result[1].name == "tool2"
        assert result[1].description == "Tool 2 description"
        assert result[1].source == "tool-source"
        assert result[1].metadata == metadata
        assert result[1].args_schema == {"properties": {}}

        test_args = {"arg1": "value1"}
        execution_result = await result[0]._arun(**test_args)
        assert execution_result == "Tool execution result"

        mock_execute_action.assert_called_once_with(
            metadata,
            contract_pb2.Action(
                runTool=contract_pb2.RunTool(name="tool1", args=json.dumps(test_args))
            ),
        )


@pytest.mark.asyncio
async def test_additional_tool_run_method():
    tool = AdditionalTool(name="test_tool", description="Test tool", metadata={})

    with pytest.raises(
        NotImplementedError, match="This tool can only be run asynchronously"
    ):
        tool._run()


@pytest.mark.asyncio
async def test_additional_tool_arun_without_metadata():
    tool = AdditionalTool(name="test_tool", description="Test tool", metadata=None)

    with pytest.raises(RuntimeError, match="metadata is not set"):
        await tool._arun(arg1="value1")


@pytest.mark.asyncio
async def test_additional_tool_format_display_message():
    tool = AdditionalTool(name="test_tool", description="Test tool", metadata={})
    arguments = {"key": "value"}

    message = tool.format_display_message(arguments)
    assert message == "Run tool test_tool: {'key': 'value'}"


@pytest.mark.asyncio
async def test_convert_additional_tools_with_invalid_json():
    metadata = {"outbox": AsyncMock()}
    additional_tools = [
        contract_pb2.Tool(
            name="tool1", description="Tool 1 description", inputSchema="invalid json"
        ),
    ]

    result = convert_additional_tools_to_langchain_tools(metadata, additional_tools)

    assert len(result) == 1
    assert isinstance(result[0], AdditionalTool)
    assert result[0].name == "tool1"
    assert result[0].description == "Tool 1 description"
    assert result[0].args_schema == {}  # Should default to empty dict for invalid JSON
