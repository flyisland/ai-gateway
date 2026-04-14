from unittest import mock

import pytest
import structlog

from lib.snowplow.logging_async_emitter import LoggingAsyncEmitter


@pytest.fixture(name="emitter")
def emitter_fixture():
    emitter = LoggingAsyncEmitter(
        logger=structlog.stdlib.get_logger("test_emitter"),
        endpoint="collector.local",
        protocol="https",
        batch_size=1,
        thread_count=1,
    )
    return emitter


class TestLoggingAsyncEmitter:
    def test_http_post_success_does_not_log_warning(self, emitter):
        with mock.patch(
            "snowplow_tracker.emitters.Emitter.http_post", return_value=200
        ):
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                result = emitter.http_post("test_data")

                assert result == 200
                mock_warning.assert_not_called()

    def test_http_post_failure_logs_warning(self, emitter):
        with mock.patch(
            "snowplow_tracker.emitters.Emitter.http_post", return_value=500
        ):
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                result = emitter.http_post("test_data")

                assert result == 500
                mock_warning.assert_called_once_with(
                    "Snowplow POST request failed",
                    status_code=500,
                    endpoint=emitter.endpoint,
                )

    def test_http_post_connection_error_logs_warning(self, emitter):
        with mock.patch("snowplow_tracker.emitters.Emitter.http_post", return_value=-1):
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                result = emitter.http_post("test_data")

                assert result == -1
                mock_warning.assert_called_once_with(
                    "Snowplow POST request failed",
                    status_code=-1,
                    endpoint=emitter.endpoint,
                )

    def test_http_get_success_does_not_log_warning(self, emitter):
        with mock.patch("snowplow_tracker.emitters.Emitter.http_get", return_value=200):
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                result = emitter.http_get({"key": "value"})

                assert result == 200
                mock_warning.assert_not_called()

    def test_http_get_failure_logs_warning(self, emitter):
        with mock.patch("snowplow_tracker.emitters.Emitter.http_get", return_value=404):
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                result = emitter.http_get({"key": "value"})

                assert result == 404
                mock_warning.assert_called_once_with(
                    "Snowplow GET request failed",
                    status_code=404,
                    endpoint=emitter.endpoint,
                )

    def test_retry_failed_events_logs_warning(self, emitter):
        failed_events = [
            {"se_ac": "event_1", "eid": "id-1"},
            {"se_ac": "event_2", "eid": "id-2"},
        ]

        with mock.patch(
            "snowplow_tracker.emitters.Emitter._retry_failed_events"
        ) as mock_retry:
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                emitter._retry_failed_events(failed_events)

                mock_warning.assert_called_once_with(
                    "Retrying failed Snowplow events",
                    failed_count=2,
                    retry_delay=emitter.retry_delay,
                    endpoint=emitter.endpoint,
                )
                mock_retry.assert_called_once_with(failed_events)

    def test_custom_logger(self):
        custom_logger = structlog.stdlib.get_logger("custom_logger")

        emitter = LoggingAsyncEmitter(
            logger=custom_logger,
            endpoint="collector.local",
        )

        assert emitter._logger is custom_logger

    @pytest.mark.parametrize("status_code", [200, 201, 204, 299])
    def test_http_post_2xx_codes_not_logged(self, emitter, status_code):
        with mock.patch(
            "snowplow_tracker.emitters.Emitter.http_post", return_value=status_code
        ):
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                result = emitter.http_post("test_data")

                assert result == status_code
                mock_warning.assert_not_called()

    @pytest.mark.parametrize("status_code", [400, 401, 403, 500, 502, 503])
    def test_http_post_non_2xx_codes_logged(self, emitter, status_code):
        with mock.patch(
            "snowplow_tracker.emitters.Emitter.http_post", return_value=status_code
        ):
            with mock.patch.object(emitter._logger, "warning") as mock_warning:
                result = emitter.http_post("test_data")

                assert result == status_code
                mock_warning.assert_called_once()
