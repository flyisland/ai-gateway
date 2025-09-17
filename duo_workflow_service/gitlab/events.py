import json
from typing import List, Union

from duo_workflow_service.entities.event import WorkflowEvent
from duo_workflow_service.gitlab.http_client import GitlabHttpClient


async def get_event(
    gitlab_client: GitlabHttpClient, workflow_id: str, ack: bool = True
) -> Union[WorkflowEvent, None]:
    events: List[WorkflowEvent] = await gitlab_client.aget(
        path=f"/api/v4/ai/duo_workflows/workflows/{workflow_id}/events", parse_json=True
    )

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
    )


async def post_event(
    gitlab_client: GitlabHttpClient, workflow_id, event_type, message: str
) -> WorkflowEvent:
    from duo_workflow_service.gitlab.http_client import GitLabHttpResponse
    
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
    
    if isinstance(response, GitLabHttpResponse):
        if response.error:
            raise Exception(f"HTTP request failed: {response.error}")
        if response.status_code != 200:
            raise Exception(f"HTTP request failed with status {response.status_code}: {response.body}")
        return response.body
    
    return response
