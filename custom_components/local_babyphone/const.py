"""Integration constants and sound metadata."""
from homeassistant.const import Platform
from .localization import SOUND_LABELS

DOMAIN='local_babyphone'
VERSION='0.5.2'
CONF_PAIRING_KEY='pairing_key'
CONF_CAMERA_SSID='camera_ssid'
PLATFORMS=(Platform.CAMERA,Platform.LIGHT,Platform.MEDIA_PLAYER,Platform.SENSOR,Platform.BINARY_SENSOR,Platform.SWITCH,Platform.NUMBER,Platform.SELECT)
FRONTEND_URL=f'/local_babyphone_frontend/local-babyphone-card.js?v={VERSION}'
SOUND_TITLES=tuple(SOUND_LABELS['en'])
ALL_LULLABIES='All lullabies'
TIMERS={'off': 0, '5_minutes': 300, '10_minutes': 600, '20_minutes': 1200, '30_minutes': 1800, '60_minutes': 3600, '90_minutes': 5400}
SENSITIVITIES={'loud_only': 1, 'medium': 2, 'high': 3, 'continuous': 4}
