"""Connection setup shared by polls and control commands."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.private_jack import coordinator as module


@pytest.fixture
def connection(monkeypatch):
    def init(self, hass, *args, **kwargs):
        self.hass = hass

    monkeypatch.setattr(module.DataUpdateCoordinator, "__init__", init)
    coordinator = module.JackeryBleCoordinator(Mock(), {module.CONF_DEVICE_ADDRESS: "test"})
    transport = Mock(spec=module.BleakClient, is_connected=True)
    establish = AsyncMock(return_value=transport)
    monkeypatch.setattr(module, "async_ble_device_from_address", Mock())
    monkeypatch.setattr(module, "establish_connection", establish)
    return coordinator, establish


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["establish", "notify"])
async def test_poll_waits_for_control_connection(connection, monkeypatch, stage):
    coordinator, establish = connection
    transport = establish.return_value
    paused = asyncio.Event()
    resume = asyncio.Event()

    async def pause(*args):
        paused.set()
        await resume.wait()
        return transport

    gate = establish if stage == "establish" else transport.start_notify
    gate.side_effect = pause
    collect = AsyncMock(return_value=[{"level": 50}])
    monkeypatch.setattr(module.JackeryBleClient, "send_command_collect_all", collect)
    monkeypatch.setattr(coordinator, "async_request_refresh", AsyncMock())

    async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
        control = tasks.create_task(coordinator.send_control_command("00"))
        await paused.wait()
        poll = tasks.create_task(coordinator._async_update_data())
        await asyncio.sleep(0)  # Let the poll reach connection setup.
        establish.assert_awaited_once()
        collect.assert_not_awaited()
        resume.set()

    assert control.result() is True
    assert poll.result() == {"level": 50}
    establish.assert_awaited_once()
    transport.start_notify.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [(RuntimeError, module.UpdateFailed), (asyncio.CancelledError, asyncio.CancelledError)],
)
async def test_retry_after_incomplete_setup(connection, error, expected):
    coordinator, establish = connection
    failed = establish.return_value
    failed.start_notify.side_effect = error
    retry = Mock(spec=module.BleakClient, is_connected=True)
    establish.side_effect = [failed, retry]

    async with asyncio.timeout(5):
        with pytest.raises(expected):
            await coordinator._ensure_connected()
        assert coordinator._client is None
        assert await coordinator._ensure_connected()

    retry.start_notify.assert_awaited_once()
