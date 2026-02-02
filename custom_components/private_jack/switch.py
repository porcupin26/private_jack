"""Switch platform for Private Jack integration."""

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DEVICE_ADDRESS, CONF_DEVICE_NAME
from .coordinator import JackeryBleCoordinator
from .lib.commands import CommandBuilder

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class JackerySwitchEntityDescription(SwitchEntityDescription):
    """Describes a Jackery switch entity."""

    state_key: str
    command_on: Callable[[CommandBuilder], str]
    command_off: Callable[[CommandBuilder], str]


SWITCH_DESCRIPTIONS: list[JackerySwitchEntityDescription] = [
    JackerySwitchEntityDescription(
        key="ac_output",
        translation_key="ac_output",
        icon="mdi:power-plug",
        state_key="oac",
        command_on=lambda cb: cb.set_ac_output(True),
        command_off=lambda cb: cb.set_ac_output(False),
    ),
    JackerySwitchEntityDescription(
        key="dc_output",
        translation_key="dc_output",
        icon="mdi:car-battery",
        state_key="odc",
        command_on=lambda cb: cb.set_dc_output(True),
        command_off=lambda cb: cb.set_dc_output(False),
    ),
    JackerySwitchEntityDescription(
        key="usb_output",
        translation_key="usb_output",
        icon="mdi:usb",
        state_key="odcu",
        command_on=lambda cb: cb.set_dc_usb_output(True),
        command_off=lambda cb: cb.set_dc_usb_output(False),
    ),
    JackerySwitchEntityDescription(
        key="car_output",
        translation_key="car_output",
        icon="mdi:car-electric-outline",
        state_key="odcc",
        command_on=lambda cb: cb.set_dc_car_output(True),
        command_off=lambda cb: cb.set_dc_car_output(False),
    ),
    JackerySwitchEntityDescription(
        key="ups_mode",
        translation_key="ups_mode",
        icon="mdi:battery-charging",
        state_key="ups",
        command_on=lambda cb: cb.set_ups_mode(True),
        command_off=lambda cb: cb.set_ups_mode(False),
    ),
    JackerySwitchEntityDescription(
        key="super_charge",
        translation_key="super_charge",
        icon="mdi:lightning-bolt",
        state_key="sfc",
        command_on=lambda cb: cb.set_super_charge(True),
        command_off=lambda cb: cb.set_super_charge(False),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Private Jack switches from a config entry."""
    coordinator: JackeryBleCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        JackeryBleSwitch(coordinator, description, config_entry)
        for description in SWITCH_DESCRIPTIONS
    ]
    async_add_entities(entities)


class JackeryBleSwitch(CoordinatorEntity[JackeryBleCoordinator], SwitchEntity):
    """Representation of a Jackery BLE switch."""

    entity_description: JackerySwitchEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JackeryBleCoordinator,
        description: JackerySwitchEntityDescription,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{config_entry.data[CONF_DEVICE_ADDRESS]}_{description.key}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.data[CONF_DEVICE_ADDRESS])},
            "name": config_entry.data.get(CONF_DEVICE_NAME, "Jackery"),
            "manufacturer": "Jackery",
            "model": f"Model {coordinator.model_code}" if coordinator.model_code else "Unknown",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.state_key)
        if value is None:
            return None
        return value == 1

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        cmd = self.entity_description.command_on(self.coordinator.command_builder)
        await self.coordinator.send_control_command(cmd)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        cmd = self.entity_description.command_off(self.coordinator.command_builder)
        await self.coordinator.send_control_command(cmd)
