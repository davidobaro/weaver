import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.for_you import build_suggestions
from backend.inference import InferenceError, parse_extraction


def extract(text, known=None):
    personal = []
    for phrase, category in [
        ('Renew my passport', 'task'), ('Submit the application tomorrow', 'task'),
        ('Look into that running plan', 'reminder'), ('Run twice a week', 'goal'),
    ]:
        if phrase in text:
            personal.append({'category': category, 'value': phrase, 'evidence': phrase})
    memories = [{'person': 'Maya', 'category': 'commitment', 'value': 'Send Maya the link',
                 'evidence': 'Send Maya the link'}] if 'Send Maya the link' in text else []
    return parse_extraction(json.dumps({'memories': memories, 'personal': personal}), text)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'personal.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', extract)
    with TestClient(main.app) as client:
        yield client


def settle(client):
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    return client.get('/api/state').json()


def add(client, text='Renew my passport.', **fields):
    response = client.post('/api/notes', json={'text': text, **fields})
    assert response.status_code == 201
    settle(client)
    return response.json()


def feed(client):
    return client.get('/api/for-you').json()['suggestions']


def test_personal_and_others_are_distinct_and_have_source_links(client):
    note = add(client, 'Renew my passport. Send Maya the link. Look into that running plan. Run twice a week.')
    items = feed(client)
    personal = [i for i in items if i['scope'] == 'personal']
    others = [i for i in items if i['scope'] == 'others']
    assert len(personal) == 3
    assert len(others) == 1
    assert {i['category'] for i in personal} == {'task', 'reminder', 'goal'}
    assert all(i['sources'][0]['person_id'] is None and i['sources'][0]['note_id'] == note['id'] for i in personal)
    assert [p['name'] for p in client.get('/api/state').json()['people']] == ['Maya']
    assert all(i['due_start'] is None for i in personal)


def test_personal_relative_dates_use_entry_date_and_overdue_stays_visible(client):
    add(client, 'Submit the application tomorrow.', kind='journal', entry_date='2026-10-10')
    with main.database() as db:
        item, = build_suggestions(db, today=date(2026, 10, 15))['suggestions']
    assert item['due_start'] == '2026-10-11'
    assert item['overdue'] is True
    assert item['scope'] == 'personal'


def test_personal_done_dismiss_restore_and_duplicate_sources(client):
    first = add(client)
    item, = feed(client)
    assert client.patch(f"/api/for-you/{item['id']}", json={'status': 'done'}).status_code == 200
    second = add(client)
    merged, = feed(client)
    assert merged['id'] == item['id'] and merged['status'] == 'done'
    assert {s['note_id'] for s in merged['sources']} == {first['id'], second['id']}
    main.initialize()
    assert feed(client)[0]['status'] == 'done'
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'dismissed'})
    assert feed(client)[0]['status'] == 'dismissed'
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'open'})
    assert feed(client)[0]['status'] == 'open'


def test_edit_removes_stale_personal_tasks_and_restore_reextracts(client):
    note = add(client)
    old, = feed(client)
    response = client.patch(f"/api/notes/{note['id']}", json={'text': 'A quiet day.', 'expected_revision': 1})
    assert response.status_code == 200
    settle(client)
    assert feed(client) == []
    response = client.post(f"/api/notes/{note['id']}/restore", json={'revision': 1, 'expected_revision': 2})
    assert response.status_code == 200
    settle(client)
    restored, = feed(client)
    assert restored['id'] == old['id']
    assert restored['sources'][0]['note_revision'] == 3
    assert client.get(f"/api/notes/{note['id']}?revision=1").json()['text'] == note['text']


def test_failed_personal_edit_keeps_writing_without_stale_task(client, monkeypatch):
    note = add(client)
    def fail(*args):
        raise InferenceError('Temporary failure')
    monkeypatch.setattr(main, 'extract_memories', fail)
    client.patch(f"/api/notes/{note['id']}", json={'text': 'Look into that running plan.', 'expected_revision': 1})
    state = settle(client)
    assert state['notes'][0]['status'] == 'failed'
    assert state['notes'][0]['text'] == 'Look into that running plan.'
    assert feed(client) == []


