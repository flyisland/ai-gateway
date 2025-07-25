# pylint: disable=direct-environment-variable-reference
import json
import os
from typing import Optional

import sentry_sdk
import structlog
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.grpc import GRPCIntegration
from sentry_sdk.types import Event, Hint

log = structlog.stdlib.get_logger("error_tracking")


def setup_error_tracking():
    if sentry_tracking_available():
        sentry_sdk.init(
            dsn=os.environ.get("SENTRY_DSN"),
            environment=os.environ.get("DUO_WORKFLOW_SERVICE_ENVIRONMENT"),
            traces_sample_rate=1.0,
            before_send=sentry_filtering_before_send,
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


def sentry_filtering_before_send(event: Event, hint: Hint) -> Optional[Event]:
    """Filter Sentry events before sending them."""
    filtered_event = remove_private_info_fields(event)
    updated_event = filter_checkpoint_errors(filtered_event, hint)
    return updated_event


def remove_private_info_fields(event: Event) -> Event:
    # Remove sensitive information from event data
    if event and "server_name" in event:
        event = event.copy()
        event["server_name"] = None  # type: ignore
    return event


def filter_checkpoint_errors(event: Event, hint: Hint) -> Optional[Event]:
    """Filter out JSON decode errors from checkpoints endpoints."""
    is_json = False
    is_from_http_client = False
    if "exc_info" not in hint:
        return event

    try:
        _, exc_value, traceback = hint["exc_info"]
        if isinstance(exc_value, json.JSONDecodeError):
            is_json = True
            current_traceback = traceback
            while current_traceback:
                frame = current_traceback.tb_frame
                if frame.f_code.co_name == "_parse_response":
                    is_from_http_client = True
                    break
                current_traceback = current_traceback.tb_next
    except (ValueError, TypeError):
        return event

    extra = event.get("extra", {})
    path = extra.get("path", "")
    if is_json and is_from_http_client and "/checkpoints" in path:  # type: ignore[operator]
        return None

    return event
