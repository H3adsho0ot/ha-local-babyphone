"""Register the bundled card for both fresh pages and cached companion shells."""
import logging
from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from .const import FRONTEND_URL

LOGGER=logging.getLogger(__name__)


async def async_register_card(hass):
    resources=hass.data[LOVELACE_DATA].resources
    if not isinstance(resources,ResourceStorageCollection):
        # YAML resources are user-owned; the page bootstrap remains a fallback.
        frontend.add_extra_js_url(hass,FRONTEND_URL)
        LOGGER.info('For cached companion sessions in YAML mode, add %s as a module resource',FRONTEND_URL)
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded=True
    path=FRONTEND_URL.split('?',1)[0]
    matches=[item for item in resources.async_items() if item.get('url','').split('?',1)[0]==path]
    if not matches:
        await resources.async_create_item({'url':FRONTEND_URL,'res_type':'module'})
        return
    for item in matches:
        if item['url']!=FRONTEND_URL or item['type']!='module':
            await resources.async_update_item(item['id'],{'url':FRONTEND_URL,'res_type':'module'})
