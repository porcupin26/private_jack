"""Jackery BLE Protocol Encryption/Decryption Module."""

import base64
import logging
import random
from typing import Optional

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .crc import crc16

_LOGGER = logging.getLogger(__name__)


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


def xor_decode_hex(hex_str: str, xor_key_hex: str) -> str:
    """XOR decode a hex string with a key byte."""
    xor_key = int(xor_key_hex, 16)
    data = bytes.fromhex(hex_str)
    return xor_with_byte(data, xor_key)


class JackeryEncryption:
    """Base class for Jackery BLE encryption/decryption (AES)."""

    MAGIC_PREFIX = ""
    RANDOM_SUFFIX_BYTES = 2

    def __init__(self, key: str, key_is_base64: bool = False):
        if key_is_base64:
            self.key_bytes = base64.b64decode(key)
        else:
            self.key_bytes = bytes.fromhex(key)
        if len(self.key_bytes) > 16:
            self.key_bytes = self.key_bytes[:16]
        elif len(self.key_bytes) < 16:
            self.key_bytes = self.key_bytes + b'\x00' * (16 - len(self.key_bytes))
        self.iv = self.key_bytes

    def _get_cipher(self, encrypt: bool = True) -> AES:
        return AES.new(self.key_bytes, AES.MODE_CBC, self.iv)

    def encrypt(self, data: str) -> str:
        if self.RANDOM_SUFFIX_BYTES == 2:
            random_suffix = format(random.randint(1, 65535), '04x')
        else:
            random_suffix = format(random.randint(1, 255), '02x')
        data_with_suffix = data + random_suffix
        crc = crc16(data_with_suffix)
        data_with_crc = data_with_suffix + crc
        plaintext = bytes.fromhex(data_with_crc)
        cipher = self._get_cipher(encrypt=True)
        padded = pad(plaintext, AES.block_size)
        encrypted = cipher.encrypt(padded)
        return encrypted.hex().upper()

    def decrypt(self, encrypted_data: bytes) -> Optional[str]:
        try:
            cipher = self._get_cipher(encrypt=False)
            decrypted = unpad(cipher.decrypt(encrypted_data), AES.block_size)
            hex_str = decrypted.hex().upper()
            min_length = 36 if self.RANDOM_SUFFIX_BYTES == 2 else 16
            if len(hex_str) < min_length:
                return None
            prefix = hex_str[:4]
            if prefix.upper() != self.MAGIC_PREFIX:
                return None
            data_for_crc = hex_str[:-4]
            expected_crc = hex_str[-4:]
            calculated_crc = crc16(data_for_crc)
            if calculated_crc.upper() != expected_crc.upper():
                return None
            suffix_chars = self.RANDOM_SUFFIX_BYTES * 2
            payload = hex_str[4:-(suffix_chars + 4)]
            return payload
        except Exception as e:
            _LOGGER.debug("Decryption error: %s", e)
            return None


class BoxEncryption(JackeryEncryption):
    """Encryption for Jackery Box (stationary) devices using AES."""
    MAGIC_PREFIX = "DFED"
    RANDOM_SUFFIX_BYTES = 2


class PortableAESEncryption(JackeryEncryption):
    """Encryption for Jackery Portable devices using AES (models 20, 21)."""
    MAGIC_PREFIX = "DFEC"
    RANDOM_SUFFIX_BYTES = 1


class PortableRC4Encryption:
    """Encryption for Jackery Portable devices using RC4 (most common)."""

    MAGIC_PREFIX = "DFEC"
    RANDOM_SUFFIX_BYTES = 1

    def __init__(self, key: str, key_is_base64: bool = False):
        if key_is_base64:
            self.key_bytes = base64.b64decode(key)
        else:
            self.key_bytes = bytes.fromhex(key)

    def encrypt(self, data: str) -> str:
        security_byte = random.randint(1, 255)
        security_hex = format(security_byte, '02x')
        data_bytes = bytes.fromhex(data)
        xor_data = xor_with_byte(data_bytes, security_byte)
        crc_input = xor_data + security_hex
        crc = crc16(crc_input)
        plaintext_hex = xor_data + security_hex + crc
        plaintext_bytes = bytes.fromhex(plaintext_hex)
        encrypted = rc4_crypt(plaintext_bytes, self.key_bytes)
        return encrypted.hex().upper()

    def decrypt(self, encrypted_data: bytes) -> Optional[str]:
        try:
            decrypted = rc4_crypt(encrypted_data, self.key_bytes)
            hex_str = decrypted.hex().upper()
            if len(hex_str) < 16:
                return None
            data_without_crc = hex_str[:-4]
            expected_crc = hex_str[-4:]
            calculated_crc = crc16(data_without_crc)
            if calculated_crc.upper() != expected_crc.upper():
                return None
            xor_key_hex = data_without_crc[-2:]
            xor_data_hex = data_without_crc[:-2]
            decoded_hex = xor_decode_hex(xor_data_hex, xor_key_hex)
            if not decoded_hex.upper().startswith(self.MAGIC_PREFIX):
                return None
            payload = decoded_hex[4:]
            return payload.upper()
        except Exception as e:
            _LOGGER.debug("RC4 Decryption error: %s", e)
            return None


