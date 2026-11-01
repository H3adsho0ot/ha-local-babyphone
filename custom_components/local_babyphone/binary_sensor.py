"""Connection, sound and native temperature alarm."""
import time
from homeassistant.components.binary_sensor import BinarySensorEntity,BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from .entity import BabyphoneEntity


async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([Activity(entry.runtime_data,key,device_class) for key,device_class in (
        ('connection',BinarySensorDeviceClass.CONNECTIVITY),
        ('sound',BinarySensorDeviceClass.SOUND),
        ('temperature_alarm',BinarySensorDeviceClass.PROBLEM),
    )])


class Activity(BabyphoneEntity,BinarySensorEntity):
    def __init__(self,coordinator,key,device_class):
        super().__init__(coordinator,key);self.key=key;self._attr_device_class=device_class
        if key=='connection':self._attr_entity_category=EntityCategory.DIAGNOSTIC
    @property
    def available(self):
        if self.key=='connection':return self.coordinator.last_update_success
        return super().available
    @property
    def is_on(self):
        data=self.coordinator.data
        if self.key=='connection':return bool(data.get('connected'))
        if self.key=='temperature_alarm':return bool(self.settings.get('Temp_alert_flag'))
        enabled=data.get('detection',{}).get('noise',False)
        kinds={'sound','camera-sound'}
        return enabled and any(e['kind'] in kinds and e['time']>time.time()-10 for e in data.get('events',[]))
