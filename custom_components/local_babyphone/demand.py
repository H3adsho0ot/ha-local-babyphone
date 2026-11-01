"""Hold a native camera session only while WebRTC viewers need it."""
import asyncio


class DemandConnection:
    def __init__(self, client, factory, changed, idle_seconds=10):
        self.client=client
        self.factory=factory
        self.changed=changed
        self.idle_seconds=idle_seconds
        self.viewers=set()
        self.started=False
        self.closed=False
        self.lock=asyncio.Lock()
        self.idle_task=None

    def state(self):
        return {'mode':'active' if self.started else 'idle',
                'viewers':len(self.viewers),'release_after':self.idle_seconds}

    async def acquire(self, viewer):
        async with self.lock:
            if self.closed:raise ConnectionError('Integration is shutting down')
            if self.idle_task:
                self.idle_task.cancel()
                self.idle_task=None
            self.viewers.add(viewer)
            if not self.started:
                if self.client.stopping.is_set():
                    previous=self.client
                    self.client=self.factory()
                    for field in ('noise_enabled','noise_threshold'):
                        setattr(self.client,field,getattr(previous,field))
                self.started=True
                self.client.start()
                self.changed(self.client)
            return self.client

    async def release(self, viewer):
        async with self.lock:
            self.viewers.discard(viewer)
            if not self.viewers and self.started and not self.closed and not self.idle_task:
                self.idle_task=asyncio.create_task(self._idle())

    async def _idle(self):
        try:
            await asyncio.sleep(self.idle_seconds)
            async with self.lock:
                # Acquiring a new viewer cancels the timer before this lock.
                # Once close begins, clear the timer so it cannot be cancelled
                # halfway through socket/thread cleanup by a new acquire.
                self.idle_task=None
                if self.viewers or self.closed:return
                await asyncio.to_thread(self.client.close)
                self.started=False
                self.changed(self.client)
        except asyncio.CancelledError:
            pass

    async def close(self):
        async with self.lock:
            self.closed=True
            if self.idle_task:
                self.idle_task.cancel()
                self.idle_task=None
            self.viewers.clear()
            await asyncio.to_thread(self.client.close)
            self.started=False
            self.changed(self.client)
