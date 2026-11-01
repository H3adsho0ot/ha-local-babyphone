"""Local Babyphone integration and bundled dashboard card."""
from pathlib import Path
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST,EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from .const import DOMAIN,PLATFORMS,CONF_PAIRING_KEY,CONF_CAMERA_SSID
from .config_flow import parse_key
from .coordinator import BabyphoneCoordinator
from .media import MediaManager
from .protocol.client import CameraClient
from .commands import execute
from .frontend import async_register_card
from .demand import DemandConnection
from .migration import async_remove_motion


async def async_setup(hass,config):
    hass.data.setdefault(DOMAIN,{'cameras':{},'frontend_registered':False})
    return True


async def async_setup_entry(hass,entry):
    async_remove_motion(hass,entry)
    data=hass.data.setdefault(DOMAIN,{'cameras':{},'frontend_registered':False})
    if not data['frontend_registered']:
        await hass.http.async_register_static_paths([StaticPathConfig('/local_babyphone_frontend',str(Path(__file__).parent/'frontend'),False)])
        await async_register_card(hass)
        from .websocket import async_register
        async_register(hass)
        data['frontend_registered']=True
    def ssid():return entry.options.get(CONF_CAMERA_SSID,entry.data.get(CONF_CAMERA_SSID,''))
    @callback
    def save_authenticated_host(host):
        coordinator=getattr(entry,'runtime_data',None)
        if coordinator and coordinator.client.host==host and coordinator.client.ready.is_set() and entry.data[CONF_HOST]!=host:
            # Preserve entry/entity IDs and all credentials; only refresh the address.
            hass.config_entries.async_update_entry(entry,data={**entry.data,CONF_HOST:host})
    def host_changed(host):hass.loop.call_soon_threadsafe(save_authenticated_host,host)
    def factory():return CameraClient(entry.data[CONF_HOST],parse_key(entry.data[CONF_PAIRING_KEY]),
                                     camera_ssid=ssid(),host_changed=host_changed)
    client=await hass.async_add_executor_job(factory)
    coordinator=BabyphoneCoordinator(hass,entry,client)
    coordinator.demand=DemandConnection(client,factory,coordinator.async_client_changed)
    coordinator.media=MediaManager(client,coordinator.demand)
    if entry.options.get('detection'):
        await execute(client,'detection',entry.options['detection'])
    # Loading entities or subscribing to status must never take the handheld's session.
    entry.runtime_data=coordinator
    async def stop(event):
        await coordinator.async_close()
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP,stop))
        async def options_updated(hass,updated):
            # Changing the lookup identifier alone must not claim a camera session.
            updated.runtime_data.client.camera_ssid=ssid()
        entry.async_on_unload(entry.add_update_listener(options_updated))
        await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    except BaseException:
        await coordinator.async_close()
        raise
    return True


async def async_unload_entry(hass,entry):
    if not await hass.config_entries.async_unload_platforms(entry,PLATFORMS):return False
    await entry.runtime_data.async_close()
    return True
