import argparse
import asyncio
import sys
import textwrap
from itertools import chain
from typing import Any, Dict, List, Tuple

import structlog
from dotenv import load_dotenv
from joblib import Memory
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import convert_to_messages
from langsmith import Client
from langsmith.schemas import Example as LSExample
from pydantic import BaseModel

from duo_workflow_service.components import tools_registry
from duo_workflow_service.tools import DuoBaseTool

logger = structlog.getLogger(__name__)

load_dotenv()

# Create cache directory
memory = Memory(location="./tmp/cache", verbose=0)
CHAT = ChatAnthropic(
    model_name="claude-sonnet-4-20250514",
    temperature=0,
    betas=["extended-cache-ttl-2025-04-11"],
    timeout=30,
    stop=None,
)
BASE_DATASET_NAME = "ds-junming-test"


class EvalCase(BaseModel):
    tools: List[DuoBaseTool]
    messages: List[BaseMessage]
    expected_tool: DuoBaseTool


def extract_tool_names(openai_tool_specs: List[Dict[str, Any]]):
    tool_names = []
    for tool_spec in openai_tool_specs:
        if tool_spec["type"] == "function":
            tool_names.append(tool_spec["function"]["name"])
    return tool_names


@memory.cache
def load_langsmith_examples(dataset_name: str) -> List[LSExample]:
    logger.info("Loading base dataset from LangSmith...")
    client = Client()
    return list(client.list_examples(dataset_name=dataset_name))


@memory.cache
def convert_to_eval_cases(
    examples: List[LSExample], all_tools_dict: Dict[str, DuoBaseTool]
) -> List[EvalCase]:
    eval_cases = []
    all_tools = list(all_tools_dict.values())
    for example in examples:
        tool_names = extract_tool_names((example.inputs or {}).get("tools", []))
        expected_tool_name: str = (example.outputs or {})["message"]["tool_calls"][-1][
            "function"
        ]["name"]
        expected_tool = all_tools_dict.get(expected_tool_name)
        if expected_tool is None:
            raise ValueError(
                f"Expected tool: {expected_tool_name} is not available in all tools"
            )
        eval_cases.append(
            EvalCase(
                tools=(
                    [tool for tool in all_tools if tool in tool_names]
                    if tool_names
                    else all_tools
                ),
                expected_tool=expected_tool,
                messages=convert_to_messages(
                    (example.inputs or {}).get("messages", [])
                ),
            )
        )
    return eval_cases


def prepare_eval_cases() -> List[EvalCase]:
    logger.info("Preparing dataset...")
    all_tools_dict = get_available_tools()
    base_cases = []
    try:
        ls_examples = load_langsmith_examples(dataset_name=BASE_DATASET_NAME)
        base_cases = convert_to_eval_cases(
            examples=ls_examples, all_tools_dict=all_tools_dict
        )
    except Exception as e:
        logger.warning(
            f"Errors when processing examples from LangSmith Dataset: {BASE_DATASET_NAME}, please check! Exception: {e}"
        )

    logger.info("Loading dataset from tool registry...")
    codebase_cases = []
    all_tools = list(all_tools_dict.values())
    for _, tool in all_tools_dict.items():
        for prompt in tool.eval_prompts or []:
            codebase_cases.append(
                EvalCase(
                    tools=all_tools,
                    messages=[
                        SystemMessage(content="You are a helpful assistant!"),
                        HumanMessage(content=prompt),
                    ],
                    expected_tool=tool,
                )
            )
    return base_cases + codebase_cases


def get_available_tools() -> Dict[str, DuoBaseTool]:
    tools = (
        tools_registry._DEFAULT_TOOLS
        + tools_registry._READ_ONLY_GITLAB_TOOLS
        + list(chain.from_iterable(tools_registry._AGENT_PRIVILEGES.values()))
    )
    return {tool().name: tool() for tool in tools}  # type: ignore[misc]