def test_delete_cascades_and_export_includes_personal_history(client):
    note = add(client)
    assert len(client.get('/api/export').json()['personal_reminders']) == 1
    client.delete(f"/api/notes/{note['id']}")
    assert feed(client) == []
    assert client.get('/api/export').json()['personal_reminders'] == []


def test_named_task_cannot_be_saved_in_both_personal_and_person_memories():
    text = 'I need to send Maya the beginner ceramics class by Friday. I should book a dentist appointment.'
    result = parse_extraction(json.dumps({'memories': [
        {'person':'Maya','category':'commitment','value':'Send her that beginner ceramics class by Friday',
         'evidence':'I need to send Maya the beginner ceramics class by Friday.'}],
        'personal': [
            {'category':'task','value':'Send Maya the beginner ceramics class by Friday',
             'evidence':'I need to send Maya the beginner ceramics class by Friday.'},
            {'category':'task','value':'Book a dentist appointment','evidence':'I should book a dentist appointment.'}
        ]}), text)
    assert len(result.memories) == 1
    assert [item.value for item in result.personal] == ['Book a dentist appointment']


def test_known_named_recipient_routes_to_people_without_losing_the_task():
    from backend.inference import route_named_tasks
    text = 'Send Maya the guide. Renew my passport.'
    result = parse_extraction(json.dumps({'memories': [], 'personal': [
        {'category':'task','value':'Send Maya the guide','evidence':'Send Maya the guide.'},
        {'category':'task','value':'Renew my passport','evidence':'Renew my passport.'}]}), text)
    route_named_tasks(result, text, [{'name':'Maya'}])
    assert [(item.person,item.value) for item in result.memories] == [('Maya','Send Maya the guide')]
    assert [item.value for item in result.personal] == ['Renew my passport']


def test_personal_quotes_are_validated_without_requiring_a_person_name():
    result = parse_extraction('{"memories":[],"personal":[{"category":"task","value":"Get water","evidence":"get water"}]}', 'get water')
    assert len(result.personal) == 1
    with pytest.raises(InferenceError, match='source quotes'):
        parse_extraction('{"memories":[],"personal":[{"category":"task","value":"Get water","evidence":"invented"}]}', 'get water')


def test_profile_includes_undated_plans_and_actions_are_shared(client, monkeypatch):
    def plans(text, known=None):
        return parse_extraction(json.dumps({'memories': [
            {'person': 'Maya', 'category': 'plan', 'value': 'Wants to visit a garden',
             'evidence': 'Maya wants to visit a garden'},
        ]}), text)
    monkeypatch.setattr(main, 'extract_memories', plans)
    add(client, 'Maya wants to visit a garden.')
    assert feed(client) == []
    response = client.get('/api/for-you?include_all_plans=true')
    assert response.status_code == 200
    task, = response.json()['suggestions']
    assert task['scope'] == 'others'
    assert task['due_start'] is None
    assert task['kind'] == 'follow_up'
    assert client.patch(f"/api/for-you/{task['id']}?include_all_plans=true", json={'status': 'done'}).status_code == 200
    assert client.get('/api/for-you?include_all_plans=true').json()['suggestions'][0]['status'] == 'done'


def test_personal_and_people_are_both_atomic_on_bad_source(client, monkeypatch):
    def invalid(text, known=None):
        return parse_extraction(json.dumps({'memories': [
            {'person': 'Maya', 'category': 'commitment', 'value': 'Send Maya the link', 'evidence': 'Send Maya the link'},
        ], 'personal': [{'category': 'task', 'value': 'Renew my passport', 'evidence': 'invented quote'}]}), text)
    monkeypatch.setattr(main, 'extract_memories', invalid)
    add(client, 'Send Maya the link. Renew my passport.')
    state = client.get('/api/state').json()
    assert state['notes'][0]['status'] == 'failed'
    assert state['people'] == []
    assert feed(client) == []


def test_completed_life_update_is_not_a_profile_task(client, monkeypatch):
    def old_plan(text, known=None):
        return parse_extraction(json.dumps({'memories': [
            {'person': 'Maya', 'category': 'plan', 'value': 'started college', 'evidence': 'Maya started college'},
        ]}), text)
    monkeypatch.setattr(main, 'extract_memories', old_plan)
    add(client, 'Maya started college.')
    assert client.get('/api/for-you?include_all_plans=true').json()['suggestions'] == []
