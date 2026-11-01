"""Native HA camera with local WebRTC video and audio."""
import asyncio
import io
from homeassistant.components.camera import Camera,CameraEntityFeature,WebRTCAnswer,WebRTCError
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import BabyphoneEntity
from .localization import localized_error


async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([BabyphoneCamera(entry.runtime_data)])


class BabyphoneCamera(BabyphoneEntity,Camera):
    _attr_supported_features=CameraEntityFeature.STREAM

    def __init__(self,coordinator):
        Camera.__init__(self)
        BabyphoneEntity.__init__(self,coordinator,'camera')

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.coordinator.camera_entity_id=self.entity_id
        self.hass.data[DOMAIN]['cameras'][self.entity_id]=self

    async def async_will_remove_from_hass(self):
        self.hass.data[DOMAIN]['cameras'].pop(self.entity_id,None)
        await super().async_will_remove_from_hass()

    @property
    def available(self):
        # An idle camera must remain selectable so HA accepts a new WebRTC offer.
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        return {'local_babyphone':True,'two_way_audio_card':True,
                'connection_mode':self.coordinator.data.get('demand',{}).get('mode','active')}

    async def async_camera_image(self,width=None,height=None):
        client=self.coordinator.client
        # Thumbnail polling must neither open a session nor return a frozen live image.
        frame=client.video_frame if client.ready.is_set() else None
        if frame is None:return None
        def encode():
            image=frame.to_image()
            if width and height:image.thumbnail((width,height))
            out=io.BytesIO();image.save(out,format='JPEG',quality=90);return out.getvalue()
        return await self.hass.async_add_executor_job(encode)

    async def async_handle_async_webrtc_offer(self,offer_sdp,session_id,send_message):
        try:send_message(WebRTCAnswer(await self.coordinator.media.offer(offer_sdp,session_id)))
        except (OSError,ValueError,ConnectionError) as exc:raise localized_error(str(exc)) from exc

    async def async_on_webrtc_candidate(self,session_id,candidate):
        await self.coordinator.media.candidate(session_id,candidate)

    @callback
    def close_webrtc_session(self,session_id):
        self.hass.async_create_task(self.coordinator.media.close_session(session_id))
