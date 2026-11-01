"""Measured room temperature, Wi-Fi strength, and local activity levels."""
from homeassistant.components.sensor import SensorEntity,SensorDeviceClass,SensorStateClass
from homeassistant.const import UnitOfTemperature,UnitOfTime,SIGNAL_STRENGTH_DECIBELS_MILLIWATT,PERCENTAGE,EntityCategory
from .entity import BabyphoneEntity

DESCRIPTIONS=(
    ('temperature',SensorDeviceClass.TEMPERATURE,UnitOfTemperature.CELSIUS,False),
    ('rssi',SensorDeviceClass.SIGNAL_STRENGTH,SIGNAL_STRENGTH_DECIBELS_MILLIWATT,True),
    ('audio_level',None,PERCENTAGE,False),
)


async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([*[Measurement(entry.runtime_data,*item) for item in DESCRIPTIONS],
        RemainingTime(entry.runtime_data,'light'),RemainingTime(entry.runtime_data,'lullaby')])


class RemainingTime(BabyphoneEntity,SensorEntity):
    _attr_device_class=SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement=UnitOfTime.SECONDS
    def __init__(self,coordinator,kind):
        super().__init__(coordinator,kind+'_remaining');self.kind=kind
    @property
    def native_value(self):return self.coordinator.data.get('timers',{}).get(self.kind,{}).get('remaining')


class Measurement(BabyphoneEntity,SensorEntity):
    _attr_state_class=SensorStateClass.MEASUREMENT
    def __init__(self,coordinator,key,device_class,unit,diagnostic):
        super().__init__(coordinator,key);self.key=key
        self._attr_device_class=device_class;self._attr_native_unit_of_measurement=unit
        if diagnostic:self._attr_entity_category=EntityCategory.DIAGNOSTIC
    @property
    def native_value(self):
        if self.key in ('temperature','rssi'):return self.settings.get(self.key)
        return self.coordinator.data.get(self.key)
