"""Common device association and availability."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


class BabyphoneEntity(CoordinatorEntity):
    _attr_has_entity_name=True

    def __init__(self,coordinator,key):
        super().__init__(coordinator)
        self._attr_unique_id=f'{coordinator.entry.entry_id}_{key}'
        self._attr_translation_key=key
        self._attr_device_info=DeviceInfo(identifiers={(DOMAIN,coordinator.entry.entry_id)},
            name=coordinator.entry.title,model='SCD923/26',
            sw_version=coordinator.client.info.get('Fw_version'))

    @property
    def available(self):
        return super().available and bool(self.coordinator.data and self.coordinator.data.get('connected'))

    @property
    def settings(self):
        return self.coordinator.data.get('settings',{})
