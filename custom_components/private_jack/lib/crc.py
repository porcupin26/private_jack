"""CRC-16 Checksum Module for Jackery BLE Protocol."""


def crc16(hex_string: str) -> str:
    """Calculate CRC-16 checksum for a hex string."""
    hex_string = hex_string.replace(" ", "")
    if len(hex_string) % 2 != 0:
        return "0000"
    data = bytes.fromhex(hex_string)
    return crc16_bytes(data)


def crc16_bytes(data: bytes) -> str:
    """Calculate CRC-16 checksum for bytes."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte & 0xFF
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    hex_crc = format(crc, '04X')
    return hex_crc[2:4] + hex_crc[0:2]
