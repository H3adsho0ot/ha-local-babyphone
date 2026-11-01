"""Built-in lullabies and soothing sounds, not an arbitrary media upload API."""
from homeassistant.components.media_player import MediaPlayerEntity,MediaPlayerEntityFeature,MediaPlayerState,MediaType
from homeassistant.exceptions import HomeAssistantError
from .entity import BabyphoneEntity
from .const import SOUND_TITLES,ALL_LULLABIES
from .localization import SOUND_LABELS, language, localized_error


async def async_setup_entry(hass,entry,async_add_entities):async_add_entities([Sounds(entry.runtime_data)])


class Sounds(BabyphoneEntity,MediaPlayerEntity):
    _attr_icon='mdi:music-note'
    _attr_supported_features=(MediaPlayerEntityFeature.PLAY|MediaPlayerEntityFeature.STOP|MediaPlayerEntityFeature.PLAY_MEDIA|MediaPlayerEntityFeature.SELECT_SOURCE|MediaPlayerEntityFeature.VOLUME_SET|MediaPlayerEntityFeature.VOLUME_STEP|MediaPlayerEntityFeature.NEXT_TRACK|MediaPlayerEntityFeature.PREVIOUS_TRACK)
    def __init__(self,coordinator):super().__init__(coordinator,'sounds')
    @property
    def state(self):return MediaPlayerState.PLAYING if self.settings.get('Lullaby_play') else MediaPlayerState.IDLE
    @property
    def track_titles(self):return list(SOUND_LABELS[language(self.coordinator.hass)][:int(self.settings.get('Lullaby_Total',self.settings.get('Lullaby_total',17)))])
    @property
    def all_lullabies(self):return 'Alle Schlaflieder' if language(self.coordinator.hass)=='de' else ALL_LULLABIES
    @property
    def source_list(self):return [self.all_lullabies,*self.track_titles]
    @property
    def source(self):
        if self.settings.get('Lullaby_mode')==0:return self.all_lullabies
        index=self.settings.get('Lullaby_select_num',0)
        return self.track_titles[index] if 0<=index<len(self.track_titles) else None
    @property
    def media_title(self):
        index=self.settings.get('Lullaby_play_num',0)
        return self.track_titles[index] if 0<=index<len(self.track_titles) else self.source
    @property
    def media_content_type(self):return MediaType.MUSIC
    @property
    def volume_level(self):return self.settings.get('Lullaby_volume',60)/100
    async def async_media_play(self):await self.coordinator.async_command('lullaby',{'Lullaby_play':1})
    async def async_media_stop(self):await self.coordinator.async_command('lullaby',{'Lullaby_play':0})
    def _track_index(self,title):
        # Accept both translations to preserve existing source-selection automations.
        for titles in SOUND_LABELS.values():
            if title in titles[:len(self.track_titles)]:return titles.index(title)
        raise localized_error('Unknown camera sound')
    async def async_select_source(self,source):
        if source in (ALL_LULLABIES,'Alle Schlaflieder'):
            await self.coordinator.async_command('lullaby',{'Lullaby_mode':0})
            return
        index=self._track_index(source)
        await self.coordinator.async_command('lullaby',{'Lullaby_mode':1,'Lullaby_select_num':index})
    async def async_play_media(self,media_type,media_id,**kwargs):
        if media_id in (ALL_LULLABIES,'Alle Schlaflieder'):
            await self.coordinator.async_command('lullaby',{'Lullaby_mode':0,'Lullaby_play':1})
            return
        try:index=int(media_id) if str(media_id).isdigit() else self._track_index(media_id)
        except ValueError as exc:raise localized_error('Expected a sound title or native sound number') from exc
        await self.coordinator.async_command('lullaby',{'Lullaby_mode':1,'Lullaby_select_num':index,'Lullaby_play':1})
    async def async_set_volume_level(self,volume):
        value=max(30,min(100,int(round(volume*10))*10))
        await self.coordinator.async_command('lullaby',{'Lullaby_volume':value})
    async def async_volume_up(self):await self.async_set_volume_level(self.volume_level+.1)
    async def async_volume_down(self):await self.async_set_volume_level(self.volume_level-.1)
    async def async_media_next_track(self):await self.async_select_source(self.track_titles[(self.settings.get('Lullaby_play_num',self.settings.get('Lullaby_select_num',0))+1)%len(self.track_titles)])
    async def async_media_previous_track(self):await self.async_select_source(self.track_titles[(self.settings.get('Lullaby_play_num',self.settings.get('Lullaby_select_num',0))-1)%len(self.track_titles)])
