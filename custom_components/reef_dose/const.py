"""Constants for the Reef Dose integration."""

DOMAIN = "reef_dose"

CONF_HOST = "host"
CONF_API_KEY = "api_key"

DEFAULT_UPDATE_INTERVAL_MINUTES = 1

# Starting value for the Manual Dose Amount / Calibration Measured Amount
# number entities - matches ManualDoseDto's bounds in reef-dose-service
# (0.01-50ml).
DEFAULT_DOSE_ML = 1.0
