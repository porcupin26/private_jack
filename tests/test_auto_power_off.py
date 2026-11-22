"""Offline tests for the auto power-off select."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import frame

from custom_components.private_jack.const import CONF_DEVICE_ADDRESS, DOMAIN
from custom_components.private_jack.coordinator import JackeryBleCoordinator
from custom_components.private_jack.lib.ble_client import JackeryBleClient
from custom_components.private_jack.select import async_setup_entry

pytestmark = pytest.mark.asyncio

OPTIONS = [(0, "Never"), (120, "2 hours"), (480, "8 hours"), (720, "12 hours"), (1440, "24 hours")]


async def setup_selects(tmp_path, status):
    hass = HomeAssistant(str(tmp_path))
    frame.async_setup(hass)
    entry = SimpleNamespace(entry_id="test", data={CONF_DEVICE_ADDRESS: "00:00:00:00:00:01"})
    coordinator = JackeryBleCoordinator(hass, entry.data)
    client = Mock(spec=JackeryBleClient, is_connected=True)
    coordinator._client = client
    coordinator.data = status
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    return {entity.entity_description.key: entity for entity in entities}, client


def assert_write(client, minutes):
    client.send_command.assert_awaited_once()
    packet = bytes.fromhex(client.send_command.await_args.args[0])
    assert packet[3:5] == bytes([9, 4])  # Auto shutdown, SET_CONTROL
    assert json.loads(packet[6:]) == {"ast": minutes}


async def test_setup_without_ast(tmp_path):
    selects, _ = await setup_selects(tmp_path, {"pm": 720})
    assert "auto_power_off" not in selects
    assert selects["energy_saving"].current_option == "12 hours"


async def test_current_option_tracks_status(tmp_path):
    selects, _ = await setup_selects(tmp_path, {"ast": 0, "pm": 720})
    timer = selects["auto_power_off"]
    assert timer.options == selects["energy_saving"].options == [label for _, label in OPTIONS]
    for minutes, label in OPTIONS:
        timer.coordinator.data = {"ast": minutes, "pm": 720}
        assert timer.current_option == label
    for status in ({"ast": 123, "pm": 0}, {"pm": 0}, None):
        timer.coordinator.data = status
        assert timer.current_option is None


@pytest.mark.parametrize(("minutes", "label"), OPTIONS)
async def test_write_and_confirm(tmp_path, minutes, label):
    selects, client = await setup_selects(tmp_path, {"ast": 120 if minutes == 0 else 0, "pm": 720})
    timer = selects["auto_power_off"]
    client.send_command_collect_all.return_value = [{"ast": minutes, "pm": 720}]

    await timer.async_select_option(label)

    assert_write(client, minutes)
    assert [name for name, _, _ in client.method_calls] == ["send_command", "send_command_collect_all"]
    query = bytes.fromhex(client.send_command_collect_all.await_args.args[0])
    assert query[3:5] == bytes([252, 3])  # Device property status query
    assert timer.current_option == label
    assert selects["energy_saving"].current_option == "12 hours"


async def test_concurrent_selections_confirm_their_own_writes(tmp_path):
    selects, client = await setup_selects(tmp_path, {"ast": 0})
    timer = selects["auto_power_off"]
    station = {"ast": 0}
    first_written = asyncio.Event()
    second_started = asyncio.Event()
    readings = []

    def write(command_hex, **kwargs):
        station.update(json.loads(bytes.fromhex(command_hex)[6:]))
        first_written.set()

    async def read_status(*args, **kwargs):
        await second_started.wait()
        readings.append(station["ast"])
        return [station.copy()]

    client.send_command.side_effect = write
    client.send_command_collect_all.side_effect = read_status

    async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
        tasks.create_task(timer.async_select_option("2 hours"))
        await first_written.wait()
        # Start the competing selection before the first can confirm its write.
        second_started.set()
        await timer.async_select_option("8 hours")

    assert readings == [120, 480]
    assert timer.current_option == "8 hours"


@pytest.mark.parametrize("readback", [[{"ast": 120, "pm": 0}], [{"pm": 0}], []],
                         ids=["mismatch", "missing-ast", "failed-refresh"])
async def test_reject_unconfirmed_write(tmp_path, readback):
    selects, client = await setup_selects(tmp_path, {"ast": 0, "pm": 720})
    timer = selects["auto_power_off"]
    # A matching cached value is not confirmation, even during the refresh cooldown.
    client.send_command_collect_all.return_value = [timer.coordinator.data]
    await timer.coordinator.async_request_refresh()
    client.reset_mock()
    client.send_command_collect_all.return_value = readback

    with pytest.raises(HomeAssistantError):
        await timer.async_select_option("Never")

    assert_write(client, 0)
    client.send_command_collect_all.assert_awaited_once()
    if readback:
        assert timer.current_option == ("2 hours" if "ast" in readback[0] else None)


async def test_send_failure_is_reported(tmp_path):
    selects, client = await setup_selects(tmp_path, {"ast": 0, "pm": 720})
    client.send_command.side_effect = RuntimeError("BLE write failed")

    with pytest.raises(HomeAssistantError):
        await selects["auto_power_off"].async_select_option("Never")

    assert_write(client, 0)
