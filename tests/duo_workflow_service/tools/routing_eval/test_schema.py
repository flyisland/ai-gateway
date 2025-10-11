from typing import Any

import pytest
from pydantic import ValidationError

from duo_workflow_service.tools.routing_eval.schema import (
    InputRule,
    OperatorEnum,
    RoutingEvalConfig,
)


@pytest.mark.parametrize(
    "operator,value,should_raise,error_message",
    [
        (OperatorEnum.IN, [1, 2, 3], False, None),
        (OperatorEnum.NOT_IN, ["a", "b"], False, None),
        (OperatorEnum.GREATER_THAN, 0, False, None),
        (OperatorEnum.LESS_THAN, -1, False, None),
        (OperatorEnum.GREATER_THAN_OR_EQUAL, 3.14, False, None),
        (OperatorEnum.LESS_THAN_OR_EQUAL, 1_000_000, False, None),
        (OperatorEnum.CONTAINS, "", False, None),
        (OperatorEnum.NOT_CONTAINS, "needle", False, None),
        (OperatorEnum.IN, "not-a-list", True, "Expected: list (e.g., ['a', 'b', 'c'])"),
        (
            OperatorEnum.NOT_IN,
            {"not": "a list"},
            True,
            "Expected: list (e.g., ['a', 'b', 'c'])",
        ),
        (OperatorEnum.GREATER_THAN, True, True, "Expected: number (int or float)"),
        (OperatorEnum.LESS_THAN, False, True, "Expected: number (int or float)"),
        (
            OperatorEnum.GREATER_THAN_OR_EQUAL,
            "5",
            True,
            "Expected: number (int or float)",
        ),
        (
            OperatorEnum.LESS_THAN_OR_EQUAL,
            None,
            True,
            "Expected: number (int or float)",
        ),
        (OperatorEnum.CONTAINS, ["not", "a", "string"], True, "Expected: string"),
        (OperatorEnum.NOT_CONTAINS, 123, True, "Expected: string"),
        (OperatorEnum.CONTAINS, None, True, "Expected: string"),
    ],
)
def test_operators_value_validation(
    operator: OperatorEnum, value: Any, should_raise: bool, error_message: str
):
    if should_raise:
        with pytest.raises(ValidationError) as exc:
            InputRule(arg_name="arg1", operator=operator, value=value)
        assert error_message in str(exc.value)
    else:
        r = InputRule(arg_name="arg1", operator=operator, value=value)
        assert r.value == value


@pytest.mark.parametrize(
    "model_class,kwargs",
    [
        (
            InputRule,
            {
                "arg_name": "arg1",
                "operator": OperatorEnum.EQUALS,
                "value": 1,
                "extra_field": 123,
            },
        ),
        (
            InputRule,
            {
                "arg_name": "arg1",
                "operator": OperatorEnum.EQUALS,
                "value": 1,
                "unexpected": True,
            },
        ),
        (
            RoutingEvalConfig,
            {"user_prompt": "Hi there", "input_rules": [], "unexpected": True},
        ),
    ],
)
def test_extra_fields_forbidden(model_class, kwargs):
    with pytest.raises(ValidationError):
        model_class(**kwargs)


def test_operator_enum_values_unique_and_stringy():
    values = [e.value for e in OperatorEnum]
    assert len(values) == len(set(values))
    assert all(isinstance(v, str) for v in values)
