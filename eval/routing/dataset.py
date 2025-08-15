from itertools import chain
from typing import List

import structlog
from joblib import Memory
from langchain_core.utils.function_calling import convert_to_openai_tool
from langsmith.schemas import ExampleCreate

from duo_workflow_service.components import tools_registry
from duo_workflow_service.tools import DuoBaseTool
from eval.routing.constants import (
    DEFAULT_LS_DATASET_INPUTS_SCHEMA,
    DEFAULT_LS_DATASET_OUTPUTS_SCHEMA,
    LS_CLIENT,
)

logger = structlog.get_logger(__name__)

# Create cache directory
memory = Memory(location="./tmp/cache", verbose=0)


def get_available_tools() -> List[DuoBaseTool]:
    tools = set(
        (
            tools_registry._DEFAULT_TOOLS
            + tools_registry._READ_ONLY_GITLAB_TOOLS
            + list(chain.from_iterable(tools_registry._AGENT_PRIVILEGES.values()))
        )
    )
    sorted_tools = sorted(tools, key=lambda tool_class: tool_class.__name__)
    return [tool_class() for tool_class in sorted_tools]  # type: ignore[misc]


def create_ls_dataset(dataset_name: str):
    LS_CLIENT.create_dataset(
        dataset_name=dataset_name,
        inputs_schema=DEFAULT_LS_DATASET_INPUTS_SCHEMA,
        outputs_schema=DEFAULT_LS_DATASET_OUTPUTS_SCHEMA,
    )


def create_ls_examples_from_tool_specs(
    tools: List[DuoBaseTool], split: str = "codebase"
) -> List[ExampleCreate]:
    logger.info("Generate examples from tool specs from codebase...")
    tools_openai_json = [convert_to_openai_tool(tool) for tool in tools]
    examples = []
    for tool in tools:
        for prompt in tool.eval_prompts or []:
            example = ExampleCreate(
                inputs={
                    "tools": tools_openai_json,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant!",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                outputs={"tool": convert_to_openai_tool(tool)},
                split=split,
                metadata={"tool_name": tool.name, "prompt": prompt},
            )
            examples.append(example)
    return examples


@memory.cache
def generate_dataset(dataset_name: str, tools: List[DuoBaseTool]):
    if LS_CLIENT.has_dataset(dataset_name=dataset_name):
        logger.info(
            f"Dataset: {dataset_name} already exists, removing current examples."
        )
        old_examples = LS_CLIENT.list_examples(dataset_name=dataset_name)
        LS_CLIENT.delete_examples(example_ids=[example.id for example in old_examples])
    else:
        logger.info(f"Dataset: {dataset_name} not found, creating new dataset...")
        create_ls_dataset(dataset_name=dataset_name)

    logger.info("Adding dataset examples...")
    new_examples = create_ls_examples_from_tool_specs(tools=tools)
    response = LS_CLIENT.create_examples(
        dataset_name=dataset_name, examples=new_examples
    )
    logger.info(f"Uploaded dataset with {response.get("count")} examples.")
