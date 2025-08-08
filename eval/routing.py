from typing import Any, Dict

import structlog
from dotenv import load_dotenv
from joblib import Memory
from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.messages.utils import convert_to_messages
from langsmith import Client

from duo_workflow_service.components import tools_registry

load_dotenv()

chat = ChatAnthropic(model="claude-sonnet-4-20250514")

log = structlog.get_logger(__name__)


# Create cache directory
memory = Memory(location="./cache_directory", verbose=0)


@memory.cache
def load_base_dataset():
    client = Client()
    return list(client.list_examples(dataset_name="ds-junming-test"))


def get_all_tools() -> Dict[str, BaseTool]:
    from itertools import chain

    tools = (
        tools_registry._DEFAULT_TOOLS
        + tools_registry._READ_ONLY_GITLAB_TOOLS
        + tools_registry.NO_OP_TOOLS
        + list(chain.from_iterable(tools_registry._AGENT_PRIVILEGES.values()))
    )
    return {tool.name: tool for tool in tools}


def get_expected_tool_name(message: Dict):
    msg = convert_to_messages(messages=[message])[-1]
    return msg.tool_calls[-1].get("name")


for example in load_base_dataset():
    expected_tool = get_expected_tool_name(message=example.outputs.get("message"))
    inputs = example.inputs
    log.info(f"{inputs.keys()}, expected_tool: {expected_tool}")
    if set(["tools", "messages"]).issubset(inputs.keys()):
        llm = chat.bind_tools(tools=inputs.get("tools"))
        response = llm.invoke(inputs.get("messages"))
        log.info(f"tool calls: {response.tool_calls}")
