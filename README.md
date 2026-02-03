# Private Jack - Home Assistant Custom Integration

A custom Home Assistant integration that communicates with Jackery solar generators over Bluetooth Low Energy (BLE).

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![version](https://img.shields.io/badge/version-1.0.3-blue.svg)](https://github.com/porcupin26/private_jack)

Tested with the **Jackery Explorer 240 and Explorer 5000**, but should work with other Jackery portable and box models that use the same BLE protocol.

## Features

- Auto-discovery of Jackery devices via BLE scan
- Automatic encryption key derivation from BLE advertisements (no manual key entry)
- Real-time sensor data (battery, power, temperature, voltage, frequency)
- Switch controls for AC, DC, USB, car output, UPS mode, and super charge
- Select controls for light mode, charge mode, battery save, and energy saving timer
- Automatic time sync on connection
- Auto-reconnect on connection loss with retry logic

## Supported Devices

| Model Code | Name | DC | Split DC | AC | UPS | Light | Super Charge |
|---|---|---|---|---|---|---|---|
| 1 | E3000Pro | Y | N | Y | N | Y | N |
| 2 | E2000Plus | Y | N | Y | N | Y | N |
| 4 | E300Plus | Y | N | N | Y | Y | N |
| 5 | E1000Plus | Y | Y | Y | Y | Y | N |
| 6 | E700Plus | Y | Y | N | Y | Y | N |
| 7 | E280Plus | Y | N | Y | Y | Y | N |
| 8 | E1000Pro2 | Y | N | Y | Y | Y | Y |
| 9 | E240 | Y | N | N | Y | N | Y |
| 10 | E600Plus | Y | N | Y | Y | Y | Y |
| 12 | E2000Pro2 | Y | N | Y | Y | Y | Y |
| 13 | E5000Plus | Y | Y | Y | N | Y | N |
| 14 | E3000 | Y | N | Y | N | Y | N |
| 15 | E900 | Y | N | Y | Y | Y | Y |
| 16 | E1800 | Y | N | Y | Y | Y | Y |
| 17 | E1500Ultra | N | N | Y | N | Y | N |
| 18 | E1100Pro2 | Y | N | Y | Y | Y | Y |
| 19 | HP3000 | Y | N | Y | N | Y | N |
| 20 | HP3600 | Y | N | Y | N | Y | N |
| 21 | E1500V2 | Y | N | Y | Y | Y | N |
| 22 | HP5000Plus | Y | Y | Y | N | Y | N |

**Encryption:** Models 20 (HP3600) and 21 (E1500V2) use AES-128-CBC. All other portable models use RC4. Box/stationary devices use AES-128-CBC. The integration auto-detects the correct encryption method.

**Split DC models** (5, 6, 13, 22) expose separate USB and car DC outputs instead of a single DC switch.

## Prerequisites

- Home Assistant instance with Bluetooth adapter available
- Jackery device powered on and within Bluetooth range
- The Jackery device should NOT be connected to the official Jackery app at the same time (only one BLE connection is possible)

## Installation

### Manual Installation

1. Copy the `custom_components/private_jack` folder into your Home Assistant `config/custom_components/` directory:

```
config/
  custom_components/
    private_jack/
      __init__.py
      config_flow.py
      const.py
      coordinator.py
      manifest.json
      select.py
      sensor.py
      switch.py
      strings.json
      translations/
        en.json
      lib/
        __init__.py
        ble_client.py
        commands.py
        crc.py
        crypto.py
        key_derivation.py
        parser.py
```

2. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services**
2. Click **Add Integration**
3. Search for **Private Jack**
4. The integration will scan for nearby Jackery devices (this takes about 10 seconds)
5. Select your device from the list
6. The integration will automatically derive the encryption key and set up the device

No manual configuration of addresses or encryption keys is needed.

## Entities

### Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| Battery Level | Current battery percentage | % |
| Battery Temperature | Battery temperature | °C |
| Total Input Power | Total charging power | W |
| Total Output Power | Total discharge power | W |
| AC Input Power | AC wall charger input | W |
| AC Output Power | AC inverter output | W |
| DC/Solar Input Power | Solar panel / DC input | W |
| AC Output Voltage | AC output voltage | V |
| AC Output Frequency | AC output frequency | Hz |
| Energy Saving Timer | Auto-shutdown timer setting | min |
| Error Code | Device error code (0 = no error) | - |

### Switches

| Entity | Description |
|--------|-------------|
| AC Output | Turn the AC inverter on/off |
| DC Output | Turn the DC output on/off (single DC models) |
| USB Output | Turn the USB ports on/off (split DC models) |
| Car Output | Turn the car DC output on/off (split DC models) |
| UPS Mode | Enable/disable UPS (uninterruptible power supply) mode |
| Super Charge | Enable/disable super fast charging |

### Selects

| Entity | Options | Description |
|--------|---------|-------------|
| Light Mode | off, low, high, sos | Control the built-in light |
| Charge Mode | fast, silent, custom | Set the charging mode |
| Battery Save | full, save, custom | Battery usage mode (full 0-100%, save 15-85%, custom) |
| Energy Saving | Never, 2h, 8h, 12h, 24h | Auto-shutdown timer |

## Polling Interval

The integration polls the device every **30 seconds** by default. Each poll establishes or reuses a BLE connection, sends a status query, and collects the response.

## Troubleshooting

### Device not found during scan

- Make sure the Jackery device is powered on
- Make sure Bluetooth is enabled on your Home Assistant host
- Move the HA host closer to the Jackery device (BLE range is typically 10-15 meters)
- Make sure the official Jackery app is not connected to the device (only one BLE connection at a time)

### Connection drops or timeouts

- BLE connections can be unreliable over distance; the integration will auto-reconnect on the next poll cycle (with up to 2 retry attempts)
- Check Home Assistant logs for error messages: **Settings > System > Logs**, filter for `private_jack`

### Switches not working

- The device must be connected and responding to status queries before control commands will work
- Some commands may not be supported by all models (e.g. UPS mode is not available on all devices)
- Check logs for "Failed to send command" errors

### Viewing debug logs

Add the following to your `configuration.yaml` to enable debug logging:

```yaml
logger:
  logs:
    custom_components.private_jack: debug
```

Restart Home Assistant after changing the log level.

## How It Works

1. **Discovery**: Scans for BLE devices with known Jackery name prefixes (HT, JACKERY, JK, EXPLORER)
2. **Key Derivation**: Extracts the device serial number from manufacturer data, decrypts the service data using RC4, and derives an encryption key from the serial number suffix, device GUID, and a static salt
3. **Connection**: Connects via BLE GATT with retry logic, subscribes to notification characteristic for responses
4. **Encryption**: Commands are encrypted (RC4 or AES depending on model) before sending; responses are decrypted and validated via CRC-16
5. **Polling**: A `DataUpdateCoordinator` queries device properties every 30 seconds and updates all sensor/switch/select entities
6. **Disconnect**: Follows the Android app disconnect sequence (stop notifications, disconnect GATT, short delay)

## Dependencies

These are installed automatically by Home Assistant:

- `bleak` >= 0.21.0 (BLE communication)
- `pycryptodome` >= 3.19.0 (AES encryption)

## License

This integration is provided as-is for personal use. It is based on reverse engineering of the Jackery BLE protocol and is not affiliated with or endorsed by Jackery Inc.
