"""Select platform for Private Jack integration."""

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_NAME,
    LIGHT_MODE_OPTIONS,
    CHARGE_MODE_OPTIONS,
    BATTERY_SAVE_OPTIONS,
    ENERGY_SAVING_OPTIONS,
)
from .coordinator import JackeryBleCoordinator
from .lib.commands import CommandBuilder

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class JackerySelectEntityDescription(SelectEntityDescription):
    """Describes a Jackery select entity."""

    state_key: str
    options_map: dict[str, int]
    command_fn: Callable[[CommandBuilder, int], str]


SELECT_DESCRIPTIONS: list[JackerySelectEntityDescription] = [
    JackerySelectEntityDescription(
        key="light_mode",
        translation_key="light_mode",
        icon="mdi:flashlight",
        state_key="lm",
        options_map=LIGHT_MODE_OPTIONS,
        command_fn=lambda cb, val: cb.set_light_mode(val),
    ),
    JackerySelectEntityDescription(
        key="charge_mode",
        translation_key="charge_mode",
        icon="mdi:battery-charging-outline",
        state_key="cs",
        options_map=CHARGE_MODE_OPTIONS,
        command_fn=lambda cb, val: cb.set_charge_model(val),
    ),
    JackerySelectEntityDescription(
        key="battery_save",
        translation_key="battery_save",
        icon="mdi:battery-heart-variant",
        state_key="lps",
        options_map=BATTERY_SAVE_OPTIONS,
        command_fn=lambda cb, val: cb.set_battery_model(val),
    ),
    JackerySelectEntityDescription(
        key="energy_saving",
        translation_key="energy_saving",
        icon="mdi:timer-outline",
        state_key="pm",
        options_map=ENERGY_SAVING_OPTIONS,
        command_fn=lambda cb, val: cb.set_power_mode(val),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Private Jack selects from a config entry."""
    coordinator: JackeryBleCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        JackeryBleSelect(coordinator, description, config_entry)
        for description in SELECT_DESCRIPTIONS
    ]
    async_add_entities(entities)


class JackeryBleSelect(CoordinatorEntity[JackeryBleCoordinator], SelectEntity):
    """Representation of a Jackery BLE select."""

    entity_description: JackerySelectEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JackeryBleCoordinator,
        description: JackerySelectEntityDescription,
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
        self._attr_options = list(description.options_map.keys())
        # Build reverse map (int value -> option label)
        self._value_to_option = {v: k for k, v in description.options_map.items()}

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.state_key)
        if value is None:
            return None
        return self._value_to_option.get(value)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        value = self.entity_description.options_map.get(option)
        if value is None:
            _LOGGER.warning("Unknown option: %s", option)
            return
        cmd = self.entity_description.command_fn(
            self.coordinator.command_builder, value
        )
        await self.coordinator.send_control_command(cmd)
