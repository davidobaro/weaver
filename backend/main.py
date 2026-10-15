import json
import os
import re
import sqlite3
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .inference import InferenceError, extract_memories
from .models import NoteInput, ReviewInput, MemoryEdit

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DB_PATH = Path(os.getenv('WEAVER_DB_PATH') or ROOT / 'data' / 'weaver.sqlite3')


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def initialize():
    with database() as db:
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
        ''')
        if 'automatic' not in {row['name'] for row in db.execute('PRAGMA table_info(notes)')}:
            db.execute('ALTER TABLE notes ADD COLUMN automatic INTEGER NOT NULL DEFAULT 0')


@asynccontextmanager
async def lifespan(app):
    initialize()
    app.state.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='weaver-organizer')
    with database() as db:
        db.execute("UPDATE notes SET status = 'queued' WHERE automatic = 1 AND status = 'processing'")
        unfinished = [row['id'] for row in db.execute("SELECT id FROM notes WHERE automatic = 1 AND status = 'queued' ORDER BY id")]
    for note_id in unfinished:
        app.state.worker.submit(organize_note, note_id)
    try:
        yield
    finally:
        app.state.worker.shutdown(wait=True)


app = FastAPI(title='Weaver', lifespan=lifespan)


@app.middleware('http')
async def local_only(request: Request, call_next):
    # This first version has no accounts. Bind to loopback and reject browser
    # writes originating from other websites, including through the dev proxy.
    host = request.headers.get('host', '').split(':')[0]
    if host not in {'localhost', '127.0.0.1', 'testserver'}:
        return JSONResponse({'detail': 'Weaver is a local application.'}, status_code=403)
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        if origin and origin not in {'http://localhost:5173', 'http://127.0.0.1:5173',
                                     'http://localhost:8000', 'http://127.0.0.1:8000'}:
            return JSONResponse({'detail': 'This origin is not allowed.'}, status_code=403)
    return await call_next(request)


def note_or_404(db, note_id):
    row = db.execute('SELECT * FROM notes WHERE id = ?', (note_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Note not found.')
    result = dict(row)
    result['candidates'] = json.loads(result['candidates']) if result['candidates'] else None
    return result


@app.get('/api/state')
def state():
    with database() as db:
        notes = [note_or_404(db, row['id']) for row in db.execute('SELECT id FROM notes ORDER BY id DESC')]
        people = [dict(row) for row in db.execute('SELECT id, name FROM people ORDER BY name COLLATE NOCASE')]
        for person in people:
            person['memories'] = [dict(row) for row in db.execute(
                'SELECT * FROM memories WHERE person_id = ? ORDER BY id DESC', (person['id'],))]
    return {'notes': notes, 'people': people, 'inference_configured': bool(os.getenv('NEBIUS_API_KEY')),
            'model': os.getenv('NEBIUS_MODEL') or 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'}


def run_extraction(note_id):
    with database() as db:
        note = note_or_404(db, note_id)
        if note['status'] != 'pending':
            raise HTTPException(409, 'This note has already been reviewed.')
    try:
        result = extract_memories(note['text'])
    except InferenceError as exc:
        with database() as db:
            db.execute('UPDATE notes SET error = ? WHERE id = ? AND status = ?', (str(exc), note_id, 'pending'))
        raise HTTPException(502, detail={'message': str(exc), 'note_id': note_id}) from exc
    with database() as db:
        changed = db.execute("UPDATE notes SET candidates = ?, error = NULL WHERE id = ? AND status = 'pending'",
                             (json.dumps([item.model_dump() for item in result.memories]), note_id))
        if not changed.rowcount:
            raise HTTPException(409, 'This note has already been reviewed.')
        return note_or_404(db, note_id)


def name_key(value):
    return ' '.join(value.split()).casefold()


def fact_key(value):
    return re.sub(r'[^\w]+', ' ', value.casefold()).strip()


def relevant_people(db, text):
    people = []
    for row in db.execute('SELECT id, name FROM people'):
        words = row['name'].split()
        if not any(re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, re.IGNORECASE) for word in words):
            continue
        person = dict(row)
        person['memories'] = [dict(m) for m in db.execute(
            'SELECT id, category, value FROM memories WHERE person_id = ? AND active = 1', (row['id'],))]
        people.append(person)
    return people


def organize_note(note_id):
    try:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            claimed = db.execute("UPDATE notes SET status = 'processing', error = NULL WHERE id = ? AND status = 'queued'", (note_id,))
            if not claimed.rowcount:
                return
            note = note_or_404(db, note_id)
            known_people = relevant_people(db, note['text'])
        # Existing proposals can be organized without another inference call.
        candidates = note['candidates']
        if candidates is None:
            candidates = [m.model_dump() for m in extract_memories(note['text'], known_people).memories]
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT status FROM notes WHERE id = ?', (note_id,)).fetchone()
            if current is None or current['status'] != 'processing':
                return
            for candidate in candidates:
                person = db.execute('SELECT id FROM people WHERE name_key = ?', (name_key(candidate['person']),)).fetchone()
                person_id = person['id'] if person else db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',
                    (candidate['person'], name_key(candidate['person']))).lastrowid
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
                db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,replaces_id)
                           VALUES (?,?,?,?,?,?)''', (person_id, note_id, candidate['category'], candidate['value'], candidate['evidence'], replacement))
            db.execute("UPDATE notes SET status = 'organized', candidates = ?, error = NULL WHERE id = ?", (json.dumps(candidates), note_id))
    except Exception as exc:
        message = str(exc) if isinstance(exc, InferenceError) else 'Could not organize this note. It is saved; please retry.'
        # Never log note contents, model responses, or credentials.
        logging.getLogger(__name__).warning('Note %s organization failed (%s)', note_id, type(exc).__name__)
        with database() as db:
            db.execute("UPDATE notes SET status = 'failed', error = ? WHERE id = ? AND status = 'processing'", (message, note_id))


