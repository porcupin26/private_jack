"""Config flow for Private Jack integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SN,
    CONF_DEVICE_TYPE,
    CONF_ENCRYPTION_KEY,
    CONF_MODEL_CODE,
    DEFAULT_SCAN_TIMEOUT,
)
from .lib.ble_client import scan_devices

_LOGGER = logging.getLogger(__name__)


class PrivateJackConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Private Jack."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_devices: dict[str, dict[str, Any]] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - scan for devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input["device"]
            device_info = self._discovered_devices[address]

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=device_info[CONF_DEVICE_NAME],
                data={
                    CONF_DEVICE_ADDRESS: address,
                    CONF_DEVICE_NAME: device_info[CONF_DEVICE_NAME],
                    CONF_DEVICE_SN: device_info.get(CONF_DEVICE_SN, ""),
                    CONF_DEVICE_TYPE: device_info[CONF_DEVICE_TYPE],
                    CONF_ENCRYPTION_KEY: device_info.get(CONF_ENCRYPTION_KEY),
                    CONF_MODEL_CODE: device_info.get(CONF_MODEL_CODE),
                },
            )

        # Scan for devices
        try:
            devices = await scan_devices(timeout=DEFAULT_SCAN_TIMEOUT)
        except Exception as e:
            _LOGGER.error("BLE scan failed: %s", e)
            errors["base"] = "scan_failed"
            devices = []

        if not devices and not errors:
            errors["base"] = "no_devices_found"

        self._discovered_devices = {}
        device_options = {}

        for device in devices:
            self._discovered_devices[device.address] = {
                CONF_DEVICE_NAME: device.name,
                CONF_DEVICE_SN: device.device_sn,
                CONF_DEVICE_TYPE: device.device_type,
                CONF_ENCRYPTION_KEY: device.encryption_key,
                CONF_MODEL_CODE: device.model_code,
            }
            label = f"{device.name} ({device.address})"
            if device.device_sn:
                label += f" - SN:{device.device_sn}"
            device_options[device.address] = label

        if not device_options:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("device"): vol.In(device_options)}
            ),
            errors=errors,
        )
