"""Build a self-contained HA card. No proprietary firmware artwork or fonts."""
from pathlib import Path
import json,re
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'frontend-src'
OUT=ROOT/'custom_components/local_babyphone/frontend'
OUT.mkdir(parents=True,exist_ok=True)


def icon(body):
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+body+'</svg>'
    return 'data:image/svg+xml,'+quote(svg,safe='')


ICONS={
    'light':icon('<path d="M12 22c0-4-5-4-5-10a9 9 0 0 1 18 0c0 6-5 6-5 10zM12 26h8m-6 3h4M16 1v2M3 5l3 2m23-2-3 2"/>'),
    'sound':icon('<path d="M12 23V7l14-3v16M12 11l14-3"/><ellipse cx="8" cy="25" rx="4" ry="3" fill="white"/><ellipse cx="22" cy="22" rx="4" ry="3" fill="white"/>'),
    'mute':icon('<path d="M4 13h5l6-5v16l-6-5H4zM21 11c3 3 3 7 0 10M25 7c6 5 6 13 0 18M3 3l26 26"/>'),
    'volume':icon('<path d="M4 13h5l6-5v16l-6-5H4zM21 11c3 3 3 7 0 10M25 7c6 5 6 13 0 18"/>'),
    'microphone':icon('<rect x="12" y="3" width="8" height="17" rx="4"/><path d="M8 14v2a8 8 0 0 0 16 0v-2M16 24v5m-5 0h10"/>'),
    'menu':icon('<path d="M7 10h18M7 16h18M7 22h18"/>'),
    'motion':icon('<circle cx="16" cy="16" r="4"/><path d="M9 7a12 12 0 0 0 0 18M23 7a12 12 0 0 1 0 18M5 3a17 17 0 0 0 0 26M27 3a17 17 0 0 1 0 26"/>'),
    'monitor':icon('<rect x="3" y="5" width="26" height="19" rx="3"/><path d="M12 24v4m8-4v4m-11 0h14"/><circle cx="16" cy="14.5" r="4" fill="#00e6c6" stroke="none"/>'),
    'play':icon('<path d="m11 6 15 10-15 10z" fill="white" stroke="none"/>'),
    'stop':icon('<rect x="8" y="8" width="16" height="16" fill="white" stroke="none"/>'),
    'privacy':icon('<path d="M2 16s5-9 14-9 14 9 14 9-5 9-14 9S2 16 2 16ZM3 3l26 26"/>'),
    'microphoneOff':icon('<path d="M12 8V7a4 4 0 0 1 8 0v9M12 13v3a4 4 0 0 0 6 3M8 14v2a8 8 0 0 0 14 5M24 14v2M16 24v5m-5 0h10M3 3l26 26"/>'),
    'camera':icon('<path d="M4 9h6l2-4h8l2 4h6v18H4z"/><circle cx="16" cy="18" r="6"/>'),
    'temperature':icon('<path d="M12 19V7a4 4 0 0 1 8 0v12a7 7 0 1 1-8 0ZM16 11v12"/><circle cx="16" cy="24" r="2"/>'),
    'events':icon('<path d="M9 7h18M9 16h18M9 25h18M4 7h.1M4 16h.1M4 25h.1"/>'),
    'close':icon('<path d="m8 8 16 16M24 8 8 24"/>'),
}
RECEPTION=[icon('<path d="m3 7 4 7 4-7ZM7 14v11"/>'+''.join(f'<path d="M{x} 25V{height}" stroke="white" opacity="{1 if i<n else .3}" stroke-width="2"/>' for i,(x,height) in enumerate(((14,22),(18,18),(22,13),(26,8))))) for n in range(5)]
template=(SRC/'template.html').read_text(encoding='utf-8')
css=(SRC/'style.css').read_text(encoding='utf-8')
assert '/assets/firmware/' not in template+css
assert '.ttf' not in css
assert not re.search(r'philips|avent|app-badge',template,re.I)
data={'CARD_TRANSLATIONS':json.loads((SRC/'translations.json').read_text(encoding='utf-8')),'CARD_HTML':template,'CARD_CSS':css,'ICONS':ICONS,'RECEPTION':RECEPTION,'SOUND_TITLES':json.loads((SRC/'sounds.json').read_text(encoding='utf-8'))}
bundle='/* Local Babyphone card - bundled with the integration; no external assets. */\n'
bundle+='\n'.join('const '+name+' = '+json.dumps(value,ensure_ascii=False)+';' for name,value in data.items())+'\n'
bundle+=(SRC/'localize.js').read_text(encoding='utf-8')+'\n'
bundle+=(SRC/'gestures.js').read_text(encoding='utf-8')+'\n'
bundle+=(SRC/'card.js').read_text(encoding='utf-8')
(OUT/'local-babyphone-card.js').write_text(bundle,encoding='utf-8')
print(f'Built self-contained card: {len(bundle.encode())} bytes; independent SVG artwork and system fonts')
