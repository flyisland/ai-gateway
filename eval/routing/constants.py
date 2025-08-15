from dotenv import load_dotenv
from langchain_anthropic.chat_models import ChatAnthropic
from langsmith import Client

load_dotenv()

CHAT = ChatAnthropic(
    model_name="claude-sonnet-4-20250514",
    temperature=0,
    betas=["extended-cache-ttl-2025-04-11"],
    timeout=30,
    stop=None,
)

LS_CLIENT = Client()

DEFAULT_LS_DATASET_INPUTS_SCHEMA = {
    "type": "object",
    "properties": {
        "messages": {
            "type": "array",
            "items": {
                "$ref": "https://api.smith.langchain.com/public/schemas/v1/message.json"
            },
        },
        "tools": {
            "type": "array",
            "items": {
                "$ref": "https://api.smith.langchain.com/public/schemas/v1/tooldef.json"
            },
        },
    },
    "required": ["messages"],
}

DEFAULT_LS_DATASET_OUTPUTS_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {
            "$ref": "https://api.smith.langchain.com/public/schemas/v1/tooldef.json"
        }
    },
    "required": ["tool"],
}
