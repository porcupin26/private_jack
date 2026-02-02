"""Jackery Device Data Parser Module."""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

_LOGGER = logging.getLogger(__name__)


@dataclass
class PortableDeviceStatus:
    """Status data for Jackery Portable devices."""
    bls: int = 0
    rb: int = 0
    bs: int = 0
    bt: int = 0
    ip: int = 0
    it: int = 0
    acip: int = 0
    cip: int = 0
    op: int = 0
    ot: int = 0
    acps: int = 0
    acov: int = 0
    acov1: int = 0
    acohz: int = 0
    acpss: int = 0
    acpsp: int = 0
    odc: int = 0
    odcu: int = 0
    odcc: int = 0
    oac: int = 0
    iac: int = 0
    idc: int = 0
    odct: int = 0
    odcut: int = 0
    odcct: int = 0
    oact: int = 0
    lm: int = 0
    pm: int = 0
    pmb: int = 0
    cs: int = 0
    lps: int = 0
    ast: int = 0
    sltb: int = 0
    sfc: int = 0
    ups: int = 0
    ec: int = 0
    ta: int = 0
    wss: int = 0
    en: int = 0
    dt: int = 0
    dl: int = 0
    cl: int = 0
    bc: int = 0
    tt: int = 0
    tp: int = 0
    ss: int = 0
    box: int = 0
    pc: int = 0
    pal: int = 0
    wname: Optional[str] = None
    wip: Optional[str] = None
    mac: Optional[str] = None
    wsig: int = 0
    csl: int = 0
    cst: int = 0
    csc: int = 0

    @property
    def battery_percent(self) -> int:
        return self.rb

    @property
    def battery_temperature_c(self) -> float:
        return self.bt / 10.0 if self.bt else 0.0

    @property
    def input_power_w(self) -> int:
        return self.ip

    @property
    def output_power_w(self) -> int:
        return self.op

    @property
    def ac_output_enabled(self) -> bool:
        return self.oac == 1

    @property
    def dc_output_enabled(self) -> bool:
        return self.odc == 1

    @property
    def dc_usb_enabled(self) -> bool:
        return self.odcu == 1

    @property
    def dc_car_enabled(self) -> bool:
        return self.odcc == 1

    @property
    def ups_enabled(self) -> bool:
        return self.ups == 1

    @property
    def super_charge_enabled(self) -> bool:
        return self.sfc == 1


@dataclass
class BoxDeviceStatus:
    """Status data for Jackery Box (stationary) devices."""
    ip: int = 0
    op: int = 0
    ot: int = 0
    rb: int = 0
    ds: int = 0
    dh: int = 0
    de: int = 0
    dg: int = 0
    pss: int = 0
    rc: int = 0
    dt: int = 0
    ddt: int = 0
    ups: int = 0
    ps: int = 0
    pst: int = 0
    en: int = 0

    @property
    def battery_percent(self) -> int:
        return self.rb

    @property
    def ups_enabled(self) -> bool:
        return self.ups == 1


class DeviceDataParser:
    """Parser for Jackery device data responses."""

    def __init__(self, device_type: str = "portable"):
        self.device_type = device_type

    def parse_response(self, data: Dict[str, Any]) -> Any:
        if self.device_type == "box":
            return self._parse_box_status(data)
        return self._parse_portable_status(data)

    def _parse_portable_status(self, data: Dict[str, Any]) -> PortableDeviceStatus:
        status = PortableDeviceStatus()
        field_mapping = {
            'bls': 'bls', 'ip': 'ip', 'it': 'it', 'op': 'op', 'ot': 'ot',
            'pal': 'pal', 'rb': 'rb', 'bs': 'bs', 'bt': 'bt',
            'acip': 'acip', 'cip': 'cip', 'acps': 'acps', 'acov': 'acov',
            'acohz': 'acohz', 'ec': 'ec', 'ta': 'ta', 'pm': 'pm', 'pmb': 'pmb',
            'odc': 'odc', 'odcu': 'odcu', 'odcc': 'odcc', 'oac': 'oac',
            'iac': 'iac', 'idc': 'idc', 'lm': 'lm', 'acpss': 'acpss',
            'acpsp': 'acpsp', 'wss': 'wss', 'cs': 'cs', 'lps': 'lps',
            'ast': 'ast', 'sltb': 'sltb', 'sfc': 'sfc', 'ups': 'ups',
            'acov1': 'acov1', 'tt': 'tt', 'tp': 'tp', 'ss': 'ss',
            'box': 'box', 'pc': 'pc', 'en': 'en', 'dt': 'dt',
            'dl': 'dl', 'cl': 'cl', 'bc': 'bc',
            'odct': 'odct', 'odcut': 'odcut', 'odcct': 'odcct', 'oact': 'oact',
            'csl': 'csl', 'cst': 'cst', 'csc': 'csc',
            'wname': 'wname', 'wip': 'wip', 'mac': 'mac', 'wsig': 'wsig',
        }
        for json_key, attr_name in field_mapping.items():
            if json_key in data:
                setattr(status, attr_name, data[json_key])
        return status

    def _parse_box_status(self, data: Dict[str, Any]) -> BoxDeviceStatus:
        status = BoxDeviceStatus()
        field_mapping = {
            'ip': 'ip', 'op': 'op', 'ot': 'ot', 'rb': 'rb',
            'ds': 'ds', 'dh': 'dh', 'de': 'de', 'dg': 'dg',
            'pss': 'pss', 'rc': 'rc', 'dt': 'dt', 'ddt': 'ddt',
            'ups': 'ups', 'ps': 'ps', 'pst': 'pst', 'en': 'en',
        }
        for json_key, attr_name in field_mapping.items():
            if json_key in data:
                setattr(status, attr_name, data[json_key])
        return status


def format_status(status: PortableDeviceStatus) -> str:
    """Format device status for display."""
    lines = [
        f"Battery: {status.battery_percent}% ({status.battery_temperature_c:.1f}C)",
        f"Input: {status.input_power_w}W  Output: {status.output_power_w}W",
        f"AC: {'ON' if status.ac_output_enabled else 'OFF'}  "
        f"DC: {'ON' if status.dc_output_enabled else 'OFF'}  "
        f"USB: {'ON' if status.dc_usb_enabled else 'OFF'}  "
        f"Car: {'ON' if status.dc_car_enabled else 'OFF'}  "
        f"UPS: {'ON' if status.ups_enabled else 'OFF'}",
    ]
    return "\n".join(lines)
