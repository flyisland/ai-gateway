from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class OperatorEnum(str, Enum):
    """Supported operators for routing evaluation tool input validation."""

    IN = "in"
    NOT_IN = "not_in"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"


class InputRule(BaseModel):
    """Single tool input rule for tool routing validation."""

    model_config = ConfigDict(extra="forbid")

    arg_name: str
    operator: OperatorEnum
    value: Any

    @field_validator("value")
    @classmethod
    def validate_value_for_operator(cls, v, info):
        """Validate that the value type is compatible with the operator."""
        if "operator" not in info.data:
            return v

        operator = info.data["operator"]

        operator_requirements = {
            OperatorEnum.IN: lambda val: isinstance(val, list),
            OperatorEnum.NOT_IN: lambda val: isinstance(val, list),
            OperatorEnum.GREATER_THAN: lambda val: isinstance(val, (int, float))
            and not isinstance(val, bool),
            OperatorEnum.LESS_THAN: lambda val: isinstance(val, (int, float))
            and not isinstance(val, bool),
            OperatorEnum.GREATER_THAN_OR_EQUAL: lambda val: isinstance(
                val, (int, float)
            )
            and not isinstance(val, bool),
            OperatorEnum.LESS_THAN_OR_EQUAL: lambda val: isinstance(val, (int, float))
            and not isinstance(val, bool),
            OperatorEnum.CONTAINS: lambda val: isinstance(val, str),
            OperatorEnum.NOT_CONTAINS: lambda val: isinstance(val, str),
        }

        # Check if operator has requirements
        if operator in operator_requirements:
            validator_func = operator_requirements[operator]
            if not validator_func(v):
                raise ValueError(
                    f"Operator '{operator}' requires a specific value type. "
                    f"Got {type(v).__name__}: {v}. "
                    f"Expected: {cls._get_expected_type_message(operator)}"
                )

        return v

    @staticmethod
    def _get_expected_type_message(operator: OperatorEnum) -> str:
        """Get human-readable expected type message for operator."""
        type_messages = {
            OperatorEnum.IN: "list (e.g., ['a', 'b', 'c'])",
            OperatorEnum.NOT_IN: "list (e.g., ['a', 'b', 'c'])",
            OperatorEnum.GREATER_THAN: "number (int or float)",
            OperatorEnum.LESS_THAN: "number (int or float)",
            OperatorEnum.GREATER_THAN_OR_EQUAL: "number (int or float)",
            OperatorEnum.LESS_THAN_OR_EQUAL: "number (int or float)",
            OperatorEnum.CONTAINS: "string",
            OperatorEnum.NOT_CONTAINS: "string",
        }
        return type_messages.get(operator, "unknown type")


class RoutingEvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_prompt: str
    input_rules: Optional[List[InputRule]] = None
