import json
import logging
from typing import List, Union

from duo_workflow_service.entities.event import WorkflowEvent
from duo_workflow_service.gitlab.http_client import GitlabHttpClient

logger = logging.getLogger(__name__)


async def get_event(
    gitlab_client: GitlabHttpClient, workflow_id: str, ack: bool = True
) -> Union[WorkflowEvent, None]:
    response = await gitlab_client.aget(
        path=f"/api/v4/ai/duo_workflows/workflows/{workflow_id}/events",
        parse_json=True,
        use_http_response=True,
    )

    if not response.is_success():
        logger.error(
            f"Failed to get events: status_code={response.status_code}, error={response.body}"
        )
        return None

    events: List[WorkflowEvent] = response.body

    if isinstance(events, list) and len(events) > 0:
        if ack:
            await ack_event(gitlab_client, workflow_id, events[0])

        return events[0]

    return None


async def ack_event(
    gitlab_client: GitlabHttpClient, workflow_id: str, event: WorkflowEvent
):
    await gitlab_client.aput(
        path=f"/api/v4/ai/duo_workflows/workflows/{workflow_id}/events/{event['id']}",
        body=json.dumps({"event_status": "delivered"}),
        use_http_response=True,
    )


async def post_event(
    gitlab_client: GitlabHttpClient, workflow_id, event_type, message: str
) -> WorkflowEvent:
    response = await gitlab_client.apost(
        path=f"/api/v4/ai/duo_workflows/workflows/{workflow_id}/events",
        parse_json=True,
        use_http_response=True,
        body=json.dumps(
            {
                "event_type": event_type,
                "message": message,
            }
        ),
    )

    if not response.is_success():
        logger.error(
            f"Failed to post event: status_code={response.status_code}, error={response.body}"
        )

    return response.body
