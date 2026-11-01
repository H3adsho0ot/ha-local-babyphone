"""Camera night light with its three supported brightness levels."""
from homeassistant.components.light import LightEntity,ColorMode,ATTR_BRIGHTNESS
from .entity import BabyphoneEntity


async def async_setup_entry(hass,entry,async_add_entities):async_add_entities([NightLight(entry.runtime_data)])


class NightLight(BabyphoneEntity,LightEntity):
    _attr_supported_color_modes={ColorMode.BRIGHTNESS}
    _attr_color_mode=ColorMode.BRIGHTNESS
    def __init__(self,coordinator):super().__init__(coordinator,'night_light')
    @property
    def is_on(self):return bool(self.settings.get('Nightlight_switch'))
    @property
    def brightness(self):return round(self.settings.get('Nightlight_bright',35)*255/100)
    async def async_turn_on(self,**kwargs):
        if kwargs.get(ATTR_BRIGHTNESS)==0:return await self.async_turn_off()
        values={'Nightlight_switch':1}
        if ATTR_BRIGHTNESS in kwargs:
            percent=kwargs[ATTR_BRIGHTNESS]*100/255
            values['Nightlight_bright']=min((35,70,100),key=lambda n:abs(n-percent))
        await self.coordinator.async_command('light',values)
    async def async_turn_off(self,**kwargs):await self.coordinator.async_command('light',{'Nightlight_switch':0})