PortableEncryption = PortableRC4Encryption

# HP3600 (code 20) and E1500V2 (code 21) use AES, others use RC4
AES_MODEL_CODES = {20, 21}


class EncryptionType:
    """Encryption type constants."""
    RC4 = "rc4"
    AES_PORTABLE = "aes_portable"
    AES_BOX = "aes_box"
    UNKNOWN = "unknown"


def get_encryption_handler(device_type: str, key: str, key_is_base64: bool = False,
                           model_code: Optional[int] = None,
                           encryption_type: Optional[str] = None):
    """Factory function to get the appropriate encryption handler."""
    if encryption_type:
        if encryption_type == EncryptionType.AES_BOX:
            return BoxEncryption(key, key_is_base64=key_is_base64)
        elif encryption_type == EncryptionType.AES_PORTABLE:
            return PortableAESEncryption(key, key_is_base64=key_is_base64)
        elif encryption_type == EncryptionType.RC4:
            return PortableRC4Encryption(key, key_is_base64=key_is_base64)
    if device_type.lower() == "box":
        return BoxEncryption(key, key_is_base64=key_is_base64)
    if model_code is not None and model_code in AES_MODEL_CODES:
        return PortableAESEncryption(key, key_is_base64=key_is_base64)
    return PortableRC4Encryption(key, key_is_base64=key_is_base64)


class AutoDetectEncryption:
    """Encryption handler that auto-detects the correct encryption type."""

    def __init__(self, key: str, key_is_base64: bool = False, device_type: str = "portable"):
        self.key = key
        self.key_is_base64 = key_is_base64
        self.device_type = device_type
        self._handlers = []
        if device_type.lower() == "box":
            self._handlers = [
                (EncryptionType.AES_BOX, BoxEncryption(key, key_is_base64=key_is_base64)),
            ]
        else:
            self._handlers = [
                (EncryptionType.RC4, PortableRC4Encryption(key, key_is_base64=key_is_base64)),
                (EncryptionType.AES_PORTABLE, PortableAESEncryption(key, key_is_base64=key_is_base64)),
            ]
        self._detected_type: Optional[str] = None
        self._detected_handler = None

    @property
    def detected_type(self) -> Optional[str]:
        return self._detected_type

    def encrypt(self, data: str) -> str:
        handler = self._detected_handler or self._handlers[0][1]
        return handler.encrypt(data)

    def encrypt_with_type(self, data: str, enc_type: str) -> str:
        for handler_type, handler in self._handlers:
            if handler_type == enc_type:
                return handler.encrypt(data)
        return self._handlers[0][1].encrypt(data)

    def get_encryption_types(self) -> list[str]:
        return [enc_type for enc_type, _ in self._handlers]

    def set_detected_type(self, enc_type: str):
        for handler_type, handler in self._handlers:
            if handler_type == enc_type:
                self._detected_type = enc_type
                self._detected_handler = handler
                return

    def decrypt(self, encrypted_data: bytes) -> Optional[str]:
        if self._detected_handler:
            result = self._detected_handler.decrypt(encrypted_data)
            if result:
                return result
            self._detected_type = None
            self._detected_handler = None
        for enc_type, handler in self._handlers:
            try:
                result = handler.decrypt(encrypted_data)
                if result is not None:
                    self._detected_type = enc_type
                    self._detected_handler = handler
                    _LOGGER.debug("Auto-detected encryption type: %s", enc_type)
                    return result
            except Exception:
                continue
        return None
