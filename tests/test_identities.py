import json

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.identities import similar_names
from backend.inference import InferenceError, parse_extraction


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'people.sqlite3')
    with TestClient(main.app) as client:
        yield client


def person(name, category='context', value='Played soccer', active=1):
    with main.database() as db:
        person_id = db.execute('INSERT INTO people(name,name_key) VALUES (?,?)', (name, name.casefold())).lastrowid
        note_id = db.execute("INSERT INTO notes(text,status) VALUES (?,'organized')", (value,)).lastrowid
        memory_id = db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,active)
                               VALUES (?,?,?,?,?,?)''', (person_id, note_id, category, value, value, active)).lastrowid
    return person_id, note_id, memory_id


def state(client):
    return client.get('/api/state').json()


def merge(client, source, target):
    return client.post('/api/people/merge', json={'source_id': source, 'target_id': target})


def test_nickname_suggestion_requires_confirmation_and_distinct_answer_persists(client):
    josh, _, _ = person('Josh')
    joshua, _, _ = person('Joshua')
    before = state(client)
    assert len(before['people']) == 2
    assert before['identity_matches'] == [{'source_id': josh, 'source_name': 'Josh', 'target_id': joshua, 'target_name': 'Joshua'}]
    assert client.post('/api/people/distinct', json={'source_id': josh, 'target_id': joshua}).status_code == 200
    main.initialize()
    assert state(client)['identity_matches'] == []
    assert len(state(client)['people']) == 2


def test_merge_preserves_all_sources_history_and_aliases(client):
    josh, source_note, source_memory = person('Josh', value='Josh played soccer')
    joshua, target_note, target_memory = person('Joshua', value='Joshua enjoys hiking', active=0)
    client.post(f'/api/people/{josh}/aliases', json={'name': 'Joshy'})
    response = merge(client, josh, joshua)
    assert response.status_code == 200
    after = state(client)
    assert len(after['people']) == 1
    profile = after['people'][0]
    assert profile['name'] == 'Joshua'
    assert {a['name'] for a in profile['aliases']} == {'Josh', 'Joshy'}
    assert {m['id'] for m in profile['memories']} == {source_memory, target_memory}
    assert {m['note_id'] for m in profile['memories']} == {source_note, target_note}
    assert next(m for m in profile['memories'] if m['id'] == target_memory)['active'] == 0
    assert after['people_merges'][0]['can_undo'] is True
    assert len(after['notes']) == 2


def test_alias_routes_new_notes_automatically_and_is_supplied_as_context(client, monkeypatch):
    joshua, _, _ = person('Joshua')
    assert client.post(f'/api/people/{joshua}/aliases', json={'name': 'Josh'}).status_code == 201
    contexts = []
    def extract(note, known):
        contexts.extend(known)
        return parse_extraction(json.dumps({'memories': [{'person': 'Josh', 'category': 'interest', 'value': 'Enjoys ceramics', 'evidence': note}]}), note)
    monkeypatch.setattr(main, 'extract_memories', extract)
    response = client.post('/api/notes', json={'text': 'Josh enjoys ceramics.'})
    assert response.status_code == 201
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    after = state(client)
    assert after['notes'][0]['status'] == 'organized'
    assert len(after['people']) == 1
    assert len(after['people'][0]['memories']) == 2
    assert contexts[0]['name'] == 'Joshua'
    assert contexts[0]['aliases'] == ['Josh']


def test_alias_collision_cannot_silently_combine_people(client):
    josh, _, _ = person('Josh')
    joshua, _, _ = person('Joshua')
    assert client.post(f'/api/people/{joshua}/aliases', json={'name': 'Josh'}).status_code == 409
    assert len(state(client)['people']) == 2
    client.post(f'/api/people/{josh}/aliases', json={'name': 'Coach / J'})
    assert client.post(f'/api/people/{joshua}/aliases', json={'name': 'Coach / J'}).status_code == 409
    assert client.request('DELETE', f'/api/people/{josh}/aliases', json={'name': 'Coach / J'}).status_code == 204
    assert client.post(f'/api/people/{joshua}/aliases', json={'name': 'Coach / J'}).status_code == 201


def test_undo_restores_original_profiles_and_aliases(client):
    josh, _, moved = person('Josh')
    joshua, _, _ = person('Joshua')
    client.post(f'/api/people/{joshua}/aliases', json={'name': 'J'})
    event = merge(client, josh, joshua).json()['id']
    assert client.post(f'/api/people/merges/{event}/undo').status_code == 200
    after = state(client)
    assert len(after['people']) == 2
    restored = next(p for p in after['people'] if p['name'] == 'Josh')
    assert [m['id'] for m in restored['memories']] == [moved]
    remaining = next(p for p in after['people'] if p['name'] == 'Joshua')
    assert [a['name'] for a in remaining['aliases']] == ['J']
    assert after['people_merges'] == []


def test_undo_is_blocked_after_profile_changes_without_losing_data(client):
    josh, _, _ = person('Josh')
    joshua, _, _ = person('Joshua')
    event = merge(client, josh, joshua).json()['id']
    client.post(f'/api/people/{joshua}/aliases', json={'name': 'Captain J'})
    assert state(client)['people_merges'][0]['can_undo'] is False
    assert client.post(f'/api/people/merges/{event}/undo').status_code == 409
    assert len(state(client)['people'][0]['memories']) == 2


def test_ambiguous_names_are_not_rewritten_by_model():
    content = json.dumps({'memories': [{'person': 'Joshua', 'category': 'context', 'value': 'Played soccer', 'evidence': 'Josh played soccer'}]})
    with pytest.raises(InferenceError):
        parse_extraction(content, 'Josh played soccer')
    assert similar_names('Josh', 'Joshua Smith')
    assert not similar_names('Josh Jones', 'Joshua Smith')


def test_merge_keeps_conflicting_birthdays_visible_without_scheduling_either(client):
    josh, _, _ = person('Josh', 'birthday', 'October 16')
    joshua, _, _ = person('Joshua', 'birthday', 'October 18')
    assert merge(client, josh, joshua).status_code == 200
    facts = state(client)['people'][0]['about']['facts']
    assert len(facts) == 2
    assert all('conflicting' in fact['label'] for fact in facts)
    assert client.get('/api/for-you').json()['suggestions'] == []


def test_merging_keeps_done_commitment_hidden(client):
    josh, _, _ = person('Josh', 'commitment', 'I promised a trail guide')
    joshua, _, _ = person('Joshua')
    before, = client.get('/api/for-you').json()['suggestions']
    client.patch(f"/api/for-you/{before['id']}", json={'status': 'done'})
    assert merge(client, josh, joshua).status_code == 200
    after, = client.get('/api/for-you').json()['suggestions']
    assert after['status'] == 'done'


def test_unknown_or_same_profile_merge_fails_without_changes(client):
    josh, _, _ = person('Josh')
    assert merge(client, josh, josh).status_code == 409
    assert merge(client, josh, 999).status_code == 409
    assert len(state(client)['people']) == 1
