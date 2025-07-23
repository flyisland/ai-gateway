from unittest import mock
from unittest.mock import ANY, Mock

import pytest
from structlog.testing import capture_logs

from ai_gateway.instrumentators.threads import monitor_threads

MAX_LOOP_COUNTER = 1


class LoopCounter:
    def __init__(self, max_count):
        self.count = max_count

    def should_run(self):
        if self.count > 0:
            self.count -= 1
            return True
        return False


@pytest.mark.asyncio
@mock.patch("prometheus_client.Gauge.labels")
@mock.patch("ai_gateway.instrumentators.threads.asyncio.sleep")
async def test_monitor_threads(mock_sleep, mock_gauges):
    loop_counter = LoopCounter(MAX_LOOP_COUNTER)
    mock_loop = Mock()
    mock_loop.is_running = loop_counter.should_run
    interval = 0.001

    with capture_logs() as cap_logs:
        await monitor_threads(mock_loop, interval=interval)

    mock_sleep.assert_any_await(interval)

    assert mock_gauges.mock_calls == [
        mock.call(pid=ANY),
        mock.call().set(ANY),
    ]

    assert cap_logs[0]["pid"] == ANY
    assert cap_logs[0]["threads_count"] == ANY
    assert cap_logs[0]["stacktrace"] == ANY
