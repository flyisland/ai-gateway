from datetime import datetime, timezone
from typing import Dict, List, Optional

import grpc
from fastapi import WebSocket

from duo_workflow_service.interceptors import (
    X_GITLAB_FEATURE_ENABLED_BY_NAMESPACE_IDS,
    X_GITLAB_GLOBAL_USER_ID_HEADER,
    X_GITLAB_HOST_NAME,
    X_GITLAB_INSTANCE_ID_HEADER,
    X_GITLAB_IS_A_GITLAB_MEMBER,
    X_GITLAB_NAMESPACE_ID,
    X_GITLAB_PROJECT_ID,
    X_GITLAB_REALM_HEADER,
)
from duo_workflow_service.interceptors.correlation_id_interceptor import correlation_id
from duo_workflow_service.interceptors.websocket_middleware import WebSocketMiddleware
from duo_workflow_service.internal_events import EventContext, current_event_context


def convert_feature_enabled_string_to_list(
    enabled_features: Optional[str] = None,
) -> Optional[List[int]]:
    if not enabled_features or enabled_features == "undefined":
        return None

    return [int(feature.strip()) for feature in enabled_features.split(",")]


def _set_event_context(metadata: Dict[str, str]) -> None:
    is_gitlab_member_metadata = metadata.get(X_GITLAB_IS_A_GITLAB_MEMBER, None)
    is_gitlab_member = None
    if is_gitlab_member_metadata:
        is_gitlab_member = is_gitlab_member_metadata.lower() == "true"

    feature_enabled_by_namespace_ids_metadata = metadata.get(
        X_GITLAB_FEATURE_ENABLED_BY_NAMESPACE_IDS, None
    )
    feature_enabled_by_namespace_ids = convert_feature_enabled_string_to_list(
        enabled_features=feature_enabled_by_namespace_ids_metadata
    )

    project_id_metadata = metadata.get(X_GITLAB_PROJECT_ID)
    project_id = int(project_id_metadata) if project_id_metadata else None

    namespace_id_metadata = metadata.get(X_GITLAB_NAMESPACE_ID)
    namespace_id = int(namespace_id_metadata) if namespace_id_metadata else None

    context = EventContext(
        realm=metadata.get(X_GITLAB_REALM_HEADER),
        instance_id=metadata.get(X_GITLAB_INSTANCE_ID_HEADER),
        host_name=metadata.get(X_GITLAB_HOST_NAME),
        global_user_id=metadata.get(X_GITLAB_GLOBAL_USER_ID_HEADER),
        context_generated_at=datetime.now(timezone.utc).isoformat(),
        correlation_id=correlation_id.get(),
        project_id=project_id,
        feature_enabled_by_namespace_ids=feature_enabled_by_namespace_ids,
        namespace_id=namespace_id,
        is_gitlab_team_member=is_gitlab_member,
    )

    current_event_context.set(context)


class InternalEventsInterceptor(grpc.aio.ServerInterceptor):

    def __init__(self):
        pass

    async def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)

        _set_event_context(metadata)

        return await continuation(handler_call_details)


class InternalEventsMiddleware(WebSocketMiddleware):
    async def __call__(self, websocket: WebSocket):
        headers = dict(websocket.headers)

        _set_event_context(headers)
