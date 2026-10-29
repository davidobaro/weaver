import asyncio
import json
import os
import re
import sqlite3
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager, nullcontext, suppress
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from typing import Literal
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from uuid import UUID, uuid4
from .demo import DemoSessions, DemoError, SessionEnded, DemoBodyLimit, current_workspace, current_admission
from .notifications import claim as claim_notifications
from .recurrence import act_on_occurrence
from .auto_recurrence import discover_repeats
from .search import search_workspace
from .suggestion_quality import coalesce_suggestions, related_suggestions

from .inference import InferenceError, extract_memories
from .models import NoteInput, ReviewInput, MemoryEdit, SuggestionAction, ReminderTiming, ReminderRepeat, AliasInput, PersonPair, EntryEdit, EntryRestore
from .for_you import build_suggestions
from .utils import name_key, entry_text
from .personal import publish_personal
from .completions import publish_completions
from .profiles import profile_about
from .noticed import entry_notices
from .revisions import archive_entry, retire_generated, historical_entry, current_predecessor
from .identities import (IdentityError, aliases_for, add_alias, get_or_create_person,
                         possible_matches, mentioned, merge_people, undo_merge, fingerprint)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DB_PATH = Path(os.getenv('WEAVER_DB_PATH') or ROOT / 'data' / 'weaver.sqlite3')


