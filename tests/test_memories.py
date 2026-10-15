import json
import time
import threading

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.inference import InferenceError, parse_extraction


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'memory.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', lambda note: parse_extraction(json.dumps({
        'memories': [{'person': 'Maya', 'category': 'birthday', 'value': 'June 12', 'evidence': note}]
    }), note))
    with TestClient(main.app) as client:
        yield client


def add(client, text='Maya’s birthday is June 12.'):
    response = client.post('/api/notes', json={'text': text, 'automatic': False})
    assert response.status_code == 201
    return response.json()['id']


def review(client, note, **patch):
    item = {'candidate_index': 0, 'person': 'Maya', 'category': 'birthday', 'value': 'June 12'}
    item.update(patch)
    return client.post(f'/api/notes/{note}/review', json={'memories': [item]})


def test_no_profile_before_approval_then_persist_with_original_source(client):
    note = add(client)
    assert client.get('/api/state').json()['people'] == []
    assert review(client, note, value='June 13 (corrected by me)').status_code == 200
    main.initialize()  # Reopening storage must not lose data.
    state = client.get('/api/state').json()
    memory = state['people'][0]['memories'][0]
    assert memory['value'] == 'June 13 (corrected by me)'
    assert memory['edited'] == 1
    assert memory['evidence'] == state['notes'][0]['text']
    assert memory['note_id'] == note
    assert review(client, note).status_code == 409
    assert len(client.get('/api/state').json()['people'][0]['memories']) == 1


def test_skip_and_unknown_candidate(client):
    note = add(client)
    assert review(client, note, candidate_index=9).status_code == 422
    assert client.get('/api/state').json()['people'] == []
    assert client.post(f'/api/notes/{note}/review', json={'memories': []}).status_code == 200
    assert client.get('/api/state').json()['people'] == []


def test_explicit_correction_preserves_history_and_delete_restores(client):
    first = add(client)
    review(client, first)
    memory_id = client.get('/api/state').json()['people'][0]['memories'][0]['id']
    second = add(client, 'Maya corrected her birthday to June 14.')
    assert review(client, second, value='June 14', replaces_id=memory_id).status_code == 200
    state = client.get('/api/state').json()
    memories = state['people'][0]['memories']
    assert [(m['value'], m['active']) for m in memories] == [('June 14', 1), ('June 12', 0)]
    assert client.delete(f'/api/notes/{second}').status_code == 204
    assert client.get('/api/state').json()['people'][0]['memories'][0]['active'] == 1
    assert client.delete(f'/api/notes/{first}').status_code == 204
    assert client.get('/api/state').json()['people'] == []


def test_wrong_person_correction_rolls_back(client):
    first = add(client)
    review(client, first)
    old = client.get('/api/state').json()['people'][0]['memories'][0]['id']
    second = add(client)
    assert review(client, second, person='Stephen', replaces_id=old).status_code == 409
    state = client.get('/api/state').json()
    assert [p['name'] for p in state['people']] == ['Maya']
    assert state['notes'][0]['status'] == 'pending'


def test_deleting_middle_correction_keeps_remaining_history_connected(client):
    first = add(client)
    review(client, first)
    original = client.get('/api/state').json()['people'][0]['memories'][0]['id']
    second = add(client)
    review(client, second, value='June 13', replaces_id=original)
    middle = client.get('/api/state').json()['people'][0]['memories'][0]['id']
    third = add(client)
    review(client, third, value='June 14', replaces_id=middle)
    client.delete(f'/api/notes/{second}')
    memories = client.get('/api/state').json()['people'][0]['memories']
    assert [(m['value'], m['active']) for m in memories] == [('June 14', 1), ('June 12', 0)]
    client.delete(f'/api/notes/{third}')
    memories = client.get('/api/state').json()['people'][0]['memories']
    assert [(m['value'], m['active']) for m in memories] == [('June 12', 1)]


def test_provider_failure_retains_note_for_retry(client, monkeypatch):
    def fail(note):
        raise InferenceError('Nebius is temporarily unavailable.')
    monkeypatch.setattr(main, 'extract_memories', fail)
    assert client.post('/api/notes', json={'text': 'Maya enjoys hiking.', 'automatic': False}).status_code == 502
    state = client.get('/api/state').json()
    assert state['notes'][0]['text'] == 'Maya enjoys hiking.'
    assert state['notes'][0]['candidates'] is None
    assert state['people'] == []


def test_missing_quote_and_malformed_response_are_rejected():
    with pytest.raises(InferenceError):
        parse_extraction('{"memories":[{"person":"Maya","category":"interest","value":"Hiking","evidence":"Maya hikes"}]}', 'Maya likes running.')
    with pytest.raises(InferenceError):
        parse_extraction('not JSON', 'Maya likes running.')


def test_external_origin_cannot_write(client):
    assert client.post('/api/notes', json={'text': 'Maya likes hiking.'}, headers={'origin': 'https://example.com'}).status_code == 403
    assert client.get('/api/state').json()['notes'] == []


def test_export_contains_source_and_reviewed_memory(client):
    note = add(client)
    review(client, note)
    response = client.get('/api/export')
    assert 'attachment' in response.headers['content-disposition']
    assert response.json()['notes'][0]['id'] == note
    assert response.json()['people'][0]['memories'][0]['note_id'] == note


def wait_for_note(client, note_id, status='organized'):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        state = client.get('/api/state').json()
        note = next(n for n in state['notes'] if n['id'] == note_id)
        if note['status'] == status:
            return state
        if note['status'] == 'failed' and status != 'failed':
            pytest.fail(note['error'])
        time.sleep(.02)
    pytest.fail('Background organization did not finish')


