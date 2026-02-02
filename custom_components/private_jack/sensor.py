"""Sensor platform for Private Jack integration."""

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DEVICE_ADDRESS, CONF_DEVICE_NAME
from .coordinator import JackeryBleCoordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="rb",
        translation_key="battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="bt",
        translation_key="battery_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ip",
        translation_key="total_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="op",
        translation_key="total_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="acip",
        translation_key="ac_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="acps",
        translation_key="ac_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="cip",
        translation_key="dc_solar_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="acov",
        translation_key="ac_output_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="acohz",
        translation_key="ac_output_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm",
        translation_key="energy_saving",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-outline",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ec",
        translation_key="error_code",
        icon="mdi:alert-circle-outline",
    ),
]

# Keys that need value transformation
VALUE_TRANSFORMS = {
    "bt": lambda v: round(v / 10.0, 1) if v else 0.0,
    "acov": lambda v: round(v / 10.0, 1) if v else 0.0,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Private Jack sensors from a config entry."""
    coordinator: JackeryBleCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        JackeryBleSensor(coordinator, description, config_entry)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class JackeryBleSensor(CoordinatorEntity[JackeryBleCoordinator], SensorEntity):
    """Representation of a Jackery BLE sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JackeryBleCoordinator,
        description: SensorEntityDescription,
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
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        key = self.entity_description.key
        value = self.coordinator.data.get(key)
        if value is None:
            return None
        transform = VALUE_TRANSFORMS.get(key)
        if transform:
            return transform(value)
        return value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None
