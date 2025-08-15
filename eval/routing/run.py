import argparse
import asyncio
import sys
import textwrap
from typing import List

import structlog
from dotenv import load_dotenv
from langsmith import Client
from langsmith.schemas import Example

from eval.routing.constants import LS_CLIENT
from eval.routing.dataset import generate_dataset, get_available_tools, memory
from eval.routing.evaluator import execute_routing, is_correct

logger = structlog.get_logger(__name__)

load_dotenv()

client = Client()


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
        "--dataset-name",
        "-d",
        type=str,
        required=True,
        help="Specify a LangSmith dataset name. "
        "Dataset will be created if it doesn't exist. "
        "Name should be unique and will be reused across evaluations.",
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
        logger.error("Error: Number of runs must be at least 1")
        sys.exit(1)

    if args.runs > 10:
        logger.error("Error: Number of runs must be at most 10")
        sys.exit(1)

    if not args.cache:
        logger.info("Clearning the cache...")
        memory.clear(warn=False)

    # Validate tools if specified
    if args.tools is not None:
        available_tools = [tool.name for tool in get_available_tools()]
        invalid_tools = [tool for tool in args.tools if tool not in available_tools]

        if invalid_tools:
            logger.error(f"Error: Unknown tools specified: {', '.join(invalid_tools)}")
            logger.info(f"Available tools: {', '.join(available_tools)}")
            sys.exit(1)


async def run_evaluation(args: argparse.Namespace) -> None:
    generate_dataset(dataset_name=args.dataset_name, tools=get_available_tools())
    example_subsets: List[Example] = []
    for tool in args.tools:
        example_subsets.extend(
            LS_CLIENT.list_examples(
                dataset_name=args.dataset_name,
                as_of="latest",
                metadata={"tool_name": tool},
            )
        )
    logger.info(
        f"Starting evaluation on {len(example_subsets)} examples from dataset..."
    )
    await LS_CLIENT.aevaluate(
        execute_routing,
        data=example_subsets,
        evaluators=[is_correct],
        num_repetitions=args.runs,
    )


async def main():
    args = parse_arguments()

    if args.list_tools:
        logger.info("Available tools:")
        for tool in get_available_tools():
            logger.info(f"  - {tool.name}")
        sys.exit(0)

    validate_arguments(args)

    # Run the evaluation
    try:
        await run_evaluation(args)
    except KeyboardInterrupt:
        logger.info("\nEvaluation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during evaluation: {e}")
        raise e


if __name__ == "__main__":
    asyncio.run(main())
