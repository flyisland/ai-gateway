# pylint: disable=direct-environment-variable-reference
import os
from typing import Optional

import sentry_sdk
import structlog
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.grpc import GRPCIntegration
from sentry_sdk.types import Event

from duo_workflow_service.monitoring import duo_workflow_metrics

log = structlog.stdlib.get_logger("error_tracking")


def setup_error_tracking():
    if sentry_tracking_available():
        sentry_sdk.init(
            dsn=os.environ.get("SENTRY_DSN"),
            environment=os.environ.get("DUO_WORKFLOW_SERVICE_ENVIRONMENT"),
            traces_sample_rate=1.0,
            before_send=before_send,
            profiles_sample_rate=1.0,
            integrations=[GRPCIntegration(), AsyncioIntegration()],
            max_value_length=30 * 1024,
        )


def sentry_tracking_available():
    if os.environ.get("SENTRY_ERROR_TRACKING_ENABLED") == "true":
        if os.environ.get("SENTRY_DSN"):
            log.debug("Using Sentry for error tracking...")
            return True
        log.debug("Could not find Sentry DSN for error tracking setup...")
    else:
        log.debug("Sentry error tracking disabled...")
    return False


def before_send(event: Event, _) -> Optional[Event]:
    sanitized_event = remove_private_info_fields(event)
    filtered_event = catch_asyncio_warnings(sanitized_event)
    return filtered_event


def catch_asyncio_warnings(event: Event) -> Optional[Event]:
    """Catch asyncio warnings and count them using prometheus."""

    if event.get("logger") != "asyncio":
        return event

    # Check for the specific warning message
    try:
        message = event.get("logentry", {}).get("message", "")
        if (
            not isinstance(message, str)
            or "Task was destroyed but it is pending" not in message
        ):
            return event
    except (AttributeError, TypeError):
        return event

    # Extract workflow ID from breadcrumbs
    workflow_id = "unknown"
    try:
        breadcrumbs = event.get("breadcrumbs")
        if isinstance(breadcrumbs, dict):
            values = breadcrumbs.get("values", [])
            for crumb in values:
                crumb_workflow_id = crumb.get("data", {}).get("workflow_id")
                if crumb_workflow_id and crumb_workflow_id != "undefined":
                    workflow_id = crumb_workflow_id
                    log.info(f"Workflow ID: {crumb_workflow_id}")
                    break
    except (AttributeError, TypeError):
        pass  # Use default "unknown" workflow_id

    # Count the warning
    duo_workflow_metrics.count_asyncio_warning(
        type="pending_task_destroyed",
        workflow_id=workflow_id,
    )
    # Filter the event
    return None


def remove_private_info_fields(event: Event) -> Event:
    # Remove sensitive information from event data
    updated_event = event

    if "server_name" in updated_event:
        updated_event["server_name"] = None  # type: ignore[typeddict-item]
    return updated_event
