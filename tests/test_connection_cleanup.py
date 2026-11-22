"""Connection setup should never leave a failed client holding the link."""

import asyncio
from unittest.mock import Mock, patch

import pytest
from bleak import BleakClient

from custom_components.private_jack.lib.ble_client import JackeryBleClient, JackeryDevice


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [RuntimeError("notify failed"), asyncio.CancelledError()])
async def test_failed_setup_releases_connected_client_and_can_retry(outcome):
    jackery = JackeryBleClient()
    first = Mock(spec=BleakClient, is_connected=True)
    first.start_notify.side_effect = outcome

    if isinstance(outcome, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await jackery.connect_with_client(first)
    else:
        assert not await jackery.connect_with_client(first)
    first.disconnect.assert_awaited_once()
    assert not jackery.is_connected

    second = Mock(spec=BleakClient, is_connected=True)
    assert await jackery.connect_with_client(second)
    second.start_notify.assert_awaited_once()
    second.disconnect.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("by_address", [False, True])
async def test_last_direct_connection_attempt_releases_client(by_address):
    jackery = JackeryBleClient()
    client = Mock(spec=BleakClient, is_connected=True)
    client.start_notify.side_effect = RuntimeError("notify failed")
    device = JackeryDevice("Jackery", "00:00:00:00:00:01", -50, "portable", Mock())

    with patch(f"{JackeryBleClient.__module__}.BleakClient", return_value=client):
        if by_address:
            assert not await jackery.connect_by_address(device.address, retries=1)
        else:
            assert not await jackery.connect(device, retries=1)
    client.disconnect.assert_awaited_once()
    assert not jackery.is_connected