@app.post('/api/notes', status_code=201)
def add_note(body: NoteInput):
    with database() as db:
        note_id = db.execute('INSERT INTO notes(text, automatic, status) VALUES (?,?,?)',
                            (body.text, int(body.automatic), 'queued' if body.automatic else 'pending')).lastrowid
        note = note_or_404(db, note_id)
    if body.automatic:
        app.state.worker.submit(organize_note, note_id)
        return note
    return run_extraction(note_id)


@app.post('/api/notes/{note_id}/organize', status_code=202)
def queue_organization(note_id: int):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        note = note_or_404(db, note_id)
        if note['status'] in {'organized', 'reviewed', 'queued', 'processing'}:
            return note
        db.execute("UPDATE notes SET status = 'queued', automatic = 1, error = NULL, candidates = NULL WHERE id = ?", (note_id,))
        note = note_or_404(db, note_id)
    app.state.worker.submit(organize_note, note_id)
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
            key = ' '.join(item.person.split()).casefold()
            person = db.execute('SELECT id FROM people WHERE name_key = ?', (key,)).fetchone()
            if person:
                person_id = person['id']
            else:
                person_id = db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',
                                        (item.person, key)).lastrowid
            if item.replaces_id:
                old = db.execute('SELECT * FROM memories WHERE id = ?', (item.replaces_id,)).fetchone()
                if not old or old['person_id'] != person_id or not old['active']:
                    raise HTTPException(409, 'The memory to replace is no longer available for this person.')
                db.execute('UPDATE memories SET active = 0 WHERE id = ?', (item.replaces_id,))
            edited = any(getattr(item, field) != candidate[field] for field in ('person', 'category', 'value'))
            db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,edited,replaces_id)
                       VALUES (?,?,?,?,?,?,?)''', (person_id, note_id, item.category, item.value,
                       candidate['evidence'], int(edited), item.replaces_id))
        db.execute("UPDATE notes SET status = 'reviewed', error = NULL WHERE id = ?", (note_id,))
    return {'saved': len(body.memories)}


@app.patch('/api/memories/{memory_id}')
def edit_memory(memory_id: int, body: MemoryEdit):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        memory = db.execute('SELECT * FROM memories WHERE id = ?', (memory_id,)).fetchone()
        if not memory or not memory['active']:
            raise HTTPException(409, 'This memory has changed. Refresh and try again.')
        person = db.execute('SELECT id FROM people WHERE name_key = ?', (name_key(body.person),)).fetchone()
        person_id = person['id'] if person else db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',
            (body.person, name_key(body.person))).lastrowid
        db.execute('UPDATE memories SET active = 0 WHERE id = ?', (memory_id,))
        new_id = db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,edited,replaces_id)
                           VALUES (?,?,?,?,?,1,?)''', (person_id, memory['note_id'], body.category, body.value,
                           memory['evidence'], memory_id)).lastrowid
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
            while previous in removed:
                previous = removed[previous]['replaces_id']
            db.execute('UPDATE memories SET replaces_id = ? WHERE replaces_id = ? AND note_id != ?',
                       (previous, memory['id'], note_id))
            if memory['active'] and previous is not None:
                db.execute('UPDATE memories SET active = 1 WHERE id = ?', (previous,))
        db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        db.execute('DELETE FROM people WHERE id NOT IN (SELECT person_id FROM memories)')


@app.get('/api/export')
def export():
    return JSONResponse(state(), headers={'Content-Disposition': 'attachment; filename="weaver-export.json"'})


# A production build is served by the same local process; development uses Vite.
if (ROOT / 'frontend' / 'dist').is_dir():
    app.mount('/', StaticFiles(directory=ROOT / 'frontend' / 'dist', html=True), name='frontend')
