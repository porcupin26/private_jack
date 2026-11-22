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


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["connect_with_client", "connect", "connect_by_address"])
async def test_cancelling_setup_waits_for_disconnect(method):
    jackery = JackeryBleClient()
    client = Mock(spec=BleakClient, is_connected=True)
    client.start_notify.side_effect = RuntimeError("notify failed")
    disconnect_started = asyncio.Event()
    allow_disconnect = asyncio.Event()

    async def disconnect():
        disconnect_started.set()
        await allow_disconnect.wait()
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    device = JackeryDevice("Jackery", "00:00:00:00:00:01", -50, "portable", Mock())
    with patch(f"{JackeryBleClient.__module__}.BleakClient", return_value=client):
        if method == "connect_with_client":
            setup = jackery.connect_with_client(client)
        elif method == "connect":
            setup = jackery.connect(device, retries=1)
        else:
            setup = jackery.connect_by_address(device.address, retries=1)

        task = asyncio.create_task(setup)
        await asyncio.wait_for(disconnect_started.wait(), timeout=1)
        try:
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)  # Deliver each cancellation while disconnect is blocked.
                assert not task.done()
        finally:
            allow_disconnect.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    client.disconnect.assert_awaited_once()
    assert not client.is_connected
