import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional, Union
from urllib.parse import urlencode

from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action
from duo_workflow_service.gitlab.http_client import GitlabHttpClient

logger = logging.getLogger(__name__)

class ExecutorGitLabHttpClient(GitlabHttpClient):
    """GitLab HTTP client implementation that uses the executor service."""

    def __init__(self, outbox: asyncio.Queue, inbox: asyncio.Queue):
        self.outbox = outbox
        self.inbox = inbox

    async def _call(
        self,
        path: str,
        method: str,
        parse_json: bool = True,
        data: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        object_hook: Union[Callable, None] = None,
    ) -> Any:
        if params:
            query_string = urlencode(params)
            path = f"{path}?{query_string}"

        response = await _execute_action(
            {"outbox": self.outbox, "inbox": self.inbox},
            contract_pb2.Action(
                runHTTPRequest=contract_pb2.RunHTTPRequest(
                    path=path, method=method, body=data
                )
            ),
        )

        if not parse_json:
            return response

        try:
            return json.loads(response, object_hook=object_hook)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {method} {path}: {str(e)}. ")
            logger.error(
                f"Raw response type: {type(response)}, content: {repr(response)}"
            )

            return {}
