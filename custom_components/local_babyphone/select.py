"""Camera timers and native video/audio sensitivity."""
from homeassistant.components.select import SelectEntity
from .entity import BabyphoneEntity
from .const import TIMERS,SENSITIVITIES


async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([SettingSelect(entry.runtime_data,*item) for item in (
        ('light_timer','light','Nightlight_timer',TIMERS),
        ('sound_timer','lullaby','Lullaby_timer',TIMERS),
        ('sensitivity','sensitivity','Stream_sensitive0',SENSITIVITIES),
    )])


class SettingSelect(BabyphoneEntity,SelectEntity):
    def __init__(self,coordinator,key,kind,field,options):
        super().__init__(coordinator,key);self.kind=kind;self.field=field;self.values=options
        self._attr_options=list(options)
    @property
    def current_option(self):return next((k for k,v in self.values.items() if v==self.settings.get(self.field)),None)
    async def async_select_option(self,option):await self.coordinator.async_command(self.kind,{self.field:self.values[option]})
