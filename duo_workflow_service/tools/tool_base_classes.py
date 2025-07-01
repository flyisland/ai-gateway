import json
from abc import abstractmethod
from typing import Any, Set

from duo_workflow_service.security.prompt_security import (
    PromptSecurity,
    SecurityException,
)
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

# Fields that are safe and don't need security validation
SAFE_FIELDS: Set[str] = {
    "error",
    "id",
    "iid",
    "project_id",
    "group_id",
    "epic_id",
    "epic_iid",
    "created_at",
    "updated_at",
    "status_code",
    "timestamp",
    "note_id",
    "author_id",
    "parent_id",
}


class ReadOperationTool(DuoBaseTool):
    """Base class for tools that READ/FETCH data - automatically applies security validation"""

    async def _arun(self, **kwargs: Any) -> str:
        """FINAL method that enforces security. DO NOT OVERRIDE. Implement _execute instead."""
        # Get the raw response from tool implementation
        raw_response = await self._execute(**kwargs)

        # Apply security validation
        try:
            result_dict = json.loads(raw_response)

            # If there's an error, return as-is
            if "error" in result_dict:
                return raw_response

            # Apply security to all fields except safe ones
            secured_dict = {}
            for key, value in result_dict.items():
                if key in SAFE_FIELDS:
                    secured_dict[key] = value
                else:
                    try:
                        secured_dict[key] = PromptSecurity.apply_security(
                            value, self.name
                        )
                    except SecurityException as e:
                        return json.dumps({"error": str(e)})

            return json.dumps(secured_dict)

        except json.JSONDecodeError:
            # If not JSON, return as-is
            return raw_response
        except Exception as e:
            return json.dumps({"error": f"Security validation error: {str(e)}"})

    @abstractmethod
    async def _execute(self, **kwargs: Any) -> str:
        """Implement your tool logic here. Return JSON string."""
        pass


class WriteOperationTool(DuoBaseTool):
    """Base class for tools that WRITE data - no security validation needed"""

    pass
