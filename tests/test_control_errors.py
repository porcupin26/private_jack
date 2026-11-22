"""Offline tests for Bluetooth control service errors."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import frame
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.private_jack import select, switch
from custom_components.private_jack.const import CONF_DEVICE_ADDRESS, CONF_DEVICE_NAME, DOMAIN
from custom_components.private_jack.coordinator import JackeryBleCoordinator
from custom_components.private_jack.lib.ble_client import JackeryBleClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def controls(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    frame.async_setup(hass)
    entry = SimpleNamespace(entry_id="test", data={
        CONF_DEVICE_ADDRESS: "00:00:00:00:00:01", CONF_DEVICE_NAME: "Test station",
    })
    coordinator = JackeryBleCoordinator(hass, entry.data)
    client = Mock(spec=JackeryBleClient, is_connected=True)
    client.send_command.return_value = None
    coordinator._client = client
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    entities = []
    await switch.async_setup_entry(hass, entry, entities.extend)
    await select.async_setup_entry(hass, entry, entities.extend)
    return {entity.entity_description.key: entity for entity in entities}, client


@pytest.mark.parametrize(("key", "method", "args"), [
    ("ac_output", "async_turn_on", ()),
    ("ac_output", "async_turn_off", ()),
    ("light_mode", "async_select_option", ("high",)),
])
async def test_service_reports_write_failure(controls, key, method, args):
    entities, client = controls
    failure = RuntimeError("Bluetooth write failed")
    client.send_command.side_effect = failure

    with pytest.raises(HomeAssistantError) as exc:
        await getattr(entities[key], method)(*args)

    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "control_send_failed"
    assert exc.value.translation_placeholders == {"device": "Test station"}
    assert exc.value.__cause__ is failure
    client.send_command.assert_awaited_once()
    client.send_command_collect_all.assert_not_awaited()


async def test_service_reports_connection_failure(controls, monkeypatch):
    entities, client = controls
    client.is_connected = False
    monkeypatch.setattr(
        "custom_components.private_jack.coordinator.async_ble_device_from_address",
        Mock(return_value=None),
    )

    with pytest.raises(HomeAssistantError) as exc:
        await entities["ac_output"].async_turn_on()

    assert exc.value.translation_key == "control_send_failed"
    assert isinstance(exc.value.__cause__, UpdateFailed)
    client.send_command.assert_not_awaited()


@pytest.mark.parametrize(("reported", "expected"), [(2, "high"), (1, "low")])
async def test_successful_write_refreshes_reported_state(controls, reported, expected):
    entities, client = controls
    light = entities["light_mode"]
    client.send_command_collect_all.return_value = [{"lm": reported}]

    await light.async_select_option("high")

    client.send_command.assert_awaited_once_with(
        light.coordinator.command_builder.set_light_mode(2), wait_response=False
    )
    client.send_command_collect_all.assert_awaited_once()
    assert light.current_option == expected