def automatic_note(client, text):
    response = client.post('/api/notes', json={'text': text})
    assert response.status_code == 201
    return response.json()['id']


def test_automatic_save_returns_before_model_and_groups_without_review(client, monkeypatch):
    release = threading.Event()
    started = threading.Event()
    def extract(note, known):
        started.set()
        assert release.wait(3)
        return parse_extraction(json.dumps({'memories': [
            {'person': 'Joshua', 'category': 'plan', 'value': 'Wants to go to the mall', 'evidence': note},
        ]}), note)
    monkeypatch.setattr(main, 'extract_memories', extract)
    try:
        note_id = automatic_note(client, 'Joshua wants to go to the mall.')
        assert started.wait(2)
        assert client.get('/api/state').json()['people'] == []
    finally:
        release.set()
    state = wait_for_note(client, note_id)
    assert state['people'][0]['name'] == 'Joshua'
    assert state['people'][0]['memories'][0]['category'] == 'plan'
    assert client.post(f'/api/notes/{note_id}/organize').status_code == 202
    assert len(client.get('/api/state').json()['people'][0]['memories']) == 1


def test_auto_connects_deduplicates_and_updates_birthday(client, monkeypatch):
    contexts = []
    def extract(note, known):
        contexts.append(known)
        value = 'June 14' if '14' in note else 'June 12'
        return parse_extraction(json.dumps({'memories': [
            {'person': 'Maya', 'category': 'birthday', 'value': value, 'evidence': note},
        ]}), note)
    monkeypatch.setattr(main, 'extract_memories', extract)
    first = automatic_note(client, 'Maya’s birthday is June 12.')
    wait_for_note(client, first)
    second = automatic_note(client, 'Maya’s birthday is June 12.')
    state = wait_for_note(client, second)
    assert len(state['people']) == 1
    assert sum(m['active'] for m in state['people'][0]['memories']) == 1
    third = automatic_note(client, 'Maya’s birthday is actually June 14.')
    state = wait_for_note(client, third)
    assert [m['value'] for m in state['people'][0]['memories'] if m['active']] == ['June 14']
    assert contexts[1][0]['name'] == 'Maya'
    assert contexts[1][0]['memories'][0]['value'] == 'June 12'


def test_background_failure_is_retryable_and_does_not_lose_note(client, monkeypatch):
    def fail(note, known):
        raise InferenceError('Nebius is temporarily unavailable.')
    monkeypatch.setattr(main, 'extract_memories', fail)
    note_id = automatic_note(client, 'Maya enjoys running.')
    state = wait_for_note(client, note_id, 'failed')
    assert state['notes'][0]['text'] == 'Maya enjoys running.'
    assert not state['people']
    monkeypatch.setattr(main, 'extract_memories', lambda note, known: parse_extraction('{"memories":[]}', note))
    assert client.post(f'/api/notes/{note_id}/organize').status_code == 202
    wait_for_note(client, note_id)


def test_edit_after_auto_save_keeps_source_and_history(client, monkeypatch):
    monkeypatch.setattr(main, 'extract_memories', lambda note, known: parse_extraction(json.dumps({'memories': [
        {'person': 'Joshua', 'category': 'interest', 'value': 'Go to the mall', 'evidence': note},
    ]}), note))
    note_id = automatic_note(client, 'Joshua wants to go to the mall.')
    state = wait_for_note(client, note_id)
    memory = state['people'][0]['memories'][0]
    assert client.patch(f"/api/memories/{memory['id']}", json={
        'person': 'Joshua', 'category': 'plan', 'value': 'Wants to go to the mall',
    }).status_code == 200
    memories = client.get('/api/state').json()['people'][0]['memories']
    assert memories[0]['category'] == 'plan'
    assert memories[0]['evidence'] == 'Joshua wants to go to the mall.'
    assert memories[0]['edited'] == 1
    assert memories[1]['active'] == 0


def test_queue_recovers_after_restart(client, monkeypatch):
    monkeypatch.setattr(main, 'extract_memories', lambda note, known: parse_extraction('{"memories":[]}', note))
    with main.database() as db:
        note_id = db.execute("INSERT INTO notes(text, status, automatic) VALUES ('A quiet day.', 'processing', 1)").lastrowid
    # Simulate an interrupted prior process using a fresh app lifespan.
    with TestClient(main.app) as restarted:
        assert wait_for_note(restarted, note_id)['notes'][0]['status'] == 'organized'


def test_invalid_cross_person_connection_rolls_back_all_auto_memories(client, monkeypatch):
    first = add(client)
    review(client, first)
    existing = client.get('/api/state').json()['people'][0]['memories'][0]['id']
    monkeypatch.setattr(main, 'extract_memories', lambda note, known: parse_extraction(json.dumps({'memories': [
        {'person': 'Stephen', 'category': 'birthday', 'value': 'June 14', 'evidence': note, 'replaces_id': existing},
    ]}), note))
    note_id = automatic_note(client, 'Stephen’s birthday is June 14.')
    state = wait_for_note(client, note_id, 'failed')
    assert [p['name'] for p in state['people']] == ['Maya']
    assert state['people'][0]['memories'][0]['active'] == 1


def test_deleted_processing_note_is_not_recreated(client, monkeypatch):
    release = threading.Event()
    started = threading.Event()
    def extract(note, known):
        started.set()
        assert release.wait(3)
        return parse_extraction('{"memories":[]}', note)
    monkeypatch.setattr(main, 'extract_memories', extract)
    try:
        note_id = automatic_note(client, 'A quiet day.')
        assert started.wait(2)
        assert client.delete(f'/api/notes/{note_id}').status_code == 204
    finally:
        release.set()
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    assert client.get('/api/state').json()['notes'] == []