async def perform_eval(case: EvalCase, n_runs: int) -> Tuple[int, List[str]]:
    async def _perform_eval(case: EvalCase) -> Tuple[bool, List[str]]:
        llm = CHAT.bind_tools(tools=case.tools)
        response = await llm.ainvoke(case.messages)
        errors = []
        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            errors.append(
                f"No tool calls returned for expected tool {case.expected_tool.name}; response: {response}"
            )
        else:
            for tool_call in tool_calls:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("args")
                try:
                    if tool_name != case.expected_tool.name:
                        raise KeyError(
                            f"Expected tool {case.expected_tool.name}, got {tool_name}"
                        )
                    case.expected_tool.input_schema.model_validate(tool_args)
                except Exception as e:
                    error_msg = (
                        f"Routing eval failed with llm response tool_name: {tool_name}, "
                        f"tool_args: {tool_args} for expected tool: {case.expected_tool.name}. Error: {e}"
                    )
                    errors.append(error_msg)
        is_pass = len(errors) == 0
        return is_pass, errors

    results = await asyncio.gather(*[_perform_eval(case=case) for _ in range(n_runs)])
    pass_runs = sum(res[0] for res in results)
    all_errors = all_errors = list(chain.from_iterable([res[1] for res in results]))
    return pass_runs, all_errors


async def run_evaluation(args: argparse.Namespace) -> None:
    """Main evaluation logic."""

    logger.info("Starting tool routing evaluation...")
    logger.info(f"Tools: {'all' if args.tools is None else ', '.join(args.tools)}")
    logger.info(f"Runs per example: {args.runs}")
    logger.info(f"Cache: {'enabled' if args.cache else 'disabled'}")

    eval_cases = prepare_eval_cases()
    tools_to_eval = args.tools or list(get_available_tools().keys())
    for tool_name in tools_to_eval:
        tool_cases = [
            case for case in eval_cases if case.expected_tool.name == tool_name
        ]
        if tool_cases:
            logger.info(f"Evaluating tool: {tool_name}")
        for case in tool_cases:
            is_pass, errors = await perform_eval(case=case, n_runs=args.runs)
            user_prompt = (
                case.messages[-1].content
                if isinstance(case.messages[-1], HumanMessage)
                else ""
            )
            logger.info(
                f"Eval result: {is_pass}/{args.runs}; Errors: {errors}; Prompt: {user_prompt}"
            )


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for tool routing evaluation."""

    parser = argparse.ArgumentParser(
        description="Run tool routing evaluation with configurable parameters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """Examples:
        %(prog)s                                    # Run all tools, 10 runs each, cache enabled
        %(prog)s --tools list_dir read_file      # Run specific tools only
        %(prog)s --runs 5 --no-cache               # 5 runs per example, cache disabled
        %(prog)s -t list_dir -r 5               # Single tool, 5 runs each
        """
        ).strip(),
    )

    parser.add_argument(
        "--tools",
        "-t",
        nargs="*",
        type=str,
        help="Specific tool(s) to evaluate. If not specified, evaluates all available tools. "
        "Examples: list_dir, read_file, edit_file",
    )

    parser.add_argument(
        "--runs",
        "-r",
        type=int,
        default=1,
        help="Number of runs for each evaluation example to ensure stable results (default: %(default)s)",
    )

    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--cache",
        action="store_true",
        default=True,
        help="Enable caching (default behavior)",
    )
    cache_group.add_argument(
        "--no-cache",
        action="store_false",
        dest="cache",
        help="Disable caching for fresh evaluation runs",
    )

    parser.add_argument(
        "--list-tools", action="store_true", help="List all available tools and exit"
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate parsed arguments and provide helpful error messages."""

    if args.runs < 1:
        logger.error("Error: Number of runs must be at least 1", file=sys.stderr)
        sys.exit(1)

    if args.runs > 10:
        logger.error("Error: Number of runs must be at most 10", file=sys.stderr)
        sys.exit(1)

    # Validate tools if specified
    if args.tools is not None:
        available_tools = get_available_tools()
        invalid_tools = [tool for tool in args.tools if tool not in available_tools]

        if invalid_tools:
            logger.error(
                f"Error: Unknown tools specified: {', '.join(invalid_tools)}",
                file=sys.stderr,
            )
            logger.info(
                f"Available tools: {', '.join(available_tools)}", file=sys.stderr
            )
            sys.exit(1)


async def main():
    args = parse_arguments()

    if args.list_tools:
        logger.info("Available tools:")
        for tool in get_available_tools():
            logger.info(f"  - {tool}")
        sys.exit(0)

    validate_arguments(args)

    # Run the evaluation
    try:
        await run_evaluation(args)
    except KeyboardInterrupt:
        logger.info("\nEvaluation interrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during evaluation: {e}", file=sys.stderr)
        raise e


if __name__ == "__main__":
    asyncio.run(main())
