"""Process-local, leased workspaces for the disposable public demo.

Request context selects a workspace; worker submissions capture it explicitly.
No client input is ever interpreted as a filesystem path.
"""
import hashlib
import os
import re
import secrets
import shutil
import tempfile
import time
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock


class DemoError(Exception):
    def __init__(self, message, status=429):
        super().__init__(message)
        self.status = status


class SessionEnded(DemoError):
    def __init__(self):
        super().__init__('This temporary session has ended. Start a new demo to continue.', 401)


current_workspace = ContextVar('weaver_workspace', default=None)
current_admission = ContextVar('weaver_admission', default=None)


def setting(name, default):
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f'{name} must be positive')
    return value


@dataclass(eq=False)
class Workspace:
    manager: object
    path: Path
    created: float
    touched: float
    client: str
    active: int = 0
    revoked: bool = False
    starts: int = 0
    outstanding: bool = False
    futures: set = field(default_factory=set)


@dataclass(eq=False)
class Admission:
    workspace: Workspace
    committed: bool = False
    background: bool = False
    released: bool = False


class DemoSessions:
    def __init__(self):
        self.lock = RLock()
        self.root = Path(tempfile.mkdtemp(prefix='weaver-demo-'))
        self.sessions = {}
        self.admissions = set()
        self.rates = OrderedDict()
        self.now = time.monotonic
        self.idle = setting('WEAVER_DEMO_IDLE_SECONDS', 3600)
        self.lifetime = setting('WEAVER_DEMO_LIFETIME_SECONDS', 86400)
        self.max_sessions = setting('WEAVER_DEMO_MAX_SESSIONS', 100)
        self.max_entries = setting('WEAVER_DEMO_MAX_ENTRIES', 20)
        self.max_starts = setting('WEAVER_DEMO_MAX_ORGANIZATIONS', 10)
        self.workers = setting('WEAVER_DEMO_WORKERS', 2)
        self.capacity = self.workers + setting('WEAVER_DEMO_QUEUE_SIZE', 4)
        self.max_calls = setting('WEAVER_DEMO_PROVIDER_CALLS', 500)
        self.calls = 0
        self.calls_day = 0
        self.closed = False

    def _expired(self, ws):
        now = self.now()
        return ws.revoked or now - ws.touched >= self.idle or now - ws.created >= self.lifetime

    def _discard(self, ws):
        if ws.revoked and ws.active == 0:
            shutil.rmtree(ws.path.parent, ignore_errors=True)

    def _revoke(self, ws):
        ws.revoked = True
        for digest, value in list(self.sessions.items()):
            if value is ws:
                del self.sessions[digest]
        for future in list(ws.futures):
            future.cancel()
        self._discard(ws)

    def cleanup(self):
        with self.lock:
            for ws in list(self.sessions.values()):
                if self._expired(ws):
                    self._revoke(ws)
            now = self.now()
            for key, (_, end) in list(self.rates.items()):
                if end <= now:
                    del self.rates[key]

    def rate(self, kind, client, limit, seconds=3600):
        # client is hashed before use. Bound the map even for many distinct IPs.
        with self.lock:
            key = (kind, client)
            now = self.now()
            count, end = self.rates.get(key, (0, now + seconds))
            if end <= now:
                count, end = 0, now + seconds
            if count >= limit:
                raise DemoError('The demo is busy or this browser network reached its limit. Please try again later.')
            if key not in self.rates and len(self.rates) >= 2000:
                # Do not evict a live limit and let rotating clients bypass it.
                raise DemoError('The demo is busy. Please try again later.', 503)
            self.rates[key] = (count + 1, end)

    @staticmethod
    def client_key(address):
        return hashlib.sha256(address.encode()).hexdigest()

    def create(self, client, initialize):
        with self.lock:
            self.cleanup()
            self.rate('sessions', client, setting('WEAVER_DEMO_SESSIONS_PER_HOUR', 10))
            if self.closed or len(self.sessions) >= self.max_sessions:
                raise DemoError('The demo is at capacity. Please try again later.', 503)
            token = secrets.token_urlsafe(32)
            now = self.now()
            ws = Workspace(self, self.root / secrets.token_hex(16) / 'workspace.sqlite3', now, now, client)
            digest = hashlib.sha256(token.encode()).hexdigest()
            self.sessions[digest] = ws
            try:
                initialize(ws)
            except Exception:
                self._revoke(ws)
                raise
            return {'token': token, 'idle_seconds': self.idle, 'lifetime_seconds': self.lifetime}

    @contextmanager
    def lease(self, credential):
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', credential):
            raise SessionEnded()
        digest = hashlib.sha256(credential[7:].encode()).hexdigest()
        with self.lock:
            ws = self.sessions.get(digest)
            if ws is None:
                raise SessionEnded()
            self.check(ws)
            ws.active += 1
        token = current_workspace.set(ws)
        try:
            yield ws
        finally:
            current_workspace.reset(token)
            with self.lock:
                ws.active -= 1
                self._discard(ws)

    def check(self, ws):
        if self.closed or self._expired(ws):
            self._revoke(ws)
            raise SessionEnded()

    @contextmanager
    def guard(self, ws):
        # Publication and reset are mutually exclusive, including the commit.
        with self.lock:
            self.check(ws)
            yield

    def touch(self, ws):
        with self.lock:
            self.check(ws)
            ws.touched = self.now()

    def reserve(self, ws, client):
        with self.lock:
            self.check(ws)
            if ws.outstanding:
                raise DemoError('Your previous entry is still organizing. Please wait before submitting another.')
            if ws.starts >= self.max_starts:
                raise DemoError('This temporary session reached its organization limit.')
            if len(self.admissions) >= self.capacity:
                raise DemoError('Organization is busy. Your draft is still here; please try again shortly.', 503)
            self.rate('organizations', client, setting('WEAVER_DEMO_ORGANIZATIONS_PER_HOUR', 30))
            ticket = Admission(ws)
            self.admissions.add(ticket)
            ws.outstanding = True
            return ticket

    def commit(self, ticket, background=False):
        with self.lock:
            self.check(ticket.workspace)
            if ticket.released or ticket.committed:
                raise DemoError('This organization request is no longer available.', 409)
            ticket.committed = True
            ticket.background = background
            ticket.workspace.starts += 1
            if background:
                ticket.workspace.active += 1

    def release(self, ticket):
        with self.lock:
            if ticket.released:
                return
            ticket.released = True
            self.admissions.discard(ticket)
            ws = ticket.workspace
            ws.outstanding = False
            if ticket.background:
                ws.active -= 1
            self._discard(ws)

    def provider_call(self, ws):
        with self.lock:
            self.check(ws)
            day = int(self.now() // 86400)
            if day != self.calls_day:
                self.calls_day, self.calls = day, 0
            if self.calls >= self.max_calls:
                raise DemoError('The demo reached its inference allowance. Your writing is saved; please try again later.')
            self.calls += 1

    def close(self):
        with self.lock:
            self.closed = True
            for ws in list(self.sessions.values()):
                self._revoke(ws)
            shutil.rmtree(self.root, ignore_errors=True)


def before_provider_call():
    ws = current_workspace.get()
    if ws is not None:
        ws.manager.provider_call(ws)


class DemoBodyLimit:
    """Bound a demo API body before JSON parsing, including chunked requests."""
    def __init__(self, app, enabled):
        self.app, self.enabled = app, enabled

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not self.enabled() or not scope.get('path', '').startswith('/api/'):
            return await self.app(scope, receive, send)
        data = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(data) + len(chunk) > 65536:
                from starlette.responses import JSONResponse
                return await JSONResponse({'detail': 'This demo request is too large.'}, status_code=413)(scope, receive, send)
            data.extend(chunk)
            if not message.get('more_body', False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(data), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)
