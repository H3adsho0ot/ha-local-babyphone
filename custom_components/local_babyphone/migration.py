"""Remove only this entry's retired local motion features."""
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN

RETIRED_KEYS={'motion','motion_level','motion_detection','motion_threshold'}

@callback
def async_remove_motion(hass,entry):
    registry=er.async_get(hass)
    retired={f'{entry.entry_id}_{key}' for key in RETIRED_KEYS}
    for entity in er.async_entries_for_config_entry(registry,entry.entry_id):
        if entity.platform==DOMAIN and entity.unique_id in retired:
            registry.async_remove(entity.entity_id)
    if 'detection' in entry.options:
        original=entry.options['detection']
        cleaned={key:value for key,value in original.items() if key in ('noise','noise_threshold')}
        if original!=cleaned:hass.config_entries.async_update_entry(entry,options={**entry.options,'detection':cleaned})
