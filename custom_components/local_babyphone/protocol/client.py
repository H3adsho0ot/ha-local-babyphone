"""Local camera protocol; credentials and decrypted media stay on the HA host."""
from . import adpcm as audioop
import base64
import binascii
import collections
import json
import logging
import re
import secrets
import select
import socket
import struct
import threading
import time

import av
import numpy as np

from .crypto import DeviceCipher
from .wire import ControlWire, frame, Wire
from .discovery import discover_camera

LOG = logging.getLogger(__name__)
IDENTITY = {'pu': 'pu.1.0.22', 'puu': 'puu.1.0.10', 'puhw_version': 'HW02', 'tb_enc': '1'}
ALLOWED_STATE = {'Model', 'Fw_version', 'Stream_mode', 'Privacy_switch',
    'Stream_sensitive0', 'Stream_sensitive1', 'Stream_sensitive2', 'Custom_count', 'Custom_valid',
    'Lullaby_play', 'Lullaby_volume', 'Lullaby_timer', 'Lullaby_mode',
    'Lullaby_select_num', 'Lullaby_play_num', 'Lullaby_Total', 'Lullaby_total',
    'Nightlight_switch', 'Nightlight_bright', 'Nightlight_timer',
    'Temp_alert', 'Temp_high', 'Temp_low', 'Temp_alert_flag', 'Audio_Status'}
EVENT_FIELDS = {0x905: 'Temp_alert_flag', 0x906: 'Nightlight_switch', 0x907: 'Nightlight_bright',
    0x908: 'Temp_alert', 0x909: 'Temp_high', 0x90A: 'Temp_low',
    0x90B: 'Lullaby_play', 0x90C: 'Lullaby_volume', 0x90D: 'Lullaby_play_num',
    0x90E: 'Lullaby_mode',
    0x915: 'Audio_Status', 0x917: 'rssi'}


