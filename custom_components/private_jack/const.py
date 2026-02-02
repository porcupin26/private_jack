"""Constants for Private Jack integration."""

DOMAIN = "private_jack"

CONF_DEVICE_ADDRESS = "device_address"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_SN = "device_sn"
CONF_DEVICE_TYPE = "device_type"
CONF_ENCRYPTION_KEY = "encryption_key"
CONF_MODEL_CODE = "model_code"

DEFAULT_SCAN_TIMEOUT = 10.0
DEFAULT_UPDATE_INTERVAL = 30

LIGHT_MODE_OFF = 0
LIGHT_MODE_LOW = 1
LIGHT_MODE_HIGH = 2
LIGHT_MODE_SOS = 3

LIGHT_MODE_OPTIONS = {
    "off": LIGHT_MODE_OFF,
    "low": LIGHT_MODE_LOW,
    "high": LIGHT_MODE_HIGH,
    "sos": LIGHT_MODE_SOS,
}

CHARGE_MODE_OPTIONS = {
    "fast": 0,
    "silent": 1,
    "custom": 2,
}

BATTERY_SAVE_OPTIONS = {
    "full": 0,
    "save": 1,
    "custom": 2,
}

ENERGY_SAVING_OPTIONS = {
    "Never": 0,
    "2 hours": 120,
    "8 hours": 480,
    "12 hours": 720,
    "24 hours": 1440,
}
