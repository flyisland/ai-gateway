import json
from typing import Any, Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool


class JsonParserInput(BaseModel):
    json_string: str = Field(description="A string containing valid JSON.")


class JsonParser(DuoBaseTool):
    name: str = "json_parser"
    description: str = (
        "Parses a JSON string into a dictionary. Returns an error if the string is not valid JSON."
    )
    args_schema: Type[BaseModel] = JsonParserInput

    async def _arun(self, json_string: str, **kwargs: Any) -> str:
        try:
            parsed_json = json.loads(json_string)
            return json.dumps(parsed_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON string: {str(e)}"})

    def format_display_message(
        self, args: JsonParserInput, _tool_response: Any = None
    ) -> str:
        return "Parsing JSON string"
