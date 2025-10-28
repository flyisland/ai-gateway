import pytest

from ai_gateway.api.v1.proxy.request import track_billing_event


@pytest.mark.asyncio
async def test_track_billing_event(mock_request, billing_event_client):
    @track_billing_event
    async def dummy_func(*_args, **_kwargs):
        return "Success"

    await dummy_func(mock_request, billing_event_client=billing_event_client)

    billing_event_client.track_billing_event.assert_called_once_with(
        mock_request.user,
        event_type="",
        category="ai_gateway.api.v1.proxy.request",
        unit_of_measure="request",
        quantity=1,
    )


@pytest.mark.asyncio
async def test_track_billing_event_with_exception(mock_request, billing_event_client):
    @track_billing_event
    async def dummy_func(*_args, **_kwargs):
        raise ValueError

    with pytest.raises(ValueError):
        await dummy_func(mock_request, billing_event_client=billing_event_client)

    billing_event_client.track_billing_event.assert_not_called()
