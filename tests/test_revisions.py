import json
import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.for_you import build_suggestions
from backend.inference import InferenceError, parse_extraction


def extraction(text, known=None):
    if 'Maya' not in text:
        return parse_extraction('{"memories":[]}', text)
    value = 'Enjoys ceramics' if 'ceramics' in text else 'Enjoys hiking'
    return parse_extraction(json.dumps({'memories': [
        {'person': 'Maya', 'category': 'interest', 'value': value, 'evidence': text},
    ]}), text)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'revisions.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', extraction)
    with TestClient(main.app) as client:
        yield client


def settled(client):
    # Edits can append another job while a prior one is running. A second
    # barrier also waits for work enqueued before the first completed.
    main.app.state.worker.submit(lambda: None).result(timeout=4)
    return client.get('/api/state').json()


def create(client, text='Maya enjoys hiking.', **fields):
    response = client.post('/api/notes', json={'text': text, **fields})
    assert response.status_code == 201
    settled(client)
    return response.json()['id']


def edit(client, note, text='Maya enjoys ceramics.', expected=1, **fields):
    return client.patch(f'/api/notes/{note}', json={'text': text, 'expected_revision': expected, **fields})


def active(state):
    return [m for p in state['people'] for m in p['memories'] if m['active']]


def test_edit_retains_versions_and_updates_active_facts_and_sources(client):
    note = create(client)
    response = edit(client, note, kind='journal', title='A different hobby', entry_date='2026-10-10')
    assert response.status_code == 200
    assert response.json()['revision'] == 2
    result = settled(client)
    assert result['notes'][0]['title'] == 'A different hobby'
    assert [(m['value'], m['note_revision']) for m in active(result)] == [('Enjoys ceramics', 2)]
    old = client.get(f'/api/notes/{note}?revision=1').json()
    assert old['text'] == 'Maya enjoys hiking.'
    assert old['is_history'] is True
    assert old['current_revision'] == 2
    assert old['title'] == ''
    versions = client.get(f'/api/notes/{note}/versions').json()['versions']
    assert [v['revision'] for v in versions] == [2, 1]
    assert len(client.get('/api/export').json()['entry_versions']) == 2


def test_manual_memory_edits_survive_and_keep_original_source_version(client):
    note = create(client)
    original = active(settled(client))[0]
    assert client.patch(f"/api/memories/{original['id']}", json={
        'person': 'Maya', 'category': 'interest', 'value': 'Enjoys trail running',
    }).status_code == 200
    assert edit(client, note).status_code == 200
    result = settled(client)
    memories = active(result)
    assert [(m['value'], m['edited'], m['note_revision']) for m in memories] == [('Enjoys trail running', 1, 1)]
    archived = client.get(f"/api/notes/{note}?revision={memories[0]['note_revision']}").json()
    assert memories[0]['evidence'] in archived['text']
    assert result['people'][0]['about']['facts'][0]['note_revision'] == 1


def test_removed_people_facts_do_not_remain_active(client):
    note = create(client)
    assert edit(client, note, 'A quiet afternoon alone.').status_code == 200
    result = settled(client)
    assert active(result) == []
    assert result['people'][0]['about']['facts'] == []
    assert result['notes'][0]['candidates'] == []


def test_failed_reextraction_keeps_new_text_without_stale_facts_and_can_retry(client, monkeypatch):
    note = create(client)
    def fail(text, known=None):
        raise InferenceError('Inference unavailable; entry is saved.')
    monkeypatch.setattr(main, 'extract_memories', fail)
    assert edit(client, note).status_code == 200
    result = settled(client)
    assert result['notes'][0]['text'] == 'Maya enjoys ceramics.'
    assert result['notes'][0]['status'] == 'failed'
    assert active(result) == []
    monkeypatch.setattr(main, 'extract_memories', extraction)
    client.post(f'/api/notes/{note}/organize')
    result = settled(client)
    assert result['notes'][0]['revision'] == 2
    assert [m['value'] for m in active(result)] == ['Enjoys ceramics']


