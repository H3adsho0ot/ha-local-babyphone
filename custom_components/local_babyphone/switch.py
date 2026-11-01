"""Native temperature alarm and local detection switches."""
from homeassistant.components.switch import SwitchEntity
from .entity import BabyphoneEntity


async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([SettingSwitch(entry.runtime_data,*item) for item in (
        ('temperature_alert','temperature','Temp_alert'),
        ('noise_detection','detection','noise'),
    )])
    async_add_entities([PrivacySwitch(entry.runtime_data)])


class SettingSwitch(BabyphoneEntity,SwitchEntity):
    def __init__(self,coordinator,key,kind,field):super().__init__(coordinator,key);self.kind=kind;self.field=field
    @property
    def is_on(self):return bool((self.coordinator.data.get('detection',{}) if self.kind=='detection' else self.settings).get(self.field))
    async def _set(self,value):await self.coordinator.async_command(self.kind,{self.field:value if self.kind=='detection' else int(value)})
    async def async_turn_on(self,**kwargs):await self._set(True)
    async def async_turn_off(self,**kwargs):await self._set(False)


class PrivacySwitch(SettingSwitch):
    """Native app-access privacy; activation may also drop camera LAN access."""
    _attr_icon='mdi:shield-lock'

    def __init__(self,coordinator):
        super().__init__(coordinator,'privacy','privacy','Privacy_switch')

    @property
    def available(self):
        value=self.settings.get(self.field)
        return super().available and type(value) is int and value in (0,1)

    @property
    def is_on(self):
        value=self.settings.get(self.field)
        return bool(value) if type(value) is int and value in (0,1) else None
