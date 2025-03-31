from typing import Annotated, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from gitlab_cloud_connector import GitLabFeatureCategory, GitLabUnitPrimitive
from pydantic import BaseModel

from ai_gateway.api.auth_utils import StarletteUser, get_current_user
from ai_gateway.api.feature_category import feature_category
from ai_gateway.async_dependency_resolver import (
    get_amazon_q_client_factory,
    get_internal_event_client,
)
from ai_gateway.integrations.amazon_q.client import AmazonQClientFactory
from ai_gateway.integrations.amazon_q.errors import AWSException, AccessDeniedException, AccessDeniedExceptionReason
from ai_gateway.internal_events import InternalEventsClient

__all__ = [
    "router",
]

router = APIRouter()

class HealthCheckStatus(BaseModel):
    status: str
    message: str

class HealthCheckResponse(BaseModel):
    response: Dict[str, HealthCheckStatus]

@router.post("/verifyOAuthAppConnection", response_model=HealthCheckResponse)
@feature_category(GitLabFeatureCategory.DUO_CHAT)
async def verify_oauth_app_connection(
    request: Request,
    current_user: Annotated[StarletteUser, Depends(get_current_user)],
    internal_event_client: Annotated[
        InternalEventsClient, Depends(get_internal_event_client)
    ],
    amazon_q_client_factory: Annotated[
        AmazonQClientFactory, Depends(get_amazon_q_client_factory)
    ],
):
    if not current_user.can(GitLabUnitPrimitive.AMAZON_Q_INTEGRATION):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to perform action",
        )

    internal_event_client.track_event(
        f"request_{GitLabUnitPrimitive.AMAZON_Q_INTEGRATION}",
        category=__name__,
    )

    try:
        q_client = amazon_q_client_factory.get_client(current_user=current_user)
        health_check_result = q_client.verify_oauth_app_connection()
        
        return HealthCheckResponse(response=health_check_result)

    except AccessDeniedException as e:
        if e.reason in [AccessDeniedExceptionReason.GITLAB_EXPIRED_IDENTITY, 
                        AccessDeniedExceptionReason.GITLAB_INVALID_IDENTITY, 
                        AccessDeniedExceptionReason.GITLAB_OAUTH_CONNECTION_INVALID, 
                        AccessDeniedExceptionReason.GITLAB_INSTANCE_UNREACHABLE]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access Denied")
    except AWSException as e:
        if e.status_code == 429:
            return HealthCheckResponse(response={
                "GITLAB_INSTANCE_REACHABLE": HealthCheckStatus(status="ERROR", message="Request was throttled. Please try again later."),
                "GITLAB_OAUTH_CONNECTION_VALID": HealthCheckStatus(status="ERROR", message="Request was throttled. Please try again later.")
            })
        elif e.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        elif e.status_code == 500:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
        else:
            raise e.to_http_exception()
