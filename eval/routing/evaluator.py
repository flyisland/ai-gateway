from typing import Dict

from langsmith.evaluation import EvaluationResult
from langsmith.schemas import Example, Run

from eval.routing.constants import CHAT


async def execute_routing(inputs: Dict):
    llm = CHAT.bind_tools(inputs["tools"])
    return llm.invoke(inputs["messages"])


def is_correct(run: Run, example: Example) -> EvaluationResult:
    output_dict = run.outputs or {}
    expected_dict = example.outputs or {}
    is_pass = (
        output_dict["tool_calls"][-1]["name"]
        == expected_dict["tool"]["function"]["name"]
    )
    return EvaluationResult(
        key="is_correct",
        score=1.0 if is_pass else 0.0,
    )
