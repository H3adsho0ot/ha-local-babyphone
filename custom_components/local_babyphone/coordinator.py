"""One camera session shared by entities and WebRTC viewers."""
from datetime import timedelta
import asyncio
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError
from .commands import execute
from .localization import localized_error
from .const import DOMAIN

LOGGER=logging.getLogger(__name__)


class BabyphoneCoordinator(DataUpdateCoordinator):
    def __init__(self,hass,entry,client):
        super().__init__(hass,LOGGER,name=entry.title,config_entry=entry,update_interval=timedelta(seconds=1))
        self.entry=entry
        self.client=client
        self.camera_entity_id=None
        self.media=None
        self.demand=None
        self.command_lock=asyncio.Lock()

    async def _async_update_data(self):
        return self.snapshot()

    def snapshot(self):
        state=self.client.state()
        if self.demand:state['demand']=self.demand.state()
        return state

    def async_client_changed(self,client):
        self.client=client
        if self.media:self.media.client=client
        self.async_set_updated_data(self.snapshot())

    async def async_command(self,kind,values):
        async with self.command_lock:
            if self.demand and not self.demand.started and kind!='detection':
                raise localized_error('Camera released. Open the live view first.')
            try:
                await execute(self.client,kind,values)
            except (ValueError,KeyError,OSError,TimeoutError,ConnectionError) as exc:
                raise localized_error(str(exc)) from exc
            if kind=='detection':
                options={**self.entry.options,'detection':self.client.state()['detection']}
                self.hass.config_entries.async_update_entry(self.entry,options=options)
            self.async_set_updated_data(self.snapshot())

    async def async_close(self):
        if self.media:await self.media.close()
        if self.demand:await self.demand.close()
        else:await asyncio.to_thread(self.client.close)
