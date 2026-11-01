"""WebRTC fan-out of one locally decrypted camera stream."""
import asyncio
from dataclasses import dataclass, field
from fractions import Fraction
import time
import logging
import av
from .vendor.aiortc import RTCPeerConnection,RTCSessionDescription,RTCConfiguration,VideoStreamTrack,AudioStreamTrack
from .vendor.aiortc.mediastreams import MediaStreamError
from .vendor.aiortc.sdp import candidate_from_sdp
from .vendor.aiortc.exceptions import InvalidStateError

LOG = logging.getLogger(__name__)


class VideoTrack(VideoStreamTrack):
    def __init__(self,client):
        super().__init__();self.client=client;self.last=0;self.origin=time.monotonic()

    async def recv(self):
        while self.readyState=='live':
            frame,number=self.client.video_frame,self.client.video_number
            if frame is not None and number!=self.last:
                self.last=number
                out=av.VideoFrame.from_ndarray(frame.reformat(format='yuv420p').to_ndarray(),format='yuv420p')
                out.pts=int((time.monotonic()-self.origin)*90000);out.time_base=Fraction(1,90000)
                return out
            await asyncio.sleep(.015)
        raise MediaStreamError


class AudioTrack(AudioStreamTrack):
    def __init__(self,client):
        super().__init__();self.client=client;self.loop=asyncio.get_running_loop()
        self.queue=asyncio.Queue(maxsize=15);self.buffer=bytearray();self.pts=0;self.origin=None
        self.callback=lambda pcm:self.loop.call_soon_threadsafe(self._offer,pcm)
        with client.lock:client.audio_listeners.add(self.callback)

    def _offer(self,pcm):
        if self.readyState!='live':return
        if self.queue.full():self.queue.get_nowait()
        self.queue.put_nowait(pcm)

    async def recv(self):
        while len(self.buffer)<640:
            try:self.buffer.extend(await asyncio.wait_for(self.queue.get(),.02))
            except TimeoutError:self.buffer.extend(bytes(640))
        if self.origin is None:self.origin=time.monotonic()
        delay=self.origin+self.pts/16000-time.monotonic()
        if delay>0:await asyncio.sleep(delay)
        elif delay<-.5:self.origin=time.monotonic()-self.pts/16000
        frame=av.AudioFrame(format='s16',layout='mono',samples=320)
        frame.planes[0].update(bytes(self.buffer[:640]));del self.buffer[:640]
        frame.sample_rate=16000;frame.time_base=Fraction(1,16000);frame.pts=self.pts;self.pts+=320
        return frame

    def stop(self):
        with self.client.lock:self.client.audio_listeners.discard(self.callback)
        super().stop()


@dataclass
class Session:
    peer: RTCPeerConnection
    tracks: list=field(default_factory=list)
    task: asyncio.Task|None=None
    timeout: asyncio.Task|None=None


class MediaManager:
    def __init__(self,client,demand=None):
        self.client=client;self.demand=demand;self.sessions={};self.talk_owner=None;self.talk_lock=asyncio.Lock();self.closing=False

    def _check_session(self,session_id,session):
        if self.closing or self.sessions.get(session_id) is not session or session.peer.connectionState=='closed':
            raise ConnectionError('Live connection closed. Reconnect the live view.')

    async def offer(self,sdp,session_id):
        if self.closing:raise ConnectionError('Integration is shutting down')
        if session_id in self.sessions:raise ValueError('Session already exists')
        if len(self.sessions)>=4:raise ConnectionError('A maximum of four simultaneous views is supported')
        peer=RTCPeerConnection(RTCConfiguration(iceServers=[]))
        session=Session(peer,[])
        self.sessions[session_id]=session
        @peer.on('track')
        def incoming(track):
            if track.kind=='audio':session.task=asyncio.create_task(self._consume_mic(track,session_id))
        @peer.on('connectionstatechange')
        async def state_changed():
            if peer.connectionState=='connected' and session.timeout:session.timeout.cancel()
            if peer.connectionState in ('failed','disconnected','closed'):
                await self.close_session(session_id)
        try:
            if self.demand:
                client=await self.demand.acquire(session_id)
                if not await asyncio.to_thread(client.ready.wait,12):
                    raise ConnectionError('No authenticated connection to the baby unit')
            else:client=self.client
            self._check_session(session_id,session)
            session.tracks=[VideoTrack(client),AudioTrack(client)]
            async def expire():
                await asyncio.sleep(30)
                if peer.connectionState!='connected':await self.close_session(session_id)
            session.timeout=asyncio.create_task(expire())
            await peer.setRemoteDescription(RTCSessionDescription(sdp=sdp,type='offer'))
            self._check_session(session_id,session)
            for track in session.tracks:peer.addTrack(track)
            await peer.setLocalDescription(await peer.createAnswer())
            self._check_session(session_id,session)
            return peer.localDescription.sdp
        except BaseException as exc:
            await self.close_session(session_id)
            if isinstance(exc,InvalidStateError):
                raise ConnectionError('Live connection closed during setup.') from exc
            raise

    async def candidate(self,session_id,candidate):
        session=self.sessions.get(session_id)
        if not session:raise ValueError('Unknown media session')
        data=candidate.to_dict() if hasattr(candidate,'to_dict') else candidate
        text=data.get('candidate','')
        parsed=candidate_from_sdp(text.removeprefix('candidate:')) if text else None
        if parsed:
            parsed.sdpMid=data.get('sdpMid');parsed.sdpMLineIndex=data.get('sdpMLineIndex')
        await session.peer.addIceCandidate(parsed)

    async def start_talk(self,session_id):
        async with self.talk_lock:
            session=self.sessions.get(session_id)
            if not session or session.peer.connectionState!='connected':raise ValueError('Connect the live view first')
            if self.talk_owner and self.talk_owner!=session_id:raise ValueError('Talkback is already active in another view')
            await asyncio.to_thread(self.client.start_talk)
            self.talk_owner=session_id

    async def stop_talk(self,session_id):
        async with self.talk_lock:
            if self.talk_owner==session_id:
                self.talk_owner=None
                await asyncio.to_thread(self.client.stop_talk)

    async def _consume_mic(self,track,session_id):
        resampler=None
        try:
            while True:
                source=await track.recv()
                if self.talk_owner==session_id and self.client.talk_sock:
                    if resampler is None:
                        resampler=av.AudioResampler(format='s16',layout='mono',rate=16000)
                    # Browser RTP timestamps may jump when replaceTrack(null) is
                    # resumed. Each press has its own sample-continuous converter.
                    source.pts=None
                    for frame in resampler.resample(source):
                        await asyncio.to_thread(self.client.talk_pcm,bytes(frame.planes[0])[:frame.samples*2])
                else:
                    resampler=None
        except (MediaStreamError,asyncio.CancelledError,OSError):
            pass
        except Exception:
            LOG.exception('Microphone conversion failed')
        finally:
            await self.stop_talk(session_id)

    async def close_session(self,session_id):
        session=self.sessions.pop(session_id,None)
        if not session:return
        try:await self.stop_talk(session_id)
        finally:
            if session.timeout and session.timeout is not asyncio.current_task():session.timeout.cancel()
            for track in session.tracks:track.stop()
            if session.task and session.task is not asyncio.current_task():
                session.task.cancel()
                await asyncio.gather(session.task,return_exceptions=True)
            try:await session.peer.close()
            finally:
                if self.demand:await self.demand.release(session_id)

    async def close(self):
        self.closing=True
        await asyncio.gather(*(self.close_session(s) for s in list(self.sessions)),return_exceptions=True)
