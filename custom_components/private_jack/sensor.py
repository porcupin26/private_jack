"""Sensor platform for Private Jack integration."""

import logging
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
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

# Sensors shared by both portable and box devices
COMMON_SENSOR_DESCRIPTIONS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="rb",
        translation_key="battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
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
]

# Sensors only for portable devices
PORTABLE_SENSOR_DESCRIPTIONS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="bt",
        translation_key="battery_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
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
        key="_solar_input",
        translation_key="solar_input_power",
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

# Sensors only for box (stationary) devices
BOX_SENSOR_DESCRIPTIONS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="ds",
        translation_key="solar_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="dh",
        translation_key="high_pv_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="de",
        translation_key="grid_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="dg",
        translation_key="generator_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
]

# Keys that need value transformation
VALUE_TRANSFORMS = {
    "bt": lambda v: round(v / 10.0, 1) if v else 0.0,
    "acov": lambda v: round(v / 10.0, 1) if v else 0.0,
}


_PORTABLE_KEYS = {d.key for d in PORTABLE_SENSOR_DESCRIPTIONS}
_BOX_KEYS = {d.key for d in BOX_SENSOR_DESCRIPTIONS}

ALL_SENSOR_DESCRIPTIONS = (
    COMMON_SENSOR_DESCRIPTIONS
    + PORTABLE_SENSOR_DESCRIPTIONS
    + BOX_SENSOR_DESCRIPTIONS
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Private Jack sensors from a config entry."""
    coordinator: JackeryBleCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Determine which keys are non-native to this device type
    if coordinator.device_type == "box":
        disabled_keys = _PORTABLE_KEYS
    else:
        disabled_keys = _BOX_KEYS

    entities = [
        JackeryBleSensor(
            coordinator, description, config_entry,
            enabled_default=description.key not in disabled_keys,
        )
        for description in ALL_SENSOR_DESCRIPTIONS
    ]
    entities.append(JackeryBleSignalSensor(coordinator, config_entry))
    async_add_entities(entities)


class JackeryBleSensor(CoordinatorEntity[JackeryBleCoordinator], SensorEntity):
    """Representation of a Jackery BLE sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JackeryBleCoordinator,
        description: SensorEntityDescription,
        config_entry: ConfigEntry,
        enabled_default: bool = True,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_entity_registry_enabled_default = enabled_default
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
        # Computed sensor: solar input = total input - AC input
        if key == "_solar_input":
            ip = self.coordinator.data.get("ip")
            acip = self.coordinator.data.get("acip")
            if ip is not None and acip is not None:
                return max(ip - acip, 0)
            return None
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


def _connected_via(address: str) -> str | None:
    """Return the source (adapter or proxy MAC) holding the BLE connection, if known."""
    # habluetooth exposes connection-slot allocations only through its manager; guard the
    # lookup so an internal API change can never break the sensor platform.
    try:
        from habluetooth import get_manager

        for allocation in get_manager().async_current_allocations() or []:
            if address in (allocation.allocated or []):
                return allocation.source
    except Exception:  # noqa: BLE001
        return None
    return None


class JackeryBleSignalSensor(CoordinatorEntity[JackeryBleCoordinator], SensorEntity):
    """Bluetooth signal strength of the device, as heard by Home Assistant's radios.

    A connected Jackery stops advertising, and Home Assistant drops it from each radio's
    advertisement history a few minutes later, so the readings taken at the last
    (re)connect are cached and reported while the device keeps responding.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "bluetooth_signal"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: JackeryBleCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._address = config_entry.data[CONF_DEVICE_ADDRESS]
        self._attr_unique_id = f"{self._address}_bluetooth_signal"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._address)},
            "name": config_entry.data.get(CONF_DEVICE_NAME, "Jackery"),
            "manufacturer": "Jackery",
            "model": f"Model {coordinator.model_code}" if coordinator.model_code else "Unknown",
        }
        self._per_source: dict[str, int] = {}

    def _rssi_by_source(self) -> dict[str, int]:
        """Return RSSI per radio, refreshed when a new advertisement is heard."""
        if self.hass is not None:
            fresh = {
                device.scanner.name: device.advertisement.rssi
                for device in bluetooth.async_scanner_devices_by_address(
                    self.hass, self._address, connectable=True
                )
                if isinstance(device.advertisement.rssi, int)
                and device.advertisement.rssi > -127
            }
            # Radios expire the device one at a time; a subset of the snapshot is not news.
            if fresh and not fresh.items() <= self._per_source.items():
                self._per_source = fresh
        return self._per_source

    @property
    def native_value(self) -> int | None:
        """Return the strongest RSSI any radio last heard from the device."""
        per_source = self._rssi_by_source()
        return max(per_source.values()) if per_source else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return which radio heard the device best and which one holds the link."""
        per_source = self._rssi_by_source()
        if not per_source:
            return None
        via = _connected_via(self._address)
        scanner = bluetooth.async_scanner_by_source(self.hass, via) if via else None
        return {
            "best_source": max(per_source, key=per_source.get),
            "connected_via": scanner.name if scanner else via,
            "rssi_by_source": per_source,
        }

    @property
    def available(self) -> bool:
        """Return True while the device responds and a reading exists."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and bool(self._rssi_by_source())
        )
