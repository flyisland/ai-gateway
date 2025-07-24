from typing import Any, Dict
from unittest import mock

import pytest
from snowplow_tracker import SelfDescribingJson, Snowplow

from lib.billing_events.client import BillingEventsClient
from lib.internal_events.context import EventContext, current_event_context

BASE_BILLING_CONTEXT_SCHEMA: Dict[str, Any] = {
    "event_id": None,
    "event_type": None,
    "unit_of_measure": None,
    "quantity": None,
    "realm": None,
    "timestamp": None,
    "instance_id": None,
    "unique_instance_id": "",
    "host_name": None,
    "project_id": None,
    "namespace_id": None,
    "subject": None,
    "root_namespace_id": None,
    "correlation_id": None,
    "seat_ids": ["TODO"],
    "metadata": {},
}


class TestBillingEventsClient:
    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self):
        """Ensure Snowplow cache is reset between tests."""
        yield
        Snowplow.reset()

    @mock.patch("snowplow_tracker.Tracker.__init__")
    @mock.patch("snowplow_tracker.emitters.AsyncEmitter.__init__")
    def test_initialization(self, mock_emitter_init, mock_tracker_init):
        mock_emitter_init.return_value = None
        mock_tracker_init.return_value = None

        BillingEventsClient(
            enabled=True,
            endpoint="https://billing.local",
            app_id="gitlab_ai_gateway",
            namespace="gl",
            batch_size=3,
            thread_count=2,
        )

        mock_emitter_init.assert_called_once()
        mock_tracker_init.assert_called_once()

        emitter_args = mock_emitter_init.call_args[1]
        assert emitter_args["batch_size"] == 3
        assert emitter_args["thread_count"] == 2
        assert emitter_args["endpoint"] == "https://billing.local"

        tracker_args = mock_tracker_init.call_args[1]
        assert tracker_args["app_id"] == "gitlab_ai_gateway"
        assert tracker_args["namespace"] == "gl"
        assert len(tracker_args["emitters"]) == 1

    @pytest.mark.parametrize(
        "event_type, unit_of_measure, quantity, metadata, category, kwargs",
        [
            (
                "ai_completion",
                "tokens",
                100.0,
                None,
                None,
                {},
            ),
            (
                "code_suggestions",
                "requests",
                5.0,
                {"model": "claude-3", "feature": "completion"},
                "code_suggestions_category",
                {"project_id": 123, "namespace_id": 456},
            ),
            (
                "duo_chat",
                "messages",
                1.0,
                {"session_id": "session-123"},
                "chat_category",
                {"global_user_id": "user-789"},
            ),
        ],
    )
    def test_track_billing_event(
        self,
        event_type,
        unit_of_measure,
        quantity,
        metadata,
        category,
        kwargs,
    ):
        with (
            mock.patch("snowplow_tracker.Tracker.track") as mock_track,
            mock.patch(
                "snowplow_tracker.events.StructuredEvent.__init__"
            ) as mock_structured_event_init,
            mock.patch("lib.billing_events.client.uuid") as mock_uuid,
            mock.patch("lib.billing_events.client.datetime") as mock_datetime,
        ):
            mock_structured_event_init.return_value = None
            mock_uuid.uuid4.return_value.__str__ = mock.Mock(
                return_value="12345678-1234-5678-9012-123456789012"
            )
            mock_datetime.now.return_value.isoformat.return_value = (
                "2023-12-01T10:00:00"
            )

            event_context = EventContext(
                realm="user",
                instance_id="instance-123",
                host_name="gitlab.example.com",
                project_id=kwargs.get("project_id"),
                namespace_id=kwargs.get("namespace_id"),
                global_user_id=kwargs.get("global_user_id"),
                correlation_id="corr-123",
            )
            current_event_context.set(event_context)

            client = BillingEventsClient(
                enabled=True,
                endpoint="https://billing.local",
                app_id="gitlab_ai_gateway",
                namespace="gl",
                batch_size=3,
                thread_count=2,
            )

            client.track_billing_event(
                event_type=event_type,
                unit_of_measure=unit_of_measure,
                quantity=quantity,
                metadata=metadata,
                category=category,
            )

            mock_track.assert_called_once()
            mock_structured_event_init.assert_called_once()
            event_init_args = mock_structured_event_init.call_args[1]

            assert event_init_args["action"] == event_type

            context = event_init_args["context"][0]
            assert isinstance(context, SelfDescribingJson)
            assert context.schema == client.BILLING_CONTEXT_SCHEMA

            expected_context_data = {
                **BASE_BILLING_CONTEXT_SCHEMA,
                "event_id": "12345678-1234-5678-9012-123456789012",
                "event_type": event_type,
                "unit_of_measure": unit_of_measure,
                "quantity": quantity,
                "realm": "user",
                "timestamp": "2023-12-01T10:00:00",
                "instance_id": "instance-123",
                "host_name": "gitlab.example.com",
                "project_id": kwargs.get("project_id"),
                "namespace_id": kwargs.get("namespace_id"),
                "subject": kwargs.get("global_user_id"),
                "correlation_id": "corr-123",
                "metadata": metadata or {},
            }

            assert context.data == expected_context_data

    def test_track_billing_event_disabled_client(self):
        client = BillingEventsClient(
            enabled=False,
            endpoint="https://billing.local",
            app_id="gitlab_ai_gateway",
            namespace="gl",
            batch_size=3,
            thread_count=2,
        )

        client.track_billing_event(
            event_type="ai_completion",
            unit_of_measure="tokens",
            quantity=100.0,
        )

    def test_track_billing_event_negative_quantity(self):
        with (
            mock.patch("snowplow_tracker.Tracker.__init__") as mock_tracker_init,
            mock.patch(
                "snowplow_tracker.emitters.AsyncEmitter.__init__"
            ) as mock_emitter_init,
        ):
            mock_emitter_init.return_value = None
            mock_tracker_init.return_value = None

            client = BillingEventsClient(
                enabled=True,
                endpoint="https://billing.local",
                app_id="gitlab_ai_gateway",
                namespace="gl",
                batch_size=3,
                thread_count=2,
            )

            client.track_billing_event(
                event_type="ai_completion",
                unit_of_measure="tokens",
                quantity=-100.0,
            )

    def test_track_billing_event_with_empty_metadata(self):
        with (
            mock.patch("snowplow_tracker.Tracker.track") as mock_track,
            mock.patch(
                "snowplow_tracker.events.StructuredEvent.__init__"
            ) as mock_structured_event_init,
            mock.patch("lib.billing_events.client.uuid") as mock_uuid,
            mock.patch("lib.billing_events.client.datetime") as mock_datetime,
        ):
            mock_structured_event_init.return_value = None
            mock_uuid.uuid4.return_value.__str__ = mock.Mock(
                return_value="12345678-1234-5678-9012-123456789012"
            )
            mock_datetime.now.return_value.isoformat.return_value = (
                "2023-12-01T10:00:00"
            )

            current_event_context.set(EventContext())

            client = BillingEventsClient(
                enabled=True,
                endpoint="https://billing.local",
                app_id="gitlab_ai_gateway",
                namespace="gl",
                batch_size=3,
                thread_count=2,
            )

            client.track_billing_event(
                event_type="ai_completion",
                unit_of_measure="tokens",
                quantity=100.0,
                metadata=None,
            )

            mock_track.assert_called_once()
            event_init_args = mock_structured_event_init.call_args[1]
            context = event_init_args["context"][0]

            assert context.data["metadata"] == {}

    def test_billing_event_context_creation_with_internal_context(self):
        with (
            mock.patch("snowplow_tracker.Tracker.track") as mock_track,
            mock.patch(
                "snowplow_tracker.events.StructuredEvent.__init__"
            ) as mock_structured_event_init,
            mock.patch("lib.billing_events.client.uuid") as mock_uuid,
            mock.patch("lib.billing_events.client.datetime") as mock_datetime,
        ):
            mock_structured_event_init.return_value = None
            mock_uuid.uuid4.return_value.__str__ = mock.Mock(
                return_value="testeventid1-2300-0000-0000-000000000000"
            )
            mock_datetime.now.return_value.isoformat.return_value = (
                "2023-12-01T15:30:00"
            )

            internal_context = EventContext(
                environment="production",
                realm="project",
                instance_id="gitlab-instance-456",
                host_name="gitlab.company.com",
                project_id=789,
                namespace_id=101,
                global_user_id="user-456",
                correlation_id="request-789",
            )
            current_event_context.set(internal_context)

            client = BillingEventsClient(
                enabled=True,
                endpoint="https://billing.local",
                app_id="gitlab_ai_gateway",
                namespace="gl",
                batch_size=3,
                thread_count=2,
            )

            client.track_billing_event(
                event_type="duo_workflow",
                unit_of_measure="executions",
                quantity=1.0,
                metadata={"workflow_type": "code_review"},
            )

            mock_track.assert_called_once()
            event_init_args = mock_structured_event_init.call_args[1]
            context = event_init_args["context"][0]

            billing_data = context.data

            # Verify that internal context data is properly mapped to billing context
            assert billing_data["event_type"] == "duo_workflow"
            assert billing_data["unit_of_measure"] == "executions"
            assert billing_data["quantity"] == 1.0
            assert billing_data["realm"] == "project"
            assert billing_data["instance_id"] == "gitlab-instance-456"
            assert billing_data["host_name"] == "gitlab.company.com"
            assert billing_data["project_id"] == 789
            assert billing_data["namespace_id"] == 101
            assert billing_data["subject"] == "user-456"
            assert billing_data["correlation_id"] == "request-789"
            assert billing_data["metadata"] == {"workflow_type": "code_review"}
            assert billing_data["timestamp"] == "2023-12-01T15:30:00"
            assert (
                billing_data["event_id"] == "testeventid1-2300-0000-0000-000000000000"
            )
