import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client
from tqdm import tqdm


def main():

    parser = argparse.ArgumentParser(
        description="Fetch Duo Workflow chat traces from Langsmith for product analytics.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days of traces to fetch.",
    )
    parser.add_argument(
        "--project-name",
        type=str,
        default="duo-workflow-production",
        help="The Langsmith project name to fetch traces from.",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        type=str,
        default=None,
        help="Output file name. If not provided, a timestamped name will be generated.",
    )
    args = parser.parse_args()

    output_file = fetch_duo_workflow_traces(
        days=args.days, project_name=args.project_name, output_file=args.output_file
    )
    if output_file:
        print(f"\nSuccessfully saved trace data to: {output_file}")


def fetch_duo_workflow_traces(days: int, project_name: str, output_file: str = ""):
    """Fetches root runs for chat workflows and orchestrates writing them to a file."""
    load_dotenv()

    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"duo_workflow_traces_{timestamp}.jsonl"

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        client = Client()
    except Exception as e:
        print(f"Error: Failed to create Langsmith client: {e}")
        print(
            "Please ensure your LANGCHAIN_API_KEY and other environment variables are set correctly."
        )
        return None

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    try:
        root_runs = list(
            client.list_runs(
                project_name=project_name,
                run_type="chain",
                start_time=start_time,
                end_time=end_time,
                filter="and(eq(is_root, true), eq(metadata_key, 'workflow_type'), eq(metadata_value, 'chat'))",
            )
        )

        if not root_runs:
            print("No chat workflow traces found in the specified time period.")
            return None

        print(f"Found {len(root_runs)} chat traces. Reconstructing conversations...")
        _write_traces_to_jsonl(root_runs, client, output_path)
        return output_path

    except Exception as e:
        print(f"An error occurred while fetching or processing traces: {e}")
        return None


def _reconstruct_conversation_from_trace(
    root_run, trace_runs: list
) -> tuple[list, str]:
    conversation = []

    initial_prompt = root_run.inputs.get("goal")
    if initial_prompt:
        conversation.append({"role": "human", "content": initial_prompt})

    sorted_runs = sorted(trace_runs, key=lambda r: r.start_time)

    # Track the content of the last AI message to avoid duplicates from retries
    last_ai_content = None

    for run in sorted_runs:
        # User/Human messages are captured from the root input.
        # This loop focuses on AI and Tool messages that occur during the flow.
        if run.run_type == "llm":
            if run.outputs and "generations" in run.outputs:
                generation_text = run.outputs["generations"][0][0].get("text")
                if generation_text and generation_text != last_ai_content:
                    conversation.append({"role": "ai", "content": generation_text})
                    last_ai_content = generation_text

        elif run.run_type == "tool":
            tool_name = run.name
            tool_input = run.inputs.get("input", run.inputs)

            if isinstance(tool_input, dict):
                tool_input_str = json.dumps(tool_input, indent=2)
            else:
                tool_input_str = str(tool_input)

            conversation.append(
                {
                    "role": "tool",
                    "content": {"tool_name": tool_name, "input": tool_input_str},
                }
            )

    if not initial_prompt and conversation:
        first_human = next(
            (msg for msg in conversation if msg["role"] == "human"), None
        )
        if first_human:
            initial_prompt = first_human["content"]

    return conversation, (initial_prompt or "Unknown")


def _write_traces_to_jsonl(root_runs: list, client: Client, output_path: Path):

    with open(output_path, "w", encoding="utf-8") as f:
        for root_run in tqdm(root_runs, desc="Processing traces"):
            try:
                full_trace_runs = list(client.list_runs(trace_id=root_run.id))

                conversation, initial_prompt = _reconstruct_conversation_from_trace(
                    root_run, full_trace_runs
                )

                if not conversation:
                    continue  # Skip traces where conversation couldn't be reconstructed

                trace_data = {
                    "trace_id": str(root_run.id),
                    "start_time": root_run.start_time.isoformat(),
                    "end_time": root_run.end_time.isoformat(),
                    "latency_seconds": (
                        root_run.end_time - root_run.start_time
                    ).total_seconds(),
                    "initial_prompt": initial_prompt,
                    "final_output": (
                        root_run.outputs.get("output") if root_run.outputs else None
                    ),
                    "conversation": conversation,
                    "metadata": root_run.extra.get("metadata", {}),
                    "tags": root_run.tags,
                }

                # Write the JSON object as a single line in the output file
                f.write(json.dumps(trace_data) + "\n")

            except Exception as e:
                tqdm.write(
                    f"Warning: Could not process trace {root_run.id}. Error: {e}"
                )


if __name__ == "__main__":
    main()
