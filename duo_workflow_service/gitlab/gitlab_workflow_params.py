import logging
from typing import Any

from duo_workflow_service.gitlab.http_client import GitlabHttpClient

logger = logging.getLogger(__name__)


async def fetch_workflow_config(
    client: GitlabHttpClient, workflow_id: str
) -> dict[str, Any]:
    response = await client.aget(
        path=f"/api/v4/ai/duo_workflows/workflows/{workflow_id}",
        parse_json=True,
        use_http_response=True,
    )

    if not response.is_success():
        logger.error(
            f"Failed to fetch workflow config: status_code={response.status_code}, error={response.body}"
        )

    return response.body
