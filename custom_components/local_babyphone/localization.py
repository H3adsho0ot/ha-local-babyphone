"""Local catalogs for media metadata and translatable HA errors."""
import json
from pathlib import Path
from homeassistant.exceptions import HomeAssistantError

_ROOT=Path(__file__).parent
SOUND_LABELS=json.loads((_ROOT/'sound_titles.json').read_text(encoding='utf-8'))
_ERRORS=json.loads((_ROOT/'translations/en.json').read_text(encoding='utf-8'))['exceptions']
_ERROR_KEYS={value['message']:key for key,value in _ERRORS.items()}
_ERROR_KEYS.update({value['message']:key for key,value in json.loads((_ROOT/'translations/de.json').read_text(encoding='utf-8'))['exceptions'].items()})

def language(hass):
    """Backend metadata follows the HA server language, as entity names do."""
    return 'de' if str(getattr(getattr(hass,'config',None),'language','en')).lower().replace('_','-').split('-')[0]=='de' else 'en'

def localized_error(message):
    if key:=_ERROR_KEYS.get(message):
        return HomeAssistantError(_ERRORS[key]['message'],translation_domain='local_babyphone',translation_key=key)
    return HomeAssistantError(message)
