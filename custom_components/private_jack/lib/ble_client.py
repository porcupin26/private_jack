"""Jackery BLE Client Module for Home Assistant."""

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic

from .crypto import (
    BoxEncryption,
    PortableAESEncryption,
    PortableRC4Encryption,
    AutoDetectEncryption,
    EncryptionType,
)
from .crc import crc16

_LOGGER = logging.getLogger(__name__)

JACKERY_DEVICE_NAMES = ["HT", "JACKERY", "JK", "EXPLORER"]


class BleUUIDs:
    SERVICE_DATA = "0000bdee-0000-1000-8000-00805f9b34fb"
    SERVICE_HEARTBEAT = "0000bdff-0000-1000-8000-00805f9b34fb"
    CHAR_DATA_WRITE = "0000ee01-0000-1000-8000-00805f9b34fb"
    CHAR_DATA_NOTIFY = "0000ee02-0000-1000-8000-00805f9b34fb"
    CHAR_HEARTBEAT = "0000ff01-0000-1000-8000-00805f9b34fb"


@dataclass
class JackeryDevice:
    """Represents a discovered Jackery device."""
    name: str
    address: str
    rssi: int
    device_type: str
    ble_device: BLEDevice
    encryption_key: Optional[str] = None
    device_sn: Optional[str] = None
    model_code: Optional[int] = None
    manufacturer_data: Optional[Dict] = None
    service_data: Optional[Dict] = None

    def __str__(self):
        key_status = "key:YES" if self.encryption_key else "key:NO"
        sn_info = f" SN:{self.device_sn}" if self.device_sn else ""
        model_info = f" Model:{self.model_code}" if self.model_code else ""
        return f"{self.name} ({self.address}) - {self.device_type} [{key_status}] [RSSI: {self.rssi}]{sn_info}{model_info}"


