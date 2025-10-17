import base64
import json
import zlib
from enum import StrEnum
from urllib.parse import urlencode

from langgraph.checkpoint.base import Checkpoint

from duo_workflow_service.gitlab.http_client import checkpoint_decoder
from duo_workflow_service.json_encoder.encoder import CustomEncoder
from lib.internal_events.event_enum import EventPropertyEnum

STATUS_TO_EVENT_PROPERTY = {
    "finished": EventPropertyEnum.WORKFLOW_COMPLETED,
    "stopped": EventPropertyEnum.CANCELLED_BY_USER,
    "input_required": EventPropertyEnum.WORKFLOW_RESUME_BY_PLAN_AFTER_INPUT,
    "plan_approval_required": EventPropertyEnum.WORKFLOW_RESUME_BY_PLAN_AFTER_APPROVAL,
}


class WorkflowStatusEventEnum(StrEnum):
    START = "start"
    FINISH = "finish"
    DROP = "drop"
    RESUME = "resume"
    PAUSE = "pause"
    STOP = "stop"
    RETRY = "retry"
    REQUIRE_INPUT = "require_input"
    REQUIRE_PLAN_APPROVAL = "require_plan_approval"
    REQUIRE_TOOL_CALL_APPROVAL = "require_tool_call_approval"


SUCCESSFUL_WORKFLOW_EXECUTION_STATUSES = [
    WorkflowStatusEventEnum.FINISH,
    WorkflowStatusEventEnum.STOP,
    WorkflowStatusEventEnum.REQUIRE_INPUT,
    WorkflowStatusEventEnum.REQUIRE_PLAN_APPROVAL,
    WorkflowStatusEventEnum.REQUIRE_TOOL_CALL_APPROVAL,
]


def compress_checkpoint(data: Checkpoint) -> str:
    """Compress checkpoint using zlib compression and base64 encode.

    Args:
        data: The checkpoint dictionary to compress

    Returns:
        Base64-encoded compressed checkpoint string
    """
    json_str = json.dumps(dict(data), cls=CustomEncoder)
    compressed = zlib.compress(json_str.encode("utf-8"))
    return base64.b64encode(compressed).decode("utf-8")


def decompress_checkpoint(compressed_data: str) -> dict:
    """Decompress compressed data.

    Args:
        compressed_data: Base64-encoded zlib compressed string

    Returns:
        Decompressed checkpoiont dictionary
    """
    decoded = base64.b64decode(compressed_data.encode("utf-8"))
    decompressed = zlib.decompress(decoded)
    return json.loads(decompressed.decode("utf-8"), object_hook=checkpoint_decoder)


def add_compression_param(endpoint: str) -> str:
    """Add accept_compressed=true query parameter to endpoint URL.

    Args:
        endpoint: The base endpoint URL, may already contain query parameters

    Returns:
        The endpoint with accept_compressed=true added as a query parameter
    """
    separator = "&" if "?" in endpoint else "?"
    return endpoint + separator + urlencode({"accept_compressed": "true"})
