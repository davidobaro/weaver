import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.for_you import build_suggestions
from backend.inference import parse_extraction
from datetime import date


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'journal.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', lambda text, known=None: parse_extraction('{"memories":[]}', text))
    with TestClient(main.app) as client:
        yield client


def wait(client):
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    return client.get('/api/state').json()


def test_personal_reflection_is_a_complete_saved_journal_without_profiles(client):
    text = 'Today I took a quiet walk.\n\nI felt clearer afterward and want to make more room for rest.'
    response = client.post('/api/notes', json={
        'kind': 'journal', 'title': 'Room to breathe', 'entry_date': '2026-10-12', 'text': text,
    })
    assert response.status_code == 201
    result = wait(client)
    entry = result['notes'][0]
    assert entry['text'] == text
    assert entry['title'] == 'Room to breathe'
    assert entry['kind'] == 'journal'
    assert entry['entry_date'] == '2026-10-12'
    assert entry['status'] == 'organized'
    assert entry['candidates'] == []
    assert result['people'] == []
    main.initialize()
    assert client.get('/api/state').json()['notes'][0]['text'] == text
    exported = client.get('/api/export').json()['notes'][0]
    assert exported['kind'] == 'journal'
    assert exported['entry_date'] == '2026-10-12'


@pytest.mark.parametrize('kind', ['note', 'journal'])
def test_entry_limit_accepts_boundary_and_rejects_overflow_without_saving(client, kind):
    text = 'A quiet day.\n\n' + 'x' * (5000 - len('A quiet day.\n\n'))
    response = client.post('/api/notes', json={'kind': kind, 'text': text})
    assert response.status_code == 201
    entry = wait(client)['notes'][0]
    assert entry['text'] == text
    assert entry['title'] == ''
    assert client.post('/api/notes', json={'kind': kind, 'text': text + 'x'}).status_code == 422
    assert client.post('/api/notes', json={'kind': kind, 'text': '  '}).status_code == 422
    rejected_edit = client.patch(f"/api/notes/{entry['id']}", json={
        'text': text + 'x', 'kind': kind, 'expected_revision': 1,
    })
    assert rejected_edit.status_code == 422
    state = client.get('/api/state').json()
    assert len(state['notes']) == 1
    assert state['notes'][0]['text'] == text
    assert state['notes'][0]['revision'] == 1


def test_journal_title_is_context_and_relative_dates_use_entry_day(client, monkeypatch):
    def extract(text, known=None):
        assert text.startswith('Coffee with Maya\n\n')
        return parse_extraction(json.dumps({'memories': [{
            'person': 'Maya', 'category': 'plan', 'value': 'Visit a museum tomorrow',
            'evidence': 'Visit a museum tomorrow',
        }]}), text)
    monkeypatch.setattr(main, 'extract_memories', extract)
    response = client.post('/api/notes', json={
        'kind': 'journal', 'title': 'Coffee with Maya', 'entry_date': '2026-10-10',
        'text': 'Visit a museum tomorrow. I am looking forward to a slower day.',
    })
    assert response.status_code == 201
    result = wait(client)
    assert result['notes'][0]['status'] == 'organized'
    assert result['people'][0]['name'] == 'Maya'
    assert result['people'][0]['about']['facts'][0]['noted_at'] == '2026-10-10'
    with main.database() as db:
        item, = build_suggestions(db, today=date(2026, 10, 10))['suggestions']
    assert item['due_start'] == '2026-10-11'


def test_quick_notes_remain_compatible_and_invalid_metadata_is_rejected(client):
    response = client.post('/api/notes', json={'text': 'An everyday thought.'})
    assert response.status_code == 201
    entry = wait(client)['notes'][0]
    assert entry['kind'] == 'note'
    assert entry['title'] == ''
    assert entry['entry_date'] is None
    assert client.post('/api/notes', json={'text': 'A thought.', 'kind': 'other'}).status_code == 422
    assert client.post('/api/notes', json={'text': 'A thought.', 'entry_date': '2026-02-30'}).status_code == 422


def test_existing_database_is_migrated_without_losing_old_notes(tmp_path, monkeypatch):
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', candidates TEXT, error TEXT, created_at TEXT NOT NULL DEFAULT '2026-10-14T16:00:00Z')")
        db.execute("INSERT INTO notes(text,status) VALUES ('An older note.','organized')")
    monkeypatch.setattr(main, 'DB_PATH', path)
    with TestClient(main.app) as client:
        entry = client.get('/api/state').json()['notes'][0]
        assert entry['text'] == 'An older note.'
        assert entry['kind'] == 'note'
        assert entry['title'] == ''
        assert entry['entry_date'] is None
