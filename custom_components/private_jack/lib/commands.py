"""Jackery BLE Command Builder Module."""

import json
import time
from enum import IntEnum


def compact_json(obj) -> str:
    """Encode object to compact JSON string (no spaces)."""
    return json.dumps(obj, separators=(',', ':'))


class ActionId(IntEnum):
    """Command action IDs."""
    OUTPUT_DC = 1
    OUTPUT_DC_USB = 2
    OUTPUT_DC_CAR = 3
    OUTPUT_AC = 4
    INPUT_AC = 5
    INPUT_DC = 6
    LIGHT_MODE = 7
    SCREEN_TIME = 8
    AUTO_SHUTDOWN = 9
    CHARGE_MODEL = 10
    BATTERY_MODEL = 11
    POWER_MODE = 12
    SUPER_CHARGE = 13
    UPS_MODE = 14
    TIME_SYNC = 15
    QUERY_STRATEGY = 16
    INSERT_STRATEGY = 17
    UPDATE_STRATEGY = 18
    DELETE_STRATEGY = 19
    QUERY_CURRENT = 20
    DEVICE_TYPE = 21
    DEVICE_ENABLE = 22
    BATTERY_BOUNDARY = 23
    OUTPUT_AC_TIME = 24
    OUTPUT_DC_TIME = 25
    OUTPUT_DC_USB_TIME = 26
    OUTPUT_DC_CAR_TIME = 27
    CHARGE_SCHEDULE = 28
    POWER_PACK_LIST = 248
    ELECTRICITY_DATA = 249
    WIFI_LIST = 251
    DEVICE_PROPERTY = 252
    WIFI_CONNECT = 253
    OTA_VERSION = 254


class MsgType(IntEnum):
    """BLE message types."""
    QUERY = 1
    SET_WIFI = 2
    DEVICE_PROPERTY = 3
    SET_CONTROL = 4
    FIRMWARE_INFO = 5
    FIRMWARE_PAGE = 6
    POWER_PACK = 7
    TIME_SYNC = 8


class CommandBuilder:
    """Builds BLE commands for Jackery devices."""

    PREFIX_PORTABLE = "DFEC00"
    PREFIX_BOX = "DFED00"

    def __init__(self, device_type: str = "portable"):
        self.device_type = device_type
        self.prefix = self.PREFIX_BOX if device_type == "box" else self.PREFIX_PORTABLE

    def _to_hex_byte(self, value: int) -> str:
        return format(value & 0xFF, '02x')

    def _body_to_hex(self, body: str) -> str:
        return body.encode('utf-8').hex()

    def build_command(self, action_id: int, msg_type: int, body: str = "") -> str:
        body_hex = self._body_to_hex(body) if body else ""
        body_len = len(body_hex) // 2
        command = (
            self.prefix
            + self._to_hex_byte(action_id)
            + self._to_hex_byte(msg_type)
            + self._to_hex_byte(body_len)
            + body_hex
        )
        return command.upper()

    def query_device_property(self) -> str:
        return self.build_command(ActionId.DEVICE_PROPERTY, MsgType.DEVICE_PROPERTY, "")

    def set_dc_output(self, enabled: bool) -> str:
        return self.build_command(ActionId.OUTPUT_DC, MsgType.SET_CONTROL, compact_json({"odc": 1 if enabled else 0}))

    def set_dc_usb_output(self, enabled: bool) -> str:
        return self.build_command(ActionId.OUTPUT_DC_USB, MsgType.SET_CONTROL, compact_json({"odcu": 1 if enabled else 0}))

    def set_dc_car_output(self, enabled: bool) -> str:
        return self.build_command(ActionId.OUTPUT_DC_CAR, MsgType.SET_CONTROL, compact_json({"odcc": 1 if enabled else 0}))

    def set_ac_output(self, enabled: bool) -> str:
        return self.build_command(ActionId.OUTPUT_AC, MsgType.SET_CONTROL, compact_json({"oac": 1 if enabled else 0}))

    def set_light_mode(self, mode: int) -> str:
        return self.build_command(ActionId.LIGHT_MODE, MsgType.SET_CONTROL, compact_json({"lm": mode}))

    def set_light_off(self) -> str:
        return self.set_light_mode(0)

    def set_light_low(self) -> str:
        return self.set_light_mode(1)

    def set_light_high(self) -> str:
        return self.set_light_mode(2)

    def set_light_sos(self) -> str:
        return self.set_light_mode(3)

    def set_screen_timeout(self, minutes: int) -> str:
        return self.build_command(ActionId.SCREEN_TIME, MsgType.SET_CONTROL, compact_json({"slt": minutes}))

    def set_screen_always_on(self) -> str:
        return self.set_screen_timeout(0)

    def set_screen_timeout_2min(self) -> str:
        return self.set_screen_timeout(2)

    def set_screen_timeout_2hr(self) -> str:
        return self.set_screen_timeout(120)

    def set_ups_mode(self, enabled: bool) -> str:
        return self.build_command(ActionId.UPS_MODE, MsgType.SET_CONTROL, compact_json({"ups": 1 if enabled else 0}))

    def set_super_charge(self, enabled: bool) -> str:
        return self.build_command(ActionId.SUPER_CHARGE, MsgType.SET_CONTROL, compact_json({"sfc": 1 if enabled else 0}))

    def set_power_mode(self, mode: int) -> str:
        """Set energy saving auto-shutdown timer (minutes: 0/120/480/720/1440)."""
        return self.build_command(ActionId.POWER_MODE, MsgType.SET_CONTROL, compact_json({"pm": mode}))

    def set_charge_model(self, model: int) -> str:
        """Set charge mode (0=fast, 1=silent, 2=custom)."""
        return self.build_command(ActionId.CHARGE_MODEL, MsgType.SET_CONTROL, compact_json({"cs": model}))

    def set_battery_model(self, model: int) -> str:
        """Set battery save mode (0=full, 1=save 15-85%, 2=custom)."""
        return self.build_command(ActionId.BATTERY_MODEL, MsgType.SET_CONTROL, compact_json({"lps": model}))

    def set_battery_boundary(self, discharge_limit: int, charge_limit: int,
                            backup_capacity: int) -> str:
        body = compact_json({"dl": discharge_limit, "cl": charge_limit, "bc": backup_capacity})
        return self.build_command(ActionId.BATTERY_BOUNDARY, MsgType.SET_CONTROL, body)

    def sync_time(self, utc_offset: int = 0) -> str:
        timestamp = int(time.time())
        return self.build_command(ActionId.TIME_SYNC, MsgType.TIME_SYNC, compact_json({"ts": timestamp, "uo": utc_offset}))

    def connect_wifi(self, ssid: str, password: str) -> str:
        return self.build_command(ActionId.WIFI_CONNECT, MsgType.SET_WIFI, compact_json({"s": ssid, "p": password}))