@contextmanager
def database(workspace=None):
    workspace = workspace or current_workspace.get()
    if getattr(app.state, 'demo', None) is not None and workspace is None:
        raise SessionEnded()
    path = workspace.path if workspace else DB_PATH
    with workspace.manager.guard(workspace) if workspace else nullcontext():
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def initialize(workspace=None):
    with database(workspace) as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.execute('PRAGMA synchronous = NORMAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY, text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', candidates TEXT,
                error TEXT, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES people(id),
                note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                category TEXT NOT NULL, value TEXT NOT NULL, evidence TEXT NOT NULL,
                edited INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
                replaces_id INTEGER REFERENCES memories(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_memories_person_id ON memories(person_id);
            CREATE INDEX IF NOT EXISTS idx_memories_note_id ON memories(note_id);
            CREATE TABLE IF NOT EXISTS suggestion_actions (
                suggestion_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS reminder_recurrence (
                suggestion_id TEXT PRIMARY KEY, frequency TEXT NOT NULL,
                anchor_date TEXT NOT NULL, next_due TEXT NOT NULL,
                occurrence_key TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'manual'
            );
            CREATE TABLE IF NOT EXISTS reminder_repeat_choices (
                suggestion_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS reminder_occurrences (
                suggestion_id TEXT NOT NULL, occurrence_key TEXT NOT NULL,
                due_date TEXT NOT NULL, frequency TEXT NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY(suggestion_id, occurrence_key)
            );
            CREATE TABLE IF NOT EXISTS notification_receipts (
                device TEXT NOT NULL, event_key TEXT NOT NULL,
                token TEXT NOT NULL, claimed_at REAL NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(device, event_key)
            );
            CREATE TABLE IF NOT EXISTS suggestion_timing (
                suggestion_id TEXT PRIMARY KEY, due_date TEXT,
                due_overridden INTEGER NOT NULL DEFAULT 0,
                snoozed_until TEXT,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
        ''')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS person_aliases (
                name_key TEXT PRIMARY KEY, name TEXT NOT NULL,
                person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_person_aliases_person_id ON person_aliases(person_id);
            CREATE TABLE IF NOT EXISTS distinct_people (
                first_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                second_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                PRIMARY KEY(first_id, second_id), CHECK(first_id < second_id)
            );
            CREATE TABLE IF NOT EXISTS people_merges (
                id TEXT PRIMARY KEY, target_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                source_name TEXT NOT NULL, snapshot TEXT NOT NULL, fingerprint TEXT NOT NULL,
                undone INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
        ''')
        if 'origin' not in {row['name'] for row in db.execute('PRAGMA table_info(reminder_recurrence)')}:
            db.execute("ALTER TABLE reminder_recurrence ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")
        columns = {row['name'] for row in db.execute('PRAGMA table_info(notes)')}
        if 'automatic' not in columns:
            db.execute('ALTER TABLE notes ADD COLUMN automatic INTEGER NOT NULL DEFAULT 0')
        for column, definition in [('kind', "TEXT NOT NULL DEFAULT 'note'"),
                                   ('title', "TEXT NOT NULL DEFAULT ''"), ('entry_date', 'TEXT'),
                                   ('revision', 'INTEGER NOT NULL DEFAULT 1'), ('updated_at', 'TEXT')]:
            if column not in columns:
                db.execute(f'ALTER TABLE notes ADD COLUMN {column} {definition}')
        if 'note_revision' not in {row['name'] for row in db.execute('PRAGMA table_info(memories)')}:
            db.execute('ALTER TABLE memories ADD COLUMN note_revision INTEGER NOT NULL DEFAULT 1')
        if 'personal_candidates' not in columns:
            db.execute('ALTER TABLE notes ADD COLUMN personal_candidates TEXT')
        if 'completion_candidates' not in columns:
            db.execute('ALTER TABLE notes ADD COLUMN completion_candidates TEXT')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS personal_reminders (
                id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                note_revision INTEGER NOT NULL, category TEXT NOT NULL,
                value TEXT NOT NULL, evidence TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_personal_reminders_note_id ON personal_reminders(note_id);
            CREATE TABLE IF NOT EXISTS personal_completions (
                id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                note_revision INTEGER NOT NULL,
                reminder_id INTEGER NOT NULL REFERENCES personal_reminders(id) ON DELETE CASCADE,
                evidence TEXT NOT NULL,
                UNIQUE(note_id,note_revision,reminder_id)
            );
            CREATE INDEX IF NOT EXISTS idx_personal_completions_reminder_id ON personal_completions(reminder_id);
            CREATE TABLE IF NOT EXISTS note_versions (
                note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, text TEXT NOT NULL, title TEXT NOT NULL,
                kind TEXT NOT NULL, entry_date TEXT, saved_at TEXT NOT NULL,
                PRIMARY KEY(note_id, revision)
            );
            INSERT OR IGNORE INTO note_versions(note_id,revision,text,title,kind,entry_date,saved_at)
                SELECT id,revision,text,title,kind,entry_date,COALESCE(updated_at,created_at) FROM notes;
        ''')


@asynccontextmanager
async def lifespan(app):
    mode = os.getenv('WEAVER_MODE', 'local')
    if mode not in {'local', 'demo'}:
        raise ValueError('WEAVER_MODE must be local or demo')
    if mode == 'demo' and not os.getenv('NEBIUS_API_KEY', '').strip():
        raise ValueError('Demo mode requires a server-side NEBIUS_API_KEY')
    app.state.demo = DemoSessions() if mode == 'demo' else None
    app.state.worker = ThreadPoolExecutor(max_workers=app.state.demo.workers if app.state.demo else 1, thread_name_prefix='weaver-organizer')
    async def cleanup():
        while True:
            await asyncio.sleep(30)
            app.state.demo.cleanup()
    reaper = asyncio.create_task(cleanup()) if app.state.demo else None
    if not app.state.demo:
        initialize()
        with database() as db:
            db.execute("UPDATE notes SET status = 'queued' WHERE automatic = 1 AND status = 'processing'")
            unfinished = [row['id'] for row in db.execute("SELECT id FROM notes WHERE automatic = 1 AND status = 'queued' ORDER BY id")]
        for note_id in unfinished:
            app.state.worker.submit(organize_note, note_id)
    try:
        yield
    finally:
        if reaper:
            reaper.cancel()
            with suppress(asyncio.CancelledError):
                await reaper
        if app.state.demo:
            with app.state.demo.lock:
                for workspace in list(app.state.demo.sessions.values()):
                    app.state.demo._revoke(workspace)
        app.state.worker.shutdown(wait=True, cancel_futures=True)
        if app.state.demo:
            app.state.demo.close()
        app.state.demo = None


app = FastAPI(title='Weaver', lifespan=lifespan)
app.add_middleware(DemoBodyLimit, enabled=lambda: getattr(app.state, 'demo', None) is not None)


@app.middleware('http')
async def local_only(request: Request, call_next):
    # Local mode stays on loopback. Demo mode additionally requires a leased
    # workspace credential for every data route; origins remain explicit.
    host_raw = request.headers.get('host', '')
    host = host_raw.lstrip('[').split(']')[0].split(':')[0]
    allowed_hosts = {'localhost', '127.0.0.1', '::1', 'testserver'}
    extra_hosts = {h.strip() for h in os.getenv('WEAVER_ALLOWED_HOSTS', '').split(',') if h.strip()}
    render_host = os.getenv('RENDER_EXTERNAL_HOSTNAME', '') if getattr(app.state, 'demo', None) else ''
    if render_host:
        extra_hosts.add(render_host)
    if host not in (allowed_hosts | extra_hosts):
        return JSONResponse({'detail': 'Weaver is a local application.'}, status_code=403)
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        allowed_origins = {'http://localhost:5173', 'http://127.0.0.1:5173',
                           'http://localhost:8000', 'http://127.0.0.1:8000',
                           'http://[::1]:5173', 'http://[::1]:8000'}
        extra_origins = {o.strip() for o in os.getenv('WEAVER_ALLOWED_ORIGINS', '').split(',') if o.strip()}
        if render_host:
            extra_origins.add(f'https://{render_host}')
        if getattr(app.state, 'demo', None):
            extra_origins.update({'http://127.0.0.1:8001', 'http://localhost:8001'})
        if origin and origin not in (allowed_origins | extra_origins):
            return JSONResponse({'detail': 'This origin is not allowed.'}, status_code=403)
    manager = getattr(app.state, 'demo', None)
    path = request.url.path
    try:
        if not manager or not path.startswith('/api/') or path == '/api/config' or (path == '/api/session' and request.method == 'POST'):
            response = await call_next(request)
        else:
            with manager.lease(request.headers.get('authorization', '')) as workspace:
                ticket = None
                marker = None
                try:
                    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                        manager.rate('writes', workspace.client, 120, 60)
                        if not path.startswith('/api/notifications/'):
                            manager.touch(workspace)
                    inference_write = (request.method == 'POST' and (path == '/api/notes' or re.fullmatch(r'/api/notes/\d+/(organize|extract|restore)', path))) or (request.method == 'PATCH' and re.fullmatch(r'/api/notes/\d+', path))
                    if inference_write:
                        client = manager.client_key(request.client.host if request.client else 'unknown')
                        ticket = manager.reserve(workspace, client)
                        marker = current_admission.set(ticket)
                    response = await call_next(request)
                finally:
                    if marker is not None:
                        current_admission.reset(marker)
                    if ticket is not None and not ticket.background:
                        manager.release(ticket)
        if path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Vary'] = 'Authorization'
        return response
    except DemoError as exc:
        return JSONResponse({'detail': str(exc)}, status_code=exc.status, headers={'Cache-Control': 'no-store'})


@app.exception_handler(DemoError)
async def demo_error(request: Request, exc: DemoError):
    return JSONResponse({'detail': str(exc)}, status_code=exc.status)


@app.get('/healthz')
def health():
    return {'status': 'ok'}


@app.get('/api/config')
def configuration():
    manager = getattr(app.state, 'demo', None)
    return {'mode': 'demo' if manager else 'local', 'idle_seconds': manager.idle if manager else None}


@app.post('/api/session', status_code=201)
def create_session(request: Request):
    manager = getattr(app.state, 'demo', None)
    if not manager:
        raise HTTPException(404, 'Temporary sessions are only available in demo mode.')
    client = manager.client_key(request.client.host if request.client else 'unknown')
    return manager.create(client, initialize)


@app.post('/api/session/activity')
def session_activity():
    # Only explicit user interactions call this; periodic GET polling does not.
    return {'active': True}


@app.delete('/api/session', status_code=204)
def reset_session():
    workspace = current_workspace.get()
    if not workspace:
        raise HTTPException(404, 'Temporary sessions are only available in demo mode.')
    with workspace.manager.lock:
        workspace.manager._revoke(workspace)


def submit_organization(note_id):
    workspace = current_workspace.get()
    if workspace is None:
        return app.state.worker.submit(organize_note, note_id)
    manager = workspace.manager
    ticket = current_admission.get()
    if ticket is None:
        raise DemoError('Organization needs a valid demo request.', 409)
    manager.commit(ticket, background=True)
    try:
        future = app.state.worker.submit(run_workspace_job, workspace, note_id)
        with manager.lock:
            workspace.futures.add(future)
        def finished(done):
            with manager.lock:
                workspace.futures.discard(done)
                manager.release(ticket)
        future.add_done_callback(finished)
        return future
    except Exception:
        manager.release(ticket)
        raise


def run_workspace_job(workspace, note_id):
    marker = current_workspace.set(workspace)
    try:
        with workspace.manager.guard(workspace):
            pass
        organize_note(note_id)
    except SessionEnded:
        pass
    finally:
        current_workspace.reset(marker)


def note_or_404(db, note_id):
    row = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Note not found.')
    result = dict(row)
    for field in ('candidates', 'personal_candidates', 'completion_candidates'):
        result[field] = json.loads(result[field]) if result[field] else None
    return result


@app.get('/api/state')
def state():
    with database() as db:
        notes_rows = db.execute('SELECT * FROM notes ORDER BY id DESC').fetchall()
        notes = []
        for row in notes_rows:
            note = dict(row)
            for field in ('candidates', 'personal_candidates', 'completion_candidates'):
                note[field] = json.loads(note[field]) if note[field] else None
            notes.append(note)
        notices = entry_notices(db, notes)
        for note in notes:
            noticed = notices.get(note['id'])
            note['noticed'] = {key: noticed[key] for key in ('counts','version')} if noticed else None
        notes_by_id = {note['id']: note for note in notes}
        source_dates = {(row['note_id'], row['revision']): row['entry_date'] for row in db.execute('SELECT note_id, revision, entry_date FROM note_versions')}
        people = [dict(row) for row in db.execute('SELECT id, name FROM people ORDER BY name COLLATE NOCASE')]
        all_aliases = defaultdict(list)
        for row in db.execute('SELECT person_id, name, name_key FROM person_aliases ORDER BY name_key'):
            all_aliases[row['person_id']].append({'name': row['name'], 'name_key': row['name_key']})
        all_memories = defaultdict(list)
        for row in db.execute('SELECT * FROM memories ORDER BY id DESC'):
            all_memories[row['person_id']].append(dict(row))
        for person in people:
            person['aliases'] = all_aliases[person['id']]
            person['memories'] = all_memories[person['id']]
            person['about'] = profile_about(person['memories'], notes_by_id, source_dates)
        matches = possible_matches(db, people)
        merges = [dict(row) for row in db.execute('SELECT id,target_id,source_name,created_at,fingerprint FROM people_merges WHERE undone=0 ORDER BY created_at DESC LIMIT 5')]
        for event in merges:
            event['can_undo'] = fingerprint(db, event['target_id']) == event.pop('fingerprint')
    return {'notes': notes, 'people': people, 'identity_matches': matches, 'people_merges': merges, 'inference_configured': bool(os.getenv('NEBIUS_API_KEY')),
            'model': os.getenv('NEBIUS_MODEL') or 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'}


@app.get('/api/notes/{note_id}/noticed')
def what_was_noticed(note_id: int):
    with database() as db:
        note = note_or_404(db, note_id)
        return entry_notices(db, [note], note_id).get(note_id, {'counts':None,'version':None,'people':[],'items':[]})


def run_extraction(note_id):
    with database() as db:
        note = note_or_404(db, note_id)
        if note['status'] != 'pending':
            raise HTTPException(409, 'This note has already been reviewed.')
    ticket = current_admission.get()
    if ticket:
        ticket.workspace.manager.commit(ticket)
    try:
        result = extract_memories(entry_text(note))
    except InferenceError as exc:
        with database() as db:
            db.execute('UPDATE notes SET error = ? WHERE id = ? AND status = ?', (str(exc), note_id, 'pending'))
        raise HTTPException(502, detail={'message': str(exc), 'note_id': note_id}) from exc
    with database() as db:
        changed = db.execute("UPDATE notes SET candidates = ?, personal_candidates = ?, completion_candidates = ?, error = NULL WHERE id = ? AND status = 'pending' AND revision = ?",
                             (json.dumps([item.model_dump() for item in result.memories]),
                              json.dumps([item.model_dump() for item in result.personal]),
                              json.dumps([item.model_dump() for item in result.completed_personal]), note_id, note['revision']))
        if not changed.rowcount:
            raise HTTPException(409, 'This note has already been reviewed.')
        return note_or_404(db, note_id)


def fact_key(value):
    return re.sub(r'[^\w]+', ' ', value.casefold()).strip()


def relevant_people(db, text):
    people = []
    for row in db.execute('SELECT id, name FROM people'):
        if not mentioned(db, row, text):
            continue
        person = dict(row)
        person['aliases'] = [alias['name'] for alias in aliases_for(db, row['id'])]
        person['memories'] = [dict(m) for m in db.execute(
            'SELECT id, category, value FROM memories WHERE person_id = ? AND active = 1', (row['id'],))]
        people.append(person)
    return people


def organize_note(note_id):
    note = {}
    try:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            claimed = db.execute("UPDATE notes SET status = 'processing', error = NULL WHERE id = ? AND status = 'queued'", (note_id,))
            if not claimed.rowcount:
                return
            note = note_or_404(db, note_id)
            known_people = relevant_people(db, entry_text(note))
        # Existing proposals can be organized without another inference call.
        candidates = note['candidates']
        personal_candidates = note['personal_candidates'] or []
        completion_candidates = note['completion_candidates'] or []
        if candidates is None:
            result = extract_memories(entry_text(note), known_people)
            candidates = [m.model_dump() for m in result.memories]
            personal_candidates = [m.model_dump() for m in result.personal]
            completion_candidates = [m.model_dump() for m in result.completed_personal]
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT status, revision FROM notes WHERE id = ?', (note_id,)).fetchone()
            if current is None or current['status'] != 'processing' or current['revision'] != note['revision']:
                return
            protected = [dict(row) for row in db.execute('SELECT * FROM memories WHERE note_id = ? AND active = 1 AND edited = 1', (note_id,))]
            for candidate in candidates:
                if any(m['evidence'] == candidate['evidence'] for m in protected):
                    continue
                person_id = get_or_create_person(db, candidate['person'])
                if any(m['person_id'] == person_id and m['category'] == candidate['category'] for m in protected):
                    continue
                existing = [dict(m) for m in db.execute('SELECT * FROM memories WHERE person_id = ? AND active = 1', (person_id,))]
                related = {m['id']: m for m in existing if m['category'] == candidate['category']}
                duplicate = candidate.get('duplicate_of')
                replacement = candidate.get('replaces_id')
                if duplicate and duplicate not in related or replacement and replacement not in related:
                    raise InferenceError('A connection could not be verified. Your note is saved; please retry.')
                if duplicate or any(m['category'] == candidate['category'] and fact_key(m['value']) == fact_key(candidate['value']) for m in existing):
                    # Keep provenance for each note, but only one active copy of a fact.
                    match = related[duplicate] if duplicate else next(m for m in existing if m['category'] == candidate['category'] and fact_key(m['value']) == fact_key(candidate['value']))
                    candidate = {**candidate, 'value': match['value']}
                    replacement = match['id']
                elif candidate['category'] == 'birthday' and len(related) == 1:
                    replacement = next(iter(related))
                if replacement:
                    db.execute('UPDATE memories SET active = 0 WHERE id = ?', (replacement,))
                db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,replaces_id,note_revision)
                           VALUES (?,?,?,?,?,?,?)''', (person_id, note_id, candidate['category'], candidate['value'], candidate['evidence'], replacement, note['revision']))
            publish_personal(db, note, personal_candidates)
            discover_repeats(db, note)
            publish_completions(db, note, completion_candidates)
            db.execute("UPDATE notes SET status = 'organized', candidates = ?, personal_candidates = ?, completion_candidates = ?, error = NULL WHERE id = ?",
                       (json.dumps(candidates), json.dumps(personal_candidates), json.dumps(completion_candidates), note_id))
    except SessionEnded:
        return
    except Exception as exc:
        message = str(exc) if isinstance(exc, (InferenceError, DemoError)) else 'Could not organize this note. It is saved; please retry.'
        # Never log note contents, model responses, or credentials.
        logging.getLogger(__name__).warning('Note %s organization failed (%s)', note_id, type(exc).__name__)
        with database() as db:
            db.execute("UPDATE notes SET status = 'failed', error = ? WHERE id = ? AND status = 'processing' AND revision = ?", (message, note_id, note.get('revision', -1)))


@app.post('/api/notes', status_code=201)
def add_note(body: NoteInput):
    with database() as db:
        workspace = current_workspace.get()
        if workspace and db.execute('SELECT COUNT(*) FROM notes').fetchone()[0] >= workspace.manager.max_entries:
            raise DemoError('This temporary workspace reached its entry limit. Export or reset the demo to continue.')
        note_id = db.execute('INSERT INTO notes(text, automatic, status, kind, title, entry_date) VALUES (?,?,?,?,?,?)',
                            (body.text, int(body.automatic), 'queued' if body.automatic else 'pending',
                             body.kind, body.title, body.entry_date.isoformat() if body.entry_date else None)).lastrowid
        note = note_or_404(db, note_id)
        archive_entry(db, note)
    if body.automatic:
        submit_organization(note_id)
        return note
    return run_extraction(note_id)


@app.post('/api/notes/{note_id}/organize', status_code=202)
def queue_organization(note_id: int):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        note = note_or_404(db, note_id)
        if note['status'] in {'organized', 'reviewed', 'queued', 'processing'}:
            return note
        db.execute("UPDATE notes SET status = 'queued', automatic = 1, error = NULL, candidates = NULL, personal_candidates = NULL, completion_candidates = NULL WHERE id = ?", (note_id,))
        note = note_or_404(db, note_id)
    submit_organization(note_id)
    return note


@app.post('/api/notes/{note_id}/extract')
def retry_extraction(note_id: int):
    return run_extraction(note_id)


@app.post('/api/notes/{note_id}/review')
def review(note_id: int, body: ReviewInput):
    with database() as db:
        # Reserve the write transaction before checking status to make double
        # submissions and concurrent corrections atomic.
        db.execute('BEGIN IMMEDIATE')
        note = note_or_404(db, note_id)
        if note['status'] != 'pending':
            raise HTTPException(409, 'This note has already been reviewed.')
        candidates = note['candidates']
        if candidates is None:
            raise HTTPException(409, 'Extract memories before reviewing this note.')
        indices = [m.candidate_index for m in body.memories]
        targets = [m.replaces_id for m in body.memories if m.replaces_id is not None]
        if len(set(indices)) != len(indices) or len(set(targets)) != len(targets):
            raise HTTPException(422, 'A proposed memory or replacement was selected twice.')
        for item in body.memories:
            if item.candidate_index >= len(candidates):
                raise HTTPException(422, 'Unknown proposed memory.')
            candidate = candidates[item.candidate_index]
            person_id = get_or_create_person(db, item.person)
            if item.replaces_id:
                old = db.execute('SELECT * FROM memories WHERE id = ?', (item.replaces_id,)).fetchone()
                if not old or old['person_id'] != person_id or not old['active']:
                    raise HTTPException(409, 'The memory to replace is no longer available for this person.')
                db.execute('UPDATE memories SET active = 0 WHERE id = ?', (item.replaces_id,))
            edited = any(getattr(item, field) != candidate[field] for field in ('person', 'category', 'value'))
            db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,edited,replaces_id,note_revision)
                       VALUES (?,?,?,?,?,?,?,?)''', (person_id, note_id, item.category, item.value,
                       candidate['evidence'], int(edited), item.replaces_id, note['revision']))
        discover_repeats(db, note)
        db.execute("UPDATE notes SET status = 'reviewed', error = NULL WHERE id = ?", (note_id,))
    return {'saved': len(body.memories)}


@app.patch('/api/memories/{memory_id}')
def edit_memory(memory_id: int, body: MemoryEdit):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        memory = db.execute('SELECT * FROM memories WHERE id = ?', (memory_id,)).fetchone()
        if not memory or not memory['active']:
            raise HTTPException(409, 'This memory has changed. Refresh and try again.')
        person_id = get_or_create_person(db, body.person)
        db.execute('UPDATE memories SET active = 0 WHERE id = ?', (memory_id,))
        new_id = db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,edited,replaces_id,note_revision)
                           VALUES (?,?,?,?,?,1,?,?)''', (person_id, memory['note_id'], body.category, body.value,
                           memory['evidence'], memory_id, memory['note_revision'])).lastrowid
        return {'id': new_id}


@app.delete('/api/notes/{note_id}', status_code=204)
def delete_note(note_id: int):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        note_or_404(db, note_id)
        removed = {row['id']: dict(row) for row in db.execute('SELECT * FROM memories WHERE note_id = ?', (note_id,))}
        # Splice removed history entries out of replacement chains. This lets
        # a surviving correction restore the nearest surviving predecessor.
        for memory in removed.values():
            previous = memory['replaces_id']
            visited = set()
            while previous in removed and previous not in visited:
                visited.add(previous)
                previous = removed[previous]['replaces_id']
            db.execute('UPDATE memories SET replaces_id = ? WHERE replaces_id = ? AND note_id != ?',
                       (previous, memory['id'], note_id))
            if memory['active']:
                eligible = current_predecessor(db, previous, note_id)
                if eligible:
                    db.execute('UPDATE memories SET active = 1 WHERE id = ?', (eligible,))
        db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        db.execute('DELETE FROM people WHERE id NOT IN (SELECT person_id FROM memories)')


@app.get('/api/export')
def export():
    result = state()
    with database() as db:
        result['entry_versions'] = [dict(row) for row in db.execute('SELECT * FROM note_versions ORDER BY note_id, revision')]
        result['personal_reminders'] = [dict(row) for row in db.execute('SELECT * FROM personal_reminders ORDER BY id')]
        result['personal_completions'] = [dict(row) for row in db.execute('SELECT * FROM personal_completions ORDER BY id')]
        result['suggestion_actions'] = [dict(row) for row in db.execute('SELECT * FROM suggestion_actions')]
        result['suggestion_timing'] = [dict(row) for row in db.execute('SELECT * FROM suggestion_timing')]
        result['reminder_repeat_choices'] = [dict(row) for row in db.execute('SELECT * FROM reminder_repeat_choices')]
        result['reminder_recurrence'] = [dict(row) for row in db.execute('SELECT * FROM reminder_recurrence')]
        result['reminder_occurrences'] = [dict(row) for row in db.execute('SELECT * FROM reminder_occurrences')]
    return JSONResponse(result, headers={'Content-Disposition': 'attachment; filename="weaver-export.json"'})


def check_timezone(timezone):
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, 'Unknown timezone.')


def _suggestions(db, timezone, include_all_plans):
    return build_suggestions(db, timezone=timezone, include_all_plans=True) if include_all_plans else build_suggestions(db, timezone=timezone)


@app.get('/api/for-you')
def for_you(timezone: str = 'America/New_York', include_all_plans: bool = False):
    check_timezone(timezone)
    with database() as db:
        return coalesce_suggestions(_suggestions(db, timezone, include_all_plans))


@app.get('/api/search')
def search(q: str = Query(default='', max_length=200),
           kind: Literal['all', 'entry', 'person', 'memory', 'task'] = 'all',
           limit: int = Query(default=20, ge=1, le=100), timezone: str = 'America/New_York'):
    check_timezone(timezone)
    with database() as db:
        return search_workspace(db, q, coalesce_suggestions(_suggestions(db, timezone, True)), kind, limit)


@app.post('/api/notifications/{device}/claim')
def claim_reminders(device: UUID, timezone: str = 'America/New_York'):
    check_timezone(timezone)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        return claim_notifications(db, str(device), coalesce_suggestions(_suggestions(db, timezone, True)))


@app.post('/api/notifications/{device}/{token}/ack')
def acknowledge_reminders(device: UUID, token: UUID):
    with database() as db:
        db.execute('UPDATE notification_receipts SET delivered = 1 WHERE device = ? AND token = ?',
                   (str(device), str(token)))
    return {'saved': True}


@app.patch('/api/for-you/{suggestion_id}')
def act_on_suggestion(suggestion_id: str, body: SuggestionAction, timezone: str = 'America/New_York', include_all_plans: bool = False):
    check_timezone(timezone)
    if body.stop_repeat and body.status != 'dismissed':
        raise HTTPException(422, 'Stopping and dismissing a repeat requires dismissed status.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        current = _suggestions(db, timezone, include_all_plans)
        items = related_suggestions(current, suggestion_id)
        if not items:
            raise HTTPException(409, 'This suggestion has changed. Refresh to see the latest.')
        for item in items:
            suggestion_id = item['id']
            if body.stop_repeat:
                if not item['repeat'] or item['past_occurrence'] or item['status'] != 'open':
                    raise HTTPException(422, 'Choose an active repeating reminder to dismiss.')
                base = item['base_id']
                db.execute('DELETE FROM reminder_recurrence WHERE suggestion_id = ?', (base,))
                db.execute('INSERT OR IGNORE INTO reminder_repeat_choices(suggestion_id) VALUES (?)', (base,))
                db.execute('''INSERT INTO suggestion_timing(suggestion_id,due_date,due_overridden,snoozed_until) VALUES (?,?,1,NULL)
                              ON CONFLICT(suggestion_id) DO UPDATE SET due_date=excluded.due_date,due_overridden=1,snoozed_until=NULL''',
                           (base, item['due_start']))
                db.execute("INSERT INTO suggestion_actions(suggestion_id,status) VALUES (?,'dismissed') ON CONFLICT(suggestion_id) DO UPDATE SET status='dismissed',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')", (base,))
                continue
            try:
                if act_on_occurrence(db, item, body.status, current['today']):
                    continue
            except (ValueError, OverflowError):
                raise HTTPException(422, 'The next occurrence is outside the supported calendar. Turn off repeat or choose an earlier date.')
            db.execute("INSERT INTO suggestion_actions(suggestion_id, status) VALUES (?,?) ON CONFLICT(suggestion_id) DO UPDATE SET status = excluded.status, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')", (suggestion_id, body.status))
            db.execute('UPDATE suggestion_timing SET snoozed_until = NULL WHERE suggestion_id = ?', (suggestion_id,))
    return {'status': body.status}


@app.patch('/api/for-you/{suggestion_id}/timing')
def set_reminder_timing(suggestion_id: str, body: ReminderTiming, timezone: str = 'America/New_York'):
    check_timezone(timezone)
    fields = body.model_fields_set
    if not fields or fields == {'reset_due_date'} and not body.reset_due_date:
        raise HTTPException(422, 'Choose a due date or snooze setting.')
    if body.reset_due_date and 'due_date' in fields:
        raise HTTPException(422, 'Choose a due date or restore the date from your writing, not both.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        feed = _suggestions(db, timezone, True)
        items = related_suggestions(feed, suggestion_id)
        if not items:
            raise HTTPException(409, 'This reminder has changed. Refresh to see the latest.')
        for item in items:
            if not item['can_schedule']:
                raise HTTPException(422, 'Only tasks, plans, reminders, goals and commitments can be scheduled.')
            if body.snoozed_until and body.snoozed_until.isoformat() <= feed['today']:
                raise HTTPException(422, 'Choose a snooze date after today.')
            suggestion_id = item['base_id']
            if item['repeat'] and ('due_date' in fields or body.reset_due_date):
                if not body.due_date or body.due_date.year > 9998:
                    raise HTTPException(422, 'Repeating reminders need a due date before year 9999.')
                db.execute("UPDATE reminder_recurrence SET next_due = ?, anchor_date = ?, origin = 'manual' WHERE suggestion_id = ?",
                           (body.due_date.isoformat(), body.due_date.isoformat(), suggestion_id))
            db.execute('INSERT OR IGNORE INTO suggestion_timing(suggestion_id) VALUES (?)', (suggestion_id,))
            if 'due_date' in fields or body.reset_due_date:
                db.execute('UPDATE suggestion_timing SET due_date = ?, due_overridden = ? WHERE suggestion_id = ?',
                           (body.due_date.isoformat() if body.due_date else None, int(not body.reset_due_date), suggestion_id))
            if 'snoozed_until' in fields:
                db.execute('UPDATE suggestion_timing SET snoozed_until = ? WHERE suggestion_id = ?',
                           (body.snoozed_until.isoformat() if body.snoozed_until else None, suggestion_id))
            db.execute("UPDATE suggestion_timing SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE suggestion_id = ?", (suggestion_id,))
    return {'saved': True}


@app.patch('/api/for-you/{suggestion_id}/repeat')
def set_reminder_repeat(suggestion_id: str, body: ReminderRepeat, timezone: str = 'America/New_York'):
    check_timezone(timezone)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        feed = _suggestions(db, timezone, True)
        items = related_suggestions(feed, suggestion_id)
        if not items:
            raise HTTPException(409, 'This reminder has changed. Refresh to see the latest.')
        for item in items:
            if not item['can_schedule'] or item['status'] != 'open':
                raise HTTPException(422, 'Choose an open task, plan, reminder, goal or commitment.')
            base_id = item['base_id']
            due = body.start_date.isoformat() if body.start_date else item['due_start']
            if body.frequency:
                if not due or int(due[:4]) > 9998:
                    raise HTTPException(422, 'Choose a first due date before year 9999.')
                existing = db.execute('SELECT * FROM reminder_recurrence WHERE suggestion_id = ?', (base_id,)).fetchone()
                anchor = existing['anchor_date'] if existing and existing['frequency'] == body.frequency and existing['next_due'] == due else due
                db.execute('''INSERT INTO reminder_recurrence(suggestion_id,frequency,anchor_date,next_due,occurrence_key)
                              VALUES (?,?,?,?,?) ON CONFLICT(suggestion_id) DO UPDATE SET
                              frequency=excluded.frequency,anchor_date=excluded.anchor_date,next_due=excluded.next_due,origin='manual' ''',
                           (base_id, body.frequency, anchor, due, uuid4().hex))
            else:
                db.execute('DELETE FROM reminder_recurrence WHERE suggestion_id = ?', (base_id,))
            db.execute('INSERT OR IGNORE INTO reminder_repeat_choices(suggestion_id) VALUES (?)', (base_id,))
            # Turning repeat off keeps the pending occurrence as a one-off task.
            db.execute('''INSERT INTO suggestion_timing(suggestion_id,due_date,due_overridden) VALUES (?,?,1)
                          ON CONFLICT(suggestion_id) DO UPDATE SET due_date=excluded.due_date,due_overridden=1''', (base_id, due))
            db.execute("INSERT INTO suggestion_actions(suggestion_id,status) VALUES (?,'open') ON CONFLICT(suggestion_id) DO UPDATE SET status='open'", (base_id,))
    return {'saved': True}


@app.exception_handler(IdentityError)
async def identity_error(request: Request, exc: IdentityError):
    return JSONResponse({'detail': str(exc)}, status_code=409)


@app.post('/api/people/{person_id}/aliases', status_code=201)
def register_alias(person_id: int, body: AliasInput):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        add_alias(db, person_id, body.name)
    return {'saved': True}


@app.delete('/api/people/{person_id}/aliases', status_code=204)
def remove_alias(person_id: int, body: AliasInput):
    with database() as db:
        db.execute('DELETE FROM person_aliases WHERE person_id = ? AND name_key = ?', (person_id, name_key(body.name)))


@app.post('/api/people/merge')
def merge_profiles(body: PersonPair):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        return merge_people(db, body.source_id, body.target_id)


@app.post('/api/people/merges/{merge_id}/undo')
def restore_profiles(merge_id: str):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        return undo_merge(db, merge_id)


@app.post('/api/people/distinct')
def distinguish_people(body: PersonPair):
    first, second = sorted((body.source_id, body.target_id))
    with database() as db:
        if first == second or db.execute('SELECT COUNT(*) FROM people WHERE id IN (?,?)', (first, second)).fetchone()[0] != 2:
            raise IdentityError('Choose two existing, different profiles.')
        db.execute('INSERT OR IGNORE INTO distinct_people VALUES (?,?)', (first, second))
    return {'saved': True}


@app.get('/api/notes/{note_id}')
def read_entry(note_id: int, revision: int | None = None):
    with database() as db:
        note = note_or_404(db, note_id)
        if revision is None or revision == note['revision']:
            return note
        version = historical_entry(db, note, revision)
        if version is None:
            raise HTTPException(404, 'Entry version not found.')
        return version


@app.get('/api/notes/{note_id}/versions')
def entry_versions(note_id: int):
    with database() as db:
        note = note_or_404(db, note_id)
        archive_entry(db, note)
        versions = [dict(row) for row in db.execute('''SELECT revision,title,kind,entry_date,saved_at
                   FROM note_versions WHERE note_id = ? ORDER BY revision DESC''', (note_id,))]
        return {'current_revision': note['revision'], 'versions': versions}


def save_entry_revision(db, note, content, expected_revision):
    if note['revision'] != expected_revision:
        raise HTTPException(409, 'This entry changed elsewhere. View the latest version before saving your edit.')
    fields = ('text', 'title', 'kind', 'entry_date')
    if all(note[field] == content[field] for field in fields):
        return note, False
    archive_entry(db, note)
    retire_generated(db, note['id'])
    db.execute('''UPDATE notes SET text=?,title=?,kind=?,entry_date=?,revision=revision+1,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),automatic=1,status='queued',
               candidates=NULL,personal_candidates=NULL,completion_candidates=NULL,error=NULL WHERE id=?''',
               (*(content[field] for field in fields), note['id']))
    updated = note_or_404(db, note['id'])
    archive_entry(db, updated)
    return updated, True


@app.patch('/api/notes/{note_id}')
def update_entry(note_id: int, body: EntryEdit):
    content = body.model_dump(exclude={'expected_revision'})
    content['entry_date'] = body.entry_date.isoformat() if body.entry_date else None
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        note, changed = save_entry_revision(db, note_or_404(db, note_id), content, body.expected_revision)
    if changed:
        submit_organization(note_id)
    return note


@app.post('/api/notes/{note_id}/restore')
def restore_entry(note_id: int, body: EntryRestore):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        current = note_or_404(db, note_id)
        content = historical_entry(db, current, body.revision)
        if content is None:
            raise HTTPException(404, 'Entry version not found.')
        note, changed = save_entry_revision(db, current, content, body.expected_revision)
    if changed:
        submit_organization(note_id)
    return note


# A production build is served by the same local process; development uses Vite.
if (ROOT / 'frontend' / 'dist').is_dir():
    app.mount('/', StaticFiles(directory=ROOT / 'frontend' / 'dist', html=True), name='frontend')