class CameraClient:
    def __init__(self, host: str, pairing_key: bytes, camera_ssid='', host_changed=None):
        self.host = host
        self.camera_ssid = camera_ssid
        self.host_changed = host_changed
        self.reported_host = host
        self.discovery_at = None
        self.cipher = DeviceCipher()
        self.key = secrets.token_bytes(16)
        if len(pairing_key) != 16:
            raise ValueError('The local pairing key must contain 16 bytes')
        self.wrapped = self.cipher.crypt(pairing_key, self.key)
        self.lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.command_lock = threading.Lock()
        self.pending = {}
        self.seq = 0
        self.sock = None
        self.stopping = threading.Event()
        self.ready = threading.Event()
        self.info = {}
        self.timer_observations = {}
        self.events = collections.deque(maxlen=30)
        self.error = None
        self.video_error = None
        self.video_frame = None
        self.video_number = 0
        self.video_at = 0
        self.audio_at = 0
        self.audio_ready = threading.Event()
        self.media_ready = threading.Event()
        self.media_generation = 0
        self.audio_number = 0
        self.audio_listeners = set()
        self.audio_level = 0
        self.noise_threshold = 45
        self.noise_enabled = True
        self.cooldowns = {}
        self.rssi_at = 0
        self.temperature_at = 0
        self.talk_sock = None
        self.talk_at = 0
        self.talk_packets = 0
        self.talk_input_samples = 0
        self.talk_input_level = 0
        self.talk_buffer = bytearray()
        self.talk_index = 0
        self.talk_lock = threading.Lock()
        self.threads = []
        self.sockets = set()
        self.sockets_lock = threading.Lock()

    def _connect(self, address, timeout):
        if self.stopping.is_set():raise ConnectionError('Camera session closed')
        sock = socket.create_connection(address, timeout)
        with self.sockets_lock:
            # A connect() may finish after the last viewer has left.
            if self.stopping.is_set():
                sock.close()
                raise ConnectionError('Camera session closed')
            self.sockets = {item for item in self.sockets if item.fileno() != -1}
            self.sockets.add(sock)
        return sock

    def start(self):
        for target in (self._control_loop, self._maintenance, self._media_loop, self._audio_loop, self._message_loop):
            t = threading.Thread(target=target, daemon=True)
            self.threads.append(t)
            t.start()

    def event(self, kind, text, cooldown=0):
        now = time.time()
        with self.lock:
            if now - self.cooldowns.get(kind, 0) < cooldown:
                return
            self.cooldowns[kind] = now
            self.events.appendleft({'id': time.time_ns()//1000000, 'time': now, 'kind': kind, 'text': text})

    def _next_seq(self):
        self.seq = (self.seq + 1) % 256
        return self.seq

    def _encode(self, obj):
        raw = json.dumps(obj, separators=(',', ':')).encode() + b'\0'
        return self.cipher.crypt(self.key, raw + bytes(-len(raw) % 16))

    def request(self, op, obj=None, timeout=6):
        if not self.ready.wait(timeout):
            raise ConnectionError('Kamera noch nicht verbunden')
        with self.command_lock:
            ev = threading.Event()
            box = []
            with self.send_lock:
                seq = self._next_seq()
                self.pending[seq] = (op, ev, box)
                try:
                    self.sock.sendall(frame(op, seq, self._encode(obj or {})))
                except Exception:
                    self.pending.pop(seq, None)
                    raise
            try:
                if not ev.wait(timeout):
                    raise TimeoutError('Keine Antwort der Kamera')
                if isinstance(box[0], Exception):
                    raise box[0]
                return box[0]
            finally:
                self.pending.pop(seq, None)

    def _merge(self, obj):
        if isinstance(obj, dict):
            with self.lock:
                for kind,prefix,switch in (('light','Nightlight','Nightlight_switch'),('lullaby','Lullaby','Lullaby_play')):
                    field=prefix+'_timer'
                    if (field in obj and obj[field]!=self.info.get(field)) or (switch in obj and obj[switch]!=self.info.get(switch)) or obj.get(switch)==0:
                        self.timer_observations.pop(kind,None)
                self.info.update({k: v for k, v in obj.items() if k in ALLOWED_STATE})

    def _handle_event(self, op, body):
        if len(body)<4:
            return
        value=struct.unpack_from('<i',body)[0]
        if op in (0x904,0x910):
            # Native *TimerVal handlers read two int32s: switch, seconds left.
            if len(body)<8:
                return
            enabled,remaining=struct.unpack_from('<ii',body)
            if enabled not in (0,1) or not 0<=remaining<=5400:
                return
            kind,switch=('light','Nightlight_switch') if op==0x904 else ('lullaby','Lullaby_play')
            with self.lock:
                self.info[switch]=enabled
                if enabled:
                    self.timer_observations[kind]=(remaining,time.monotonic())
                else:
                    self.timer_observations.pop(kind,None)
        elif op in (0x903,0x912):
            if 0<=value<=5400:
                self._merge({('Lullaby_timer' if op==0x903 else 'Nightlight_timer'):value})
        elif op in (0x90f,0x911):
            if value==0:
                self._merge({('Lullaby_timer' if op==0x90f else 'Nightlight_timer'):0})
        elif op in EVENT_FIELDS:
            self._merge({EVENT_FIELDS[op]:value})
            # RSSI and native alarm fields are event-only, outside GetDevInfo.
            with self.lock:
                self.info[EVENT_FIELDS[op]]=value
                if op==0x917 and -150<=value<=0:
                    self.rssi_at=time.monotonic()
        if op==0x902 and value:
            self.event('camera-sound','Tonalarm der Kamera',10)
        elif op==0x905 and value:
            self.event('temperature','Temperaturalarm der Kamera',10)

    def _timer_state(self,kind,now):
        prefix,switch=('Nightlight','Nightlight_switch') if kind=='light' else ('Lullaby','Lullaby_play')
        configured=self.info.get(prefix+'_timer',0)
        active=bool(self.info.get(switch))
        sample=self.timer_observations.get(kind)
        age=now-sample[1] if sample else None
        fresh=self.ready.is_set() and age is not None and age<=90
        remaining=max(0,sample[0]-int(age)) if fresh else None
        if not active or configured==0:
            remaining=0
        return {'active':active,'configured':configured,'remaining':remaining,'fresh':fresh,'age':round(age,1) if age is not None else None}

    def _refresh_host(self):
        if not self.camera_ssid or self.stopping.is_set():return
        now=time.monotonic()
        if self.discovery_at is not None and now-self.discovery_at<30:return
        self.discovery_at=now
        try:host=discover_camera(self.camera_ssid,stop_event=self.stopping)
        except (OSError,ValueError):
            LOG.debug('Local discovery unavailable; retaining the configured address')
            return
        if host and not self.stopping.is_set():self.host=host

    def _authenticated_host(self):
        if self.ready.is_set() and self.host!=self.reported_host:
            if self.host_changed:self.host_changed(self.host)
            self.reported_host=self.host

    def _control_loop(self):
        while not self.stopping.is_set():
            try:
                self._refresh_host()
                sock = self._connect((self.host, 6000), 5)
                sock.settimeout(16)
                self.sock = sock
                wire = ControlWire(sock)
                with self.send_lock:
                    sock.sendall(frame(1, self._next_seq(), self.wrapped + b'0\0'))
                first = wire.read()
                if struct.unpack_from('<H', first, 8)[0] != 0x8001:
                    raise ConnectionError('Lokale Anmeldung fehlgeschlagen')
                # Identity negotiation is a session setup operation, not a polling query.
                # Repeating it makes this camera close its media sockets.
                with self.send_lock:
                    init_seq = self._next_seq()
                    sock.sendall(frame(2, init_seq, self._encode(IDENTITY)))
                auth_deadline = time.monotonic()+10
                while True:
                    if time.monotonic()>auth_deadline:
                        raise TimeoutError('Camera authentication timed out')
                    initial = wire.read()
                    if struct.unpack_from('<H', initial, 8)[0] == 0x8002 and initial[10] == init_seq:
                        self._merge(json.loads(self.cipher.crypt(self.key, initial[11:], True).rstrip(b'\0')))
                        break
                self.error = None
                self.ready.set()
                self._authenticated_host()
                self.event('connection', 'Kamera lokal verbunden')
                while not self.stopping.is_set():
                    msg = wire.read()
                    op = struct.unpack_from('<H', msg, 8)[0]
                    seq, body = msg[10], msg[11:]
                    if (op & 0x7fff) == 1:
                        if len(body) >= 4:
                            temperature = struct.unpack_from('<i', body)[0]
                            if -4000 <= temperature <= 8000:
                                with self.lock:
                                    self.info['temperature'] = temperature/100
                                    self.temperature_at = time.monotonic()
                        continue
                    if len(body) % 16:
                        raise ValueError('Ungültige Kontrollantwort')
                    body = self.cipher.crypt(self.key, body, True)
                    if op & 0x8000:
                        if seq in self.pending:
                            expected, ev, box = self.pending[seq]
                            if expected == (op & 0x7fff):
                                try:
                                    obj = json.loads(body.rstrip(b'\0'))
                                except (ValueError, UnicodeError):
                                    obj = {}
                                self._merge(obj)
                                box.append(obj)
                                ev.set()
                    elif 0x900 <= op <= 0x919:
                        self._handle_event(op,body)
                        with self.send_lock:
                            sock.sendall(frame(op | 0x8000, seq, self.cipher.crypt(self.key, body)))
            except Exception as exc:
                self.error = str(exc) or type(exc).__name__
                LOG.warning('Control: %s', self.error)
            finally:
                self.ready.clear()
                with self.lock:
                    self.timer_observations.clear()
                    self.temperature_at = 0
                if self.sock:
                    self.sock.close()
                for _, ev, box in list(self.pending.values()):
                    box.append(ConnectionError('Kameraverbindung unterbrochen'))
                    ev.set()
                self.stopping.wait(3)

    def _maintenance(self):
        last_refresh = 0
        wake_sent = False
        while not self.stopping.wait(4):
            if self.ready.is_set():
                try:
                    with self.send_lock:
                        self.sock.sendall(frame(1, self._next_seq(), self.wrapped + b'0\0'))
                    if not wake_sent:
                        self.request(13, {'Btn_alert': 2})
                        wake_sent = True
                    if time.monotonic() - last_refresh > 30:
                        for query in (6, 8, 10):
                            self.request(query)
                        last_refresh = time.monotonic()
                except Exception as exc:
                    LOG.warning('Refresh: %s', exc)
            else:
                wake_sent = False
            if self.talk_sock and time.monotonic() - self.talk_at > 3:
                try:
                    self.stop_talk()
                except Exception:
                    LOG.exception('Talk watchdog')

    def state(self):
        with self.lock:
            now = time.monotonic()
            settings = dict(self.info)
            age = now-self.temperature_at if self.temperature_at else None
            value = settings.get('temperature')
            fresh = bool(self.ready.is_set() and age is not None and 0<=age<=30
                         and type(value) in (int,float) and -40<=value<=80)
            settings['temperature'] = value if fresh else None
            return {'connected': self.ready.is_set(), 'error': self.error,
                'video_error': self.video_error, 'video_live': self.ready.is_set() and self.media_ready.is_set() and now-self.video_at < 5,
                'audio_live': self.ready.is_set() and self.audio_ready.is_set() and self.audio_number > 0,
                'audio_active': now-self.audio_at < 5, 'video_frames': self.video_number,
                'audio_packets': self.audio_number, 'settings': settings,
                'temperature': {'fresh': fresh, 'age': round(age,1) if age is not None else None},
                'events': list(self.events), 'audio_level': round(self.audio_level) if now-self.audio_at < 2 else 0,
                'detection': {'noise': self.noise_enabled, 'noise_threshold': self.noise_threshold},
                'talking': self.talk_sock is not None, 'talk_packets': self.talk_packets,
                'talk_input_samples': self.talk_input_samples,
                'talk_input_level': round(self.talk_input_level),
                'timers': {kind:self._timer_state(kind,now) for kind in ('light','lullaby')},
                'wifi': {'rssi': self.info.get('rssi'), 'age': round(now-self.rssi_at, 1) if self.rssi_at else None},
                'resolution': f'{self.video_frame.width} × {self.video_frame.height}' if self.video_frame else None}

    def _media_loop(self):
        while not self.stopping.is_set():
            if not self.ready.wait(2):
                continue
            conn = None
            try:
                conn = self._connect((self.host, 554), 5)
                conn.settimeout(12)
                wire = Wire(conn)
                base = f'rtsp://{self.host}:554/av2_0'
                session = ''
                seq = 0
                def req(method, url, extra='', binary=False):
                    nonlocal seq, session
                    seq += 1
                    if binary:
                        data = f'OPTIONS {url} RTSP/1.0\r\nCSeq: {seq}\r\nUser-Agent:'.encode()+b'\xa5'+self.wrapped+b'\r\n\r\n'
                    else:
                        data = (f'{method} {url} RTSP/1.0\r\nCSeq: {seq}\r\nUser-Agent: sky-light (ysp20200805)\r\n'+extra+'\r\n').encode()
                    conn.sendall(data)
                    while True:
                        msg = wire.read()
                        if not isinstance(msg, bytes):
                            break
                    h, b = msg
                    if method in ('SETUP', 'PLAY'):
                        LOG.debug('RTSP %s %s: %r', method, url, h)
                    if b' 200 ' not in h.split(b'\r\n')[0]:
                        raise ConnectionError(h.split(b'\r\n')[0].decode(errors='replace'))
                    match = re.search(rb'(?im)^Session:\s*([^;\r\n]+)', h)
                    if match:
                        session = match[1].decode()
                    return h, b
                req('OPTIONS', base, binary=True)
                header, sdp = req('DESCRIBE', base, 'Accept: application/sdp\r\n')
                content_base = re.search(rb'(?im)^Content-Base:\s*([^\r\n]+)', header)
                prefix = content_base[1].decode() if content_base else base+'/'
                for kind, channel in ((b'video', 0), (b'audio', 2)):
                    section = sdp.split(b'm='+kind, 1)[1].split(b'\r\nm=', 1)[0]
                    track = re.search(rb'(?m)^a=control:([^\r\n]+)', section)[1].decode()
                    url = track if track.startswith('rtsp://') else prefix.rstrip('/')+'/'+track
                    # The parent uses the SDP control value verbatim (trackID=1).
                    # Absolute track URLs are accepted but incorrectly select video again.
                    req('SETUP', track, f'Transport: RTP/AVP/TCP;unicast;interleaved={channel}-{channel+1}\r\n'+(f'Session: {session}\r\n' if session else ''))
                req('PLAY', base, f'Session: {session}\r\nRange: npt=0.000-\r\n')
                self.media_generation += 1
                self.media_ready.set()
                last_report = time.monotonic()
                decoder = av.CodecContext.create('h264', 'r')
                def feed(nal):
                    try:
                        for p in decoder.parse(b'\0\0\0\1'+nal):
                            for v in decoder.decode(p):
                                self._publish_video(v)
                    except av.FFmpegError:
                        LOG.debug('Video decode dropped damaged frame')
                params = re.search(rb'sprop-parameter-sets=([^;\r\n]+)', sdp)
                if params:
                    for item in params[1].split(b','):
                        feed(base64.b64decode(item))
                fragment, last_seq = None, None
                self.video_error = None
                while not self.stopping.is_set() and self.ready.is_set():
                    msg = wire.read()
                    if time.monotonic()-last_report >= 8:
                        # Exact legacy receiver report from RtcpVideoSendRR in the
                        # parent firmware. This is also the camera's media keepalive.
                        conn.sendall(bytes.fromhex('240120000ac91f00')+bytes(28))
                        last_report = time.monotonic()
                    if not isinstance(msg, bytes) or msg[1] not in (0, 2):
                        continue
                    rtp = msg[4:]
                    if len(rtp) < 13:
                        continue
                    off = 12+4*(rtp[0]&15)
                    if rtp[0]&16:
                        off += 4+4*int.from_bytes(rtp[off+2:off+4], 'big')
                    payload = bytearray(rtp[off:])
                    if rtp[0]&32:
                        payload = payload[:-rtp[-1]]
                    if msg[1] == 2:
                        if self.audio_number == 0:
                            LOG.info('Audio received on RTSP interleaved channel 2')
                        self._audio(payload)
                        continue
                    if not payload:
                        continue
                    kind = payload[0]&31
                    pos = 2 if kind == 28 else 1
                    if len(payload) >= pos+16:
                        payload[pos:pos+16] = self.cipher.crypt(self.key, bytes(payload[pos:pos+16]), True)
                    cur = int.from_bytes(rtp[2:4], 'big')
                    if kind == 28:
                        if payload[1]&128:
                            fragment = bytearray([(payload[0]&224)|(payload[1]&31)])+payload[2:]
                        elif fragment is not None and last_seq is not None and cur == ((last_seq+1)&65535):
                            fragment.extend(payload[2:])
                        else:
                            fragment = None
                        if payload[1]&64 and fragment is not None:
                            feed(bytes(fragment))
                            fragment = None
                    elif 1 <= kind <= 23:
                        feed(bytes(payload))
                    last_seq = cur
            except Exception as exc:
                self.video_error = str(exc) or type(exc).__name__
                LOG.warning('Media: %s', self.video_error)
            finally:
                self.media_ready.clear()
                if conn:
                    conn.close()
                self.stopping.wait(3)

    def _publish_video(self, video):
        now = time.monotonic()
        self.video_frame, self.video_at = video, now
        self.video_number += 1

    def _audio(self, payload):
        if len(payload) < 9:
            return
        raw = bytes(payload[4:])
        aligned = len(raw)//16*16
        raw = self.cipher.crypt(self.key, raw[:aligned], True)+raw[aligned:]
        predictor, index = struct.unpack_from('<hB', raw)
        if index > 88:
            LOG.warning('Invalid ADPCM state index: %s', index)
            return
        decoded, _ = audioop.adpcm2lin(raw[4:], 2, (predictor, index))
        # The parent prepends the predictor and emits exactly 2 samples per encoded byte.
        pcm = raw[:2]+decoded[:-2]
        rms = audioop.rms(pcm, 2)
        self.audio_level = max(0, min(100, (20*np.log10(max(rms, 1)/32768)+65)/65*100))
        self.audio_at = time.monotonic()
        self.audio_number += 1
        if self.noise_enabled and self.audio_level >= self.noise_threshold:
            self.event('sound', 'Geräusch erkannt · lokal', 12)
        with self.lock:
            listeners = list(self.audio_listeners)
        for listener in listeners:
            try:
                listener(pcm)
            except RuntimeError:
                pass  # A browser event loop may have closed during fan-out.

    def _audio_loop(self):
        # This firmware advertises audio in SDP but sends it on a separate TCP socket.
        while not self.stopping.is_set():
            if not self.ready.wait(2) or not self.media_ready.wait(2):
                self.stopping.wait(1)
                continue
            conn = None
            try:
                conn = self._connect((self.host, 8687), 5)
                conn.settimeout(None)
                self.audio_ready.set()
                wire = Wire(conn)
                generation = self.media_generation
                while not self.stopping.is_set() and self.ready.is_set() and self.media_ready.is_set() and generation == self.media_generation:
                    # Silence is allowed. Closing an idle audio socket also closes
                    # the camera's video session on this firmware.
                    if not select.select([conn], [], [], 1)[0]:
                        continue
                    msg = wire.read()
                    if not isinstance(msg, bytes):
                        continue
                    rtp = msg[4:]
                    if len(rtp) < 21:
                        continue
                    offset = 12+4*(rtp[0]&15)
                    if rtp[0]&16:
                        offset += 4+4*int.from_bytes(rtp[offset+2:offset+4], 'big')
                    self._audio(rtp[offset:])
            except Exception as exc:
                LOG.warning('Audio socket: %s', str(exc) or type(exc).__name__)
            finally:
                self.audio_ready.clear()
                if conn:
                    conn.close()
                self.stopping.wait(3)

    def _message_loop(self):
        # The parent also maintains the camera's secondary authenticated session.
        while not self.stopping.is_set():
            if not self.ready.wait(2):
                continue
            conn = None
            try:
                conn = self._connect((self.host, 8684), 5)
                conn.settimeout(4)
                wire = ControlWire(conn)
                seq = 0
                while not self.stopping.is_set() and self.ready.is_set():
                    conn.sendall(frame(0x7001, seq, self.wrapped+b'0\0'))
                    seq = (seq+1)%256
                    try:
                        msg = wire.read()
                        op = struct.unpack_from('<H', msg, 8)[0]
                        LOG.debug('Secondary reply opcode=%04x bytes=%d', op, len(msg))
                        if not op&0x8000:
                            conn.sendall(frame(op|0x8000, msg[10], msg[11:]))
                    except socket.timeout:
                        pass
                    self.stopping.wait(2)
            except Exception as exc:
                LOG.warning('Secondary control: %s', str(exc) or type(exc).__name__)
            finally:
                if conn:
                    conn.close()
                self.stopping.wait(3)

    def start_talk(self):
        with self.talk_lock:
            if self.talk_sock:
                self.talk_at = time.monotonic()
                return
            self.request(14, {'TalkBack_ctl': 1})
            try:
                self.talk_sock = self._connect((self.host, 8686), 5)
                self.talk_sock.settimeout(2)
                self.talk_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.talk_buffer.clear()
                self.talk_index = 0
                self.talk_input_level = 0
                self.talk_at = time.monotonic()
            except Exception:
                if self.talk_sock:
                    self.talk_sock.close()
                    self.talk_sock = None
                self.request(14, {'TalkBack_ctl': 0})
                raise

    def talk_pcm(self, pcm):
        with self.talk_lock:
            if not self.talk_sock or not pcm:
                return
            if len(pcm) % 2:
                raise ValueError('16-bit microphone PCM must contain whole samples')
            self.talk_input_samples += len(pcm)//2
            rms = audioop.rms(pcm, 2)
            self.talk_input_level = max(0, min(100, (20*np.log10(max(rms, 1)/32768)+65)/65*100))
            self.talk_buffer.extend(pcm)
            # AiInit/get_pcm_frame_len: 16 kHz, mono, 1280-byte PCM / 40 ms.
            # AiThreadFunc carries the IMA step index across consecutive frames.
            while len(self.talk_buffer) >= 1280:
                block = bytes(self.talk_buffer[:1280])
                del self.talk_buffer[:1280]
                predictor = struct.unpack_from('<h', block)[0]
                index = self.talk_index
                encoded, (_, self.talk_index) = audioop.lin2adpcm(block[2:]+block[-2:], 2, (predictor, index))
                raw = struct.pack('<hBB', predictor, index, 0)+encoded
                size = len(raw)+7
                header = bytes((255, 240, 0, (size>>11)&3, (size>>3)&255, (size<<5)&255, 0))
                crc = binascii.crc_hqx(raw, 0x1234)
                n = len(raw)//16*16
                encrypted = self.cipher.crypt(self.key, raw[:n])+raw[n:]
                self.talk_sock.sendall(b'SWSW'+struct.pack('<I', size)+header+struct.pack('<H', crc)+b'\0\0'+encrypted)
                self.talk_packets += 1
            self.talk_at = time.monotonic()

    def stop_talk(self):
        with self.talk_lock:
            self.talk_buffer.clear()
            self.talk_index = 0
            self.talk_input_level = 0
            if self.talk_sock:
                self.talk_sock.close()
                self.talk_sock = None
                self.request(14, {'TalkBack_ctl': 0})

    def close(self):
        try:
            self.stop_talk()
        except (OSError, TimeoutError, ConnectionError):
            pass
        self.stopping.set()
        self.ready.clear()
        self.media_ready.clear()
        with self.sockets_lock:
            sockets=list(self.sockets)
            self.sockets.clear()
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        for thread in self.threads:
            thread.join(timeout=2)