def test_stale_tab_and_noop_do_not_overwrite_or_create_extra_versions(client):
    note = create(client)
    assert edit(client, note).status_code == 200
    settled(client)
    assert edit(client, note, 'Wrong old tab content', expected=1).status_code == 409
    assert edit(client, note, expected=2).json()['revision'] == 2
    assert len(client.get(f'/api/notes/{note}/versions').json()['versions']) == 2


def test_restore_creates_new_version_and_regenerates_correct_facts(client):
    note = create(client)
    edit(client, note)
    settled(client)
    response = client.post(f'/api/notes/{note}/restore', json={'revision': 1, 'expected_revision': 2})
    assert response.status_code == 200
    assert response.json()['revision'] == 3
    assert [m['value'] for m in active(settled(client))] == ['Enjoys hiking']
    assert client.get(f'/api/notes/{note}?revision=2').json()['text'] == 'Maya enjoys ceramics.'
    assert len(client.get(f'/api/notes/{note}/versions').json()['versions']) == 3
    main.initialize()
    assert client.get(f'/api/notes/{note}').json()['revision'] == 3


def test_old_inflight_response_cannot_reintroduce_stale_facts(client, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def slow(text, known=None):
        if 'hiking' in text:
            started.set()
            assert release.wait(4)
        return extraction(text)
    monkeypatch.setattr(main, 'extract_memories', slow)
    response = client.post('/api/notes', json={'text': 'Maya enjoys hiking.'})
    note = response.json()['id']
    try:
        assert started.wait(2)
        assert edit(client, note).status_code == 200
    finally:
        release.set()
    result = settled(client)
    assert result['notes'][0]['revision'] == 2
    assert result['notes'][0]['status'] == 'organized'
    assert [m['value'] for m in active(result)] == ['Enjoys ceramics']


def test_manually_corrected_dates_keep_original_journal_date(client, monkeypatch):
    def dated(text, known=None):
        return parse_extraction(json.dumps({'memories': [{
            'person': 'Maya', 'category': 'commitment', 'value': 'Send Maya the guide tomorrow', 'evidence': text,
        }]}), text)
    monkeypatch.setattr(main, 'extract_memories', dated)
    note = create(client, 'Send Maya the guide tomorrow.', kind='journal', entry_date='2026-10-10')
    memory = active(settled(client))[0]
    client.patch(f"/api/memories/{memory['id']}", json={
        'person': 'Maya', 'category': 'commitment', 'value': 'Send Maya the trail guide tomorrow',
    })
    edit(client, note, 'Send Maya the guide tomorrow. Added a reflection.', kind='journal', entry_date='2026-10-15')
    settled(client)
    with main.database() as db:
        suggestion, = build_suggestions(db, today=date(2026, 10, 10))['suggestions']
    assert suggestion['due_start'] == '2026-10-11'
    assert suggestion['sources'][0]['note_revision'] == 1


def test_delete_purges_all_entry_versions(client):
    note = create(client)
    edit(client, note)
    settled(client)
    assert client.delete(f'/api/notes/{note}').status_code == 204
    assert client.get(f'/api/notes/{note}?revision=1').status_code == 404
    assert client.get('/api/export').json()['entry_versions'] == []


def test_editing_replacement_restores_only_current_predecessors(client, monkeypatch):
    def birthday(text, known=None):
        return parse_extraction(json.dumps({'memories': [] if 'quiet' in text else [{
            'person': 'Maya', 'category': 'birthday', 'value': 'June 14' if '14' in text else 'June 12', 'evidence': text,
        }]}), text)
    monkeypatch.setattr(main, 'extract_memories', birthday)
    first = create(client, 'Maya birthday June 12')
    second = create(client, 'Maya birthday June 14')
    assert [m['value'] for m in active(settled(client))] == ['June 14']
    edit(client, first, 'A quiet day.')
    settled(client)
    client.delete(f'/api/notes/{second}')
    assert active(settled(client)) == []  # Never restore the retired version-1 birthday.
