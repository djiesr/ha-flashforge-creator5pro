"""Constants for the FlashForge Creator 5 Pro integration."""

DOMAIN = "flashforge_creator5pro"
MANUFACTURER = "FlashForge"
MODEL = "Creator 5 Pro"

CONF_SERIAL_NUMBER = "serial_number"
CONF_CHECK_CODE = "check_code"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CAMERA_URL = "camera_url"

DEFAULT_NAME = "Creator 5 Pro"
DEFAULT_SCAN_INTERVAL = 15  # seconds
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 120

# Cancel job: off unless enabled in the options, and only after arming.
CONF_ENABLE_CANCEL = "enable_cancel"
CANCEL_ARM_SECONDS = 30

# Pause / resume: off unless enabled in the options. No arming.
CONF_ENABLE_PAUSE_RESUME = "enable_pause_resume"

# Chamber light: harmless, so on unless disabled in the options.
CONF_ENABLE_LIGHT = "enable_light"
