import asyncio
from typing import Any, Dict

import structlog

from contract import contract_pb2


async def _execute_action(metadata: Dict[str, Any], action: contract_pb2.Action):
    outbox: asyncio.Queue = metadata["outbox"]
    inbox: asyncio.Queue = metadata["inbox"]
    log = structlog.stdlib.get_logger("workflow")

    log.debug(
        "Attempting action from the egress queue",
        requestID=action.requestID,
        action_class=action.WhichOneof("action"),
    )

    await outbox.put(action)

    event: contract_pb2.ClientEvent = await inbox.get()

    if event.actionResponse:
        log.debug(
            "Read ClientEvent into the ingres queue",
            requestID=event.actionResponse.requestID,
        )

    inbox.task_done()
    return event.actionResponse.response
