import structlog
from snowplow_tracker import AsyncEmitter
from snowplow_tracker.emitters import Emitter

__all__ = ["LoggingAsyncEmitter"]


class LoggingAsyncEmitter(AsyncEmitter):
    """AsyncEmitter subclass that logs HTTP status codes on failure."""

    def __init__(self, logger: structlog.stdlib.BoundLogger, **kwargs):
        self._logger = logger
        super().__init__(**kwargs)

    def http_post(self, data: str) -> int:
        status_code = super().http_post(data)
        if not Emitter.is_good_status_code(status_code):
            self._logger.warning(
                "Snowplow POST request failed",
                status_code=status_code,
                endpoint=self.endpoint,
            )
        return status_code

    def http_get(self, payload) -> int:
        status_code = super().http_get(payload)
        if not Emitter.is_good_status_code(status_code):
            self._logger.warning(
                "Snowplow GET request failed",
                status_code=status_code,
                endpoint=self.endpoint,
            )
        return status_code

    def _retry_failed_events(self, failed_events) -> None:
        self._logger.warning(
            "Retrying failed Snowplow events",
            failed_count=len(failed_events),
            retry_delay=self.retry_delay,
            endpoint=self.endpoint,
        )
        super()._retry_failed_events(failed_events)
