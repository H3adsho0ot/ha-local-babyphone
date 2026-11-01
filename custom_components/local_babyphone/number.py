"""Temperature boundaries and local detection thresholds."""
from homeassistant.components.number import NumberEntity,NumberMode
from homeassistant.const import UnitOfTemperature,PERCENTAGE
from .entity import BabyphoneEntity


async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([SettingNumber(entry.runtime_data,*item) for item in (
        ('temperature_low','temperature','Temp_low',100,5,40,UnitOfTemperature.CELSIUS),
        ('temperature_high','temperature','Temp_high',100,5,40,UnitOfTemperature.CELSIUS),
        ('noise_threshold','detection','noise_threshold',1,1,100,PERCENTAGE),
    )])


class SettingNumber(BabyphoneEntity,NumberEntity):
    _attr_mode=NumberMode.BOX
    _attr_native_step=1
    def __init__(self,coordinator,key,kind,field,scale,low,high,unit):
        super().__init__(coordinator,key);self.kind=kind;self.field=field;self.scale=scale
        self._attr_native_min_value=low;self._attr_native_max_value=high;self._attr_native_unit_of_measurement=unit
    @property
    def native_value(self):
        value=(self.coordinator.data.get('detection',{}) if self.kind=='detection' else self.settings).get(self.field)
        return value/self.scale if value is not None else None
    async def async_set_native_value(self,value):await self.coordinator.async_command(self.kind,{self.field:int(value*self.scale)})
