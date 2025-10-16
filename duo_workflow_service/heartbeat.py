import logging

from duo_workflow_service.executor.outbox import Outbox
from duo_workflow_service.gitlab.http_client import GitlabHttpClient

logger = logging.getLogger(__name__)


class Heartbeat:
    def __init__(self, workflow_id: str, lease_id: str | None, outbox: GitlabHttpClient):
        self.workflow_id = workflow_id
        self.lease_id = lease_id
        self.http_client = http_client
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self) -> None:
        logger.info("Starting heartbeat")

        workflow_gid = f"gid://gitlab/Ai::DuoWorkflows::Workflow/{workflow_id}"

        variables = {
            "leaseId": self.lease_id,
            "workflowId": workflow_gid,
        }

        mutation = """
mutation($workflowId: WorkflowID!, $leaseId: String) {
    AiDuoWorkflowLeaseRenew(input: {
    workflowId: $workflowId,
    leaseId: $leaseId,
    }) {
        errors
        lastRenewedAt
    }
}
"""
        try:
            while True:
                response = await self.http_client.apost(
                            path=f"/api/graphql",
                            body=json.dumps({"query": mutation, "variables": variables}),
                            use_http_response=True,
                        )

                if response.is_success():
                    logger.info("Heartbeat sent successfully", last_renewed_at=response.body["data"]["AiDuoWorkflowLeaseRenew"]["lastRenewedAt"])
                else:
                    logger.error(
                        "Heartbeat failed",
                        status_code=response.status_code,
                        body=response.body,
                    )

        finally:
            logger.error("Heartbeat sender task failed")
