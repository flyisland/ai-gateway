# pylint: disable=direct-environment-variable-reference

import os

import sentry_sdk
import structlog
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.grpc import GRPCIntegration

log = structlog.stdlib.get_logger("error_tracking")


def setup_error_tracking():
    if sentry_tracking_available():
        sentry_sdk.init(
            dsn=os.environ.get("SENTRY_DSN"),
            environment=os.environ.get("DUO_WORKFLOW_SERVICE_ENVIRONMENT"),
            traces_sample_rate=1.0,
            before_send=remove_private_info_fields,
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


def remove_private_info_fields(event, hint):  # pylint: disable=unused-argument
    # Remove sensitive information from event data
    updated_event = event

    if "server_name" in updated_event:
        updated_event["server_name"] = None
    
    # Filter out handled errors to reduce monitoring noise
    if _should_filter_error(event, hint):
        log.debug("Filtering out handled error from Sentry", extra={"event": event})
        return None
    
    return updated_event


def _should_filter_error(event, hint):
    """Determine if an error should be filtered out from Sentry reporting."""
    # Filter out handled HTTP errors that are expected
    if "exception" in event and "values" in event["exception"]:
        for exception in event["exception"]["values"]:
            exception_type = exception.get("type", "")
            exception_value = exception.get("value", "")
            
            # Filter out handled rate limiting errors (429)
            if "429" in exception_value or "rate limit" in exception_value.lower():
                return True
            
            # Filter out handled overload errors
            if "overload" in exception_value.lower() or "throttle" in exception_value.lower():
                return True
            
            # Filter out handled timeout errors that are retried
            if "timeout" in exception_value.lower() and "retry" in exception_value.lower():
                return True
            
            # Filter out handled authentication errors that are expected
            if "401" in exception_value or "unauthorized" in exception_value.lower():
                return True
    
    # Filter out errors with specific tags indicating they are handled
    if "tags" in event:
        tags = event["tags"]
        if tags.get("handled") == "true" or tags.get("expected") == "true":
            return True
    
    # Filter out errors from specific modules that handle errors gracefully
    if "modules" in event:
        handled_modules = ["duo_workflow_service.errors", "duo_workflow_service.retry"]
        for module in handled_modules:
            if any(module in mod for mod in event["modules"]):
                return True
    
    return False
