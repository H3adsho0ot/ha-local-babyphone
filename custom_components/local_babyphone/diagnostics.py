"""Diagnostics deliberately exclude keys, host addresses, and camera images."""
async def async_get_config_entry_diagnostics(hass,entry):
    state=entry.runtime_data.data
    return {'version':entry.version,'connected':state.get('connected'),
        'video_live':state.get('video_live'),'audio_live':state.get('audio_live'),
        'video_frames':state.get('video_frames'),'audio_packets':state.get('audio_packets'),
        'firmware':state.get('settings',{}).get('Fw_version'),'resolution':state.get('resolution')}
