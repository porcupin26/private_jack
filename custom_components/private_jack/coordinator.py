"""DataUpdateCoordinator for Private Jack."""

import asyncio
import json
import logging
import time
from datetime import timedelta
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_DEVICE_ADDRESS,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_ENCRYPTION_KEY,
    CONF_MODEL_CODE,
    DEFAULT_UPDATE_INTERVAL,
)
from .lib.ble_client import JackeryBleClient, JackeryDevice
from .lib.commands import CommandBuilder
from .lib.parser import DeviceDataParser

_LOGGER = logging.getLogger(__name__)


class JackeryBleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that manages BLE connection and polling for a Jackery device."""

    def __init__(self, hass: HomeAssistant, config_data: dict) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Jackery {config_data.get(CONF_DEVICE_NAME, 'Unknown')}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self._address: str = config_data[CONF_DEVICE_ADDRESS]
        self._device_name: str = config_data.get(CONF_DEVICE_NAME, "Jackery")
        self._device_type: str = config_data.get(CONF_DEVICE_TYPE, "portable")
        self._encryption_key: Optional[str] = config_data.get(CONF_ENCRYPTION_KEY)
        self._model_code: Optional[int] = config_data.get(CONF_MODEL_CODE)

        self._client: Optional[JackeryBleClient] = None
        self._command_builder = CommandBuilder(self._device_type)
        self._parser = DeviceDataParser(self._device_type)
        self._connected = False

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def device_address(self) -> str:
        return self._address

    @property
    def model_code(self) -> Optional[int]:
        return self._model_code

    @property
    def command_builder(self) -> CommandBuilder:
        return self._command_builder

    async def _ensure_connected(self) -> bool:
        """Ensure BLE connection is active, reconnecting if needed."""
        if self._client and self._client.is_connected:
            return True

        _LOGGER.debug("Connecting to %s (%s)", self._device_name, self._address)

        self._client = JackeryBleClient(
            encryption_key=self._encryption_key,
            device_type=self._device_type,
            key_is_base64=True if self._encryption_key else False,
            model_code=self._model_code,
        )

        success = await self._client.connect_by_address(self._address)
        if not success:
            self._connected = False
            raise UpdateFailed(f"Failed to connect to {self._device_name}")

        self._connected = True

        # Sync time after connecting
        try:
            utc_offset = -time.timezone if time.daylight == 0 else -time.altzone
            cmd = self._command_builder.sync_time(utc_offset)
            await self._client.send_command(cmd, wait_response=False)
        except Exception as e:
            _LOGGER.debug("Time sync failed: %s", e)

        return True

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        try:
            await self._ensure_connected()
        except Exception as err:
            raise UpdateFailed(f"Connection failed: {err}") from err

        cmd = self._command_builder.query_device_property()

        try:
            responses = await self._client.send_command_collect_all(
                cmd, timeout=5.0, collect_time=2.0
            )
        except RuntimeError as err:
            self._connected = False
            raise UpdateFailed(f"Communication error: {err}") from err

        if not responses:
            raise UpdateFailed("No response from device")

        merged_data: dict[str, Any] = {}
        for response in responses:
            try:
                if isinstance(response, dict):
                    if "raw_hex" in response:
                        hex_data = response["raw_hex"]
                        ascii_data = bytes.fromhex(hex_data).decode('utf-8')
                        data = json.loads(ascii_data)
                        merged_data.update(data)
                    else:
                        # Filter out internal metadata keys
                        merged_data.update(
                            {k: v for k, v in response.items() if not k.startswith("_")}
                        )
                elif isinstance(response, str):
                    ascii_data = bytes.fromhex(response).decode('utf-8')
                    data = json.loads(ascii_data)
                    merged_data.update(data)
            except Exception as e:
                _LOGGER.debug("Parse error for response: %s", e)

        if not merged_data:
            raise UpdateFailed("Could not parse device response")

        _LOGGER.debug("Device data: %s", merged_data)
        return merged_data

    async def send_control_command(self, command_hex: str) -> bool:
        """Send a control command to the device."""
        try:
            await self._ensure_connected()
            await self._client.send_command(command_hex, wait_response=False)
            await asyncio.sleep(0.5)
            # Refresh data after command
            await self.async_request_refresh()
            return True
        except Exception as e:
            _LOGGER.error("Failed to send command: %s", e)
            return False

    async def async_shutdown(self) -> None:
        """Disconnect on shutdown."""
        if self._client:
            await self._client.disconnect()
            self._client = None
            self._connected = False