class JackeryBleClient:
    """BLE client for communicating with Jackery solar generators."""

    def __init__(self, encryption_key: Optional[str] = None, device_type: str = "portable",
                 key_is_base64: bool = False, model_code: Optional[int] = None):
        self.client: Optional[BleakClient] = None
        self.device: Optional[JackeryDevice] = None
        self.encryption = None
        self.encryption_key = encryption_key
        self.key_is_base64 = key_is_base64
        self.device_type = device_type
        self.model_code = model_code
        self._notification_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._response_event: asyncio.Event = asyncio.Event()
        self._last_response: Optional[str] = None
        self._packet_buffer: dict = {}
        self._expected_packets: int = 0
        self._encryption_logged: bool = False

    async def scan(self, timeout: float = 10.0,
                   name_filter: Optional[str] = None) -> list[JackeryDevice]:
        """Scan for nearby Jackery devices."""
        devices_dict = {}

        def detection_callback(device: BLEDevice, advertisement_data):
            name = device.name or ""
            name_upper = name.upper()
            is_jackery = False
            if name_filter:
                is_jackery = name_filter.upper() in name_upper or name_upper == name_filter.upper()
            else:
                is_jackery = any(
                    name_upper.startswith(prefix) or prefix in name_upper
                    for prefix in JACKERY_DEVICE_NAMES
                )
            if is_jackery and device.address not in devices_dict:
                device_type = "box" if "BOX" in name_upper else "portable"
                mfr_data = dict(advertisement_data.manufacturer_data) if advertisement_data.manufacturer_data else None
                svc_data = dict(advertisement_data.service_data) if advertisement_data.service_data else None
                encryption_key = None
                device_sn = None
                model_code = None
                if mfr_data and svc_data:
                    encryption_key, device_sn, model_code = self._extract_key_from_advertisement(mfr_data, svc_data)
                rssi = advertisement_data.rssi if hasattr(advertisement_data, 'rssi') else -100
                jackery_device = JackeryDevice(
                    name=name, address=device.address, rssi=rssi,
                    device_type=device_type, ble_device=device,
                    encryption_key=encryption_key, device_sn=device_sn,
                    model_code=model_code, manufacturer_data=mfr_data,
                    service_data=svc_data,
                )
                devices_dict[device.address] = jackery_device

        scanner = BleakScanner(detection_callback=detection_callback)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        return list(devices_dict.values())

    def _extract_key_from_advertisement(self, manufacturer_data: Dict,
                                        service_data: Dict) -> tuple:
        """Extract encryption key from BLE advertisement data."""
        try:
            from .key_derivation import rc4_crypt, xor_with_byte, SALT_RC4, SALT_KEY
            import base64

            svc_uuid = BleUUIDs.SERVICE_DATA.lower()
            svc_bytes = None
            for uuid, data in service_data.items():
                if svc_uuid in str(uuid).lower():
                    svc_bytes = bytes(data)
                    break
            if not svc_bytes or len(svc_bytes) < 14:
                return None, None, None

            if not manufacturer_data:
                return None, None, None

            mfr_id, mfr_bytes = next(iter(manufacturer_data.items()))
            mfr_bytes = bytes(mfr_bytes)
            id_hex = format(mfr_id, '04x')
            id_swapped = id_hex[2:4] + id_hex[0:2]
            try:
                sn_part1 = bytes.fromhex(id_swapped[2:]).decode('utf-8', errors='ignore')
                sn_part2 = mfr_bytes.decode('utf-8', errors='ignore')
                device_sn = sn_part1 + sn_part2
            except Exception:
                return None, None, None

            if len(device_sn) < 8:
                return None, None, None

            encrypted_data = svc_bytes[:14]
            if len(device_sn) >= 15:
                rc4_key = (device_sn[0:3] + device_sn[-5:] + SALT_RC4).encode('utf-8')
            else:
                rc4_key = (device_sn[:3] + device_sn[-5:] + SALT_RC4).encode('utf-8')

            decrypted = rc4_crypt(encrypted_data, rc4_key)
            decrypted_hex = decrypted.hex().upper()
            if len(decrypted_hex) < 8:
                return None, None, None

            data_for_crc = decrypted_hex[:-4]
            expected_crc = decrypted_hex[-4:]
            actual_crc = crc16(data_for_crc)
            if actual_crc.upper() != expected_crc.upper():
                pass  # CRC failed but continue

            if len(data_for_crc) < 4:
                return None, None, None

            payload_hex = data_for_crc[:-2]
            xor_key_hex = data_for_crc[-2:]
            xor_key = int(xor_key_hex, 16)
            payload_bytes = bytes.fromhex(payload_hex)
            decoded = xor_with_byte(payload_bytes, xor_key)

            if len(decoded) >= 22:
                model_code = int(decoded[0:4], 16)
                device_guid = bytes.fromhex(decoded[4:16])
                _LOGGER.debug("Extracted model_code: %s, device_guid: %s", model_code, device_guid.hex())
            else:
                return None, None, None

            sn_suffix = device_sn[-6:] if len(device_sn) >= 6 else device_sn
            key_material = (
                sn_suffix.encode('utf-8')
                + device_guid
                + SALT_KEY.encode('utf-8')
            )
            encryption_key = base64.b64encode(key_material).decode('utf-8')
            return encryption_key, device_sn, model_code
        except Exception:
            return None, None, None

    async def connect(self, device: JackeryDevice, retries: int = 2) -> bool:
        """Connect to a Jackery device with retry logic."""
        for attempt in range(1, retries + 1):
            try:
                if self.client:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None

                self.device = device
                self.device_type = device.device_type
                self.client = BleakClient(device.ble_device)
                await self.client.connect()
                if not self.client.is_connected:
                    raise RuntimeError("connect() returned but not connected")

                if device.encryption_key:
                    key_to_use = device.encryption_key
                    key_is_b64 = True
                elif self.encryption_key:
                    key_to_use = self.encryption_key
                    key_is_b64 = self.key_is_base64
                else:
                    key_to_use = None
                    key_is_b64 = False

                if key_to_use:
                    self.encryption_key = key_to_use
                    self.key_is_base64 = key_is_b64
                    if self.device_type == "box":
                        self.encryption = BoxEncryption(key_to_use, key_is_base64=key_is_b64)
                    else:
                        model_code = device.model_code
                        if model_code in (20, 21):
                            self.encryption = PortableAESEncryption(key_to_use, key_is_base64=key_is_b64)
                        else:
                            self.encryption = PortableRC4Encryption(key_to_use, key_is_base64=key_is_b64)

                await self.client.start_notify(BleUUIDs.CHAR_DATA_NOTIFY, self._handle_notification)
                _LOGGER.debug("Connected to %s", device.name)
                return True

            except Exception as e:
                error_msg = str(e) if str(e) else type(e).__name__
                if attempt < retries:
                    _LOGGER.debug("Connection attempt %d/%d failed: %s, retrying...", attempt, retries, error_msg)
                    await asyncio.sleep(2.0)
                else:
                    _LOGGER.error("Connection failed: %s", error_msg)
                    return False

        return False

    async def connect_by_address(self, address: str, retries: int = 2) -> bool:
        """Connect to a device by its Bluetooth address with retry logic."""
        for attempt in range(1, retries + 1):
            try:
                if self.client:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None

                self.client = BleakClient(address)
                await self.client.connect()
                if not self.client.is_connected:
                    raise RuntimeError("connect() returned but not connected")

                if self.encryption_key:
                    if self.device_type == "box":
                        self.encryption = BoxEncryption(self.encryption_key, key_is_base64=self.key_is_base64)
                    elif self.model_code in (20, 21):
                        self.encryption = PortableAESEncryption(self.encryption_key, key_is_base64=self.key_is_base64)
                    elif self.model_code is not None:
                        self.encryption = PortableRC4Encryption(self.encryption_key, key_is_base64=self.key_is_base64)
                    else:
                        self.encryption = AutoDetectEncryption(self.encryption_key, key_is_base64=self.key_is_base64, device_type="portable")

                await self.client.start_notify(BleUUIDs.CHAR_DATA_NOTIFY, self._handle_notification)
                _LOGGER.debug("Connected to %s", address)
                return True

            except Exception as e:
                error_msg = str(e) if str(e) else type(e).__name__
                if attempt < retries:
                    _LOGGER.debug("Connection attempt %d/%d failed: %s, retrying...", attempt, retries, error_msg)
                    await asyncio.sleep(2.0)
                else:
                    _LOGGER.error("Connection failed: %s", error_msg)
                    return False

        return False

    async def disconnect(self):
        """Disconnect from the device following Android app sequence."""
        if self.client:
            try:
                if self.client.is_connected:
                    try:
                        await self.client.stop_notify(BleUUIDs.CHAR_DATA_NOTIFY)
                    except Exception:
                        pass
                    await self.client.disconnect()
                    await asyncio.sleep(0.3)
            except (EOFError, OSError, Exception):
                pass
        self.client = None
        self.device = None
        self._notification_callback = None

    def set_notification_callback(self, callback: Callable[[Dict[str, Any]], None]):
        self._notification_callback = callback

    def get_detected_encryption_type(self) -> Optional[str]:
        if isinstance(self.encryption, AutoDetectEncryption):
            return self.encryption.detected_type
        elif isinstance(self.encryption, BoxEncryption):
            return EncryptionType.AES_BOX
        elif isinstance(self.encryption, PortableRC4Encryption):
            return EncryptionType.RC4
        elif isinstance(self.encryption, PortableAESEncryption):
            return EncryptionType.AES_PORTABLE
        return None

    def _handle_notification(self, sender: BleakGATTCharacteristic, data: bytes):
        """Handle incoming BLE notifications."""
        if self.encryption:
            decrypted = self.encryption.decrypt(data)
            if decrypted:
                if not self._encryption_logged and isinstance(self.encryption, AutoDetectEncryption) and self.encryption.detected_type:
                    _LOGGER.debug("Detected encryption type: %s", self.encryption.detected_type)
                    self._encryption_logged = True
                if decrypted.startswith("80"):
                    self._handle_multi_packet(decrypted)
                else:
                    self._last_response = decrypted
                    self._response_event.set()
                    if self._notification_callback:
                        self._parse_and_callback(decrypted)
            else:
                _LOGGER.debug("Decryption failed for %d bytes", len(data))
        else:
            self._last_response = data.hex()
            self._response_event.set()

    def _handle_multi_packet(self, decrypted: str):
        try:
            packet_num = int(decrypted[8:12], 16)
            total_packets = int(decrypted[12:16], 16)
            body = decrypted[16:]
            self._packet_buffer[packet_num] = body
            self._expected_packets = total_packets
            if len(self._packet_buffer) >= total_packets:
                combined = ""
                for i in range(1, total_packets + 1):
                    if i in self._packet_buffer:
                        combined += self._packet_buffer[i]
                self._packet_buffer = {}
                self._expected_packets = 0
                self._last_response = combined
                self._response_event.set()
                if self._notification_callback:
                    self._parse_and_callback_raw(combined)
        except Exception as e:
            _LOGGER.debug("Multi-packet parse error: %s", e)

    def _parse_and_callback(self, decrypted: str):
        try:
            if len(decrypted) < 8:
                self._notification_callback({"raw_hex": decrypted})
                return
            action_id = int(decrypted[2:4], 16)
            body_hex = decrypted[8:]
            if body_hex:
                ascii_data = bytes.fromhex(body_hex).decode('utf-8')
                if ascii_data.strip():
                    parsed = json.loads(ascii_data)
                    if isinstance(parsed, dict):
                        parsed['_actionId'] = action_id
                        self._notification_callback(parsed)
                    else:
                        self._notification_callback({"raw_hex": decrypted, "_actionId": action_id})
                else:
                    self._notification_callback({"raw_hex": decrypted, "_actionId": action_id})
            else:
                self._notification_callback({"raw_hex": decrypted, "_actionId": action_id})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
            _LOGGER.debug("JSON parse error: %s", e)
            self._notification_callback({"raw_hex": decrypted})

    def _parse_and_callback_raw(self, combined_hex: str):
        try:
            ascii_data = bytes.fromhex(combined_hex).decode('utf-8')
            parsed = json.loads(ascii_data)
            if isinstance(parsed, dict):
                self._notification_callback(parsed)
            else:
                self._notification_callback({"raw_hex": combined_hex})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._notification_callback({"raw_hex": combined_hex})

    async def send_command(self, command_hex: str, wait_response: bool = True,
                           timeout: float = 5.0) -> Optional[str]:
        """Send a command to the device."""
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected to device")

        if isinstance(self.encryption, AutoDetectEncryption) and not self.encryption.detected_type and wait_response:
            return await self._send_with_auto_detect(command_hex, timeout)

        if self.encryption:
            encrypted = self.encryption.encrypt(command_hex)
            data = bytes.fromhex(encrypted)
        else:
            data = bytes.fromhex(command_hex)

        self._response_event.clear()
        self._last_response = None

        try:
            await asyncio.sleep(0.1)
            await self.client.write_gatt_char(BleUUIDs.CHAR_DATA_WRITE, data, response=False)
        except EOFError as e:
            raise RuntimeError(f"Connection closed unexpectedly: {e}")
        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            raise RuntimeError(f"Failed to send command: {error_msg}")

        if wait_response:
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout)
                return self._last_response
            except asyncio.TimeoutError:
                _LOGGER.debug("Response timeout")
                return None
        return None

    async def _send_with_auto_detect(self, command_hex: str, timeout: float) -> Optional[str]:
        enc_types = self.encryption.get_encryption_types()
        for enc_type in enc_types:
            encrypted = self.encryption.encrypt_with_type(command_hex, enc_type)
            data = bytes.fromhex(encrypted)
            self._response_event.clear()
            self._last_response = None
            await self.client.write_gatt_char(BleUUIDs.CHAR_DATA_WRITE, data, response=False)
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=2.0)
                if self._last_response:
                    self.encryption.set_detected_type(enc_type)
                    self._encryption_logged = True
                    return self._last_response
            except asyncio.TimeoutError:
                continue
        return None

    async def send_command_collect_all(self, command_hex: str,
                                       timeout: float = 5.0,
                                       collect_time: float = 3.0) -> list[dict]:
        """Send a command and collect all responses over a period of time."""
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected to device")

        responses = []
        original_callback = self._notification_callback

        def collect_callback(data: dict):
            responses.append(data)

        self._notification_callback = collect_callback

        if isinstance(self.encryption, AutoDetectEncryption) and not self.encryption.detected_type:
            result = await self._collect_with_auto_detect(command_hex, collect_callback, collect_time)
            self._notification_callback = original_callback
            return result

        if self.encryption:
            encrypted = self.encryption.encrypt(command_hex)
            data = bytes.fromhex(encrypted)
        else:
            data = bytes.fromhex(command_hex)

        self._response_event.clear()
        self._last_response = None
        self._packet_buffer = {}

        await self.client.write_gatt_char(BleUUIDs.CHAR_DATA_WRITE, data, response=False)
        await asyncio.sleep(collect_time)

        self._notification_callback = original_callback
        return responses

    async def _collect_with_auto_detect(self, command_hex: str,
                                        original_callback, collect_time: float) -> list[dict]:
        enc_types = self.encryption.get_encryption_types()
        all_responses = []

        for enc_type in enc_types:
            responses_this_attempt = []

            def make_callback(resp_list):
                def cb(data: dict):
                    resp_list.append(data)
                    original_callback(data)
                return cb

            self._notification_callback = make_callback(responses_this_attempt)
            encrypted = self.encryption.encrypt_with_type(command_hex, enc_type)
            data = bytes.fromhex(encrypted)
            self._response_event.clear()
            self._last_response = None
            self._packet_buffer = {}

            await self.client.write_gatt_char(BleUUIDs.CHAR_DATA_WRITE, data, response=False)
            await asyncio.sleep(2.0)

            if responses_this_attempt:
                self.encryption.set_detected_type(enc_type)
                self._encryption_logged = True
                all_responses.extend(responses_this_attempt)
                remaining_time = collect_time - 2.0
                if remaining_time > 0:
                    await asyncio.sleep(remaining_time)
                return all_responses
        return all_responses

    async def send_heartbeat(self):
        """Send a heartbeat to keep the connection alive."""
        if self.client and self.client.is_connected:
            await self.client.write_gatt_char(BleUUIDs.CHAR_HEARTBEAT, bytes([0x01]), response=False)

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected


async def scan_devices(timeout: float = 10.0,
                       name_filter: Optional[str] = None) -> list[JackeryDevice]:
    """Convenience function to scan for Jackery devices."""
    client = JackeryBleClient()
    return await client.scan(timeout, name_filter)
