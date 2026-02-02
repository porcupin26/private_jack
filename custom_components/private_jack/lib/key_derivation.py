"""Jackery Encryption Key Derivation Module."""

import base64
import logging
from typing import Optional
from dataclasses import dataclass

from .crc import crc16

_LOGGER = logging.getLogger(__name__)

SALT_RC4 = "LYx*G!6u9#"
SALT_KEY = "6*SY1c5B9@"


def rc4_crypt(data: bytes, key: bytes) -> bytes:
    """RC4 encryption/decryption (symmetric)."""
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 255
        S[i], S[j] = S[j], S[i]
    i = j = 0
    result = bytearray(len(data))
    for k in range(len(data)):
        i = (i + 1) & 255
        j = (j + S[i]) & 255
        S[i], S[j] = S[j], S[i]
        result[k] = data[k] ^ S[(S[i] + S[j]) & 255]
    return bytes(result)


def xor_with_byte(data: bytes, xor_byte: int) -> str:
    """XOR each byte with a single byte and return hex string."""
    result = ""
    for b in data:
        result += format((b & 255) ^ xor_byte, '02x')
    return result


@dataclass
class BleAdvertisementData:
    """Parsed BLE advertisement data from Jackery device."""
    device_sn: str
    device_guid: bytes
    device_model: int
    battery_level: int
    reset_mark: int
    app_type: int


def parse_manufacturer_data(
    manufacturer_id: int, data: bytes, service_data: Optional[bytes] = None
) -> Optional[BleAdvertisementData]:
    """Parse BLE manufacturer data to extract device info."""
    try:
        id_hex = format(manufacturer_id, '04x')
        id_swapped = id_hex[2:4] + id_hex[0:2]
        app_type = int(id_swapped[0:2], 16)
        sn_part1 = bytes.fromhex(id_swapped[2:]).decode('utf-8')
        if data is None or len(data) == 0:
            return None
        sn_part2 = data.decode('utf-8')
        device_sn = sn_part1 + sn_part2
        if len(device_sn) != 15:
            return None
        if service_data is None or len(service_data) != 14:
            return None
        rc4_key = (device_sn[0:3] + device_sn[-5:] + SALT_RC4).encode('utf-8')
        decrypted = rc4_crypt(service_data, rc4_key)
        decrypted_hex = decrypted.hex().upper()
        data_part = decrypted_hex[:-4]
        crc_part = decrypted_hex[-4:]
        if crc16(data_part).upper() != crc_part.upper():
            _LOGGER.debug("CRC mismatch: expected %s, got %s", crc16(data_part), crc_part)
            return None
        payload = data_part[:-2]
        xor_key = int(data_part[-2:], 16)
        decoded = xor_with_byte(bytes.fromhex(payload), xor_key)
        device_model = int(decoded[0:4], 16)
        device_guid = bytes.fromhex(decoded[4:16])
        battery_level = int(decoded[16:18], 16)
        reset_mark = int(decoded[18:22], 16)
        return BleAdvertisementData(
            device_sn=device_sn,
            device_guid=device_guid,
            device_model=device_model,
            battery_level=battery_level,
            reset_mark=reset_mark,
            app_type=app_type,
        )
    except Exception as e:
        _LOGGER.debug("Failed to parse advertisement data: %s", e)
        return None


def derive_encryption_key(device_sn: str, device_guid: bytes) -> str:
    """Derive the encryption key from device serial number and GUID."""
    key_material = (
        device_sn[-6:].encode('utf-8')
        + device_guid
        + SALT_KEY.encode('utf-8')
    )
    return base64.b64encode(key_material).decode('utf-8')


def derive_key_from_advertisement(
    manufacturer_id: int, manufacturer_data: bytes, service_data: bytes
) -> Optional[str]:
    """Derive encryption key directly from BLE advertisement data."""
    adv_data = parse_manufacturer_data(manufacturer_id, manufacturer_data, service_data)
    if adv_data is None:
        return None
    return derive_encryption_key(adv_data.device_sn, adv_data.device_guid)
