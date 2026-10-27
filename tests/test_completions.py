import json
import threading

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.inference import InferenceError, parse_extraction


def extract(text, known=None):
    personal, completed = [], []
    if text.startswith(('Renew my passport', 'Pay electricity bill', 'Pay phone bill')):
        personal = [{'category': 'task', 'value': text.rstrip('.'), 'evidence': text.rstrip('.')}]
    if 'renewed' in text:
        completed = [{'value': 'Renew my passport', 'evidence': text.rstrip('.')}]
    if text.startswith('I paid'):
        completed = [{'value': text.replace('I paid', 'Pay').rstrip('.'), 'evidence': text.rstrip('.')}]
    return parse_extraction(json.dumps({'memories': [], 'personal': personal,
        'completed_personal': completed}), text)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'completions.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', extract)
    with TestClient(main.app) as client:
        yield client


def settle(client):
    main.app.state.worker.submit(lambda: None).result(timeout=4)
    return client.get('/api/state').json()


def add(client, text, **fields):
    r = client.post('/api/notes', json={'text': text, **fields})
    assert r.status_code == 201
    settle(client)
    return r.json()


def feed(client):
    return client.get('/api/for-you').json()['suggestions']


def test_clear_completion_moves_task_to_done_with_its_source(client):
    task = add(client, 'Renew my passport.')
    original, = feed(client)
    done = add(client, 'I renewed my passport.')
    item, = feed(client)
    assert item['id'] == original['id']
    assert item['status'] == 'done'
    assert item['sources'][0]['note_id'] == task['id']
    assert item['completion'] == {'note_id': done['id'], 'note_revision': 1,
                                  'evidence': 'I renewed my passport'}
    assert client.get('/api/state').json()['people'] == []
    assert len(client.get('/api/export').json()['personal_completions']) == 1


@pytest.mark.parametrize('text', [
    "I haven't renewed my passport.", 'I have not renewed my passport.',
    'I will have renewed my passport tomorrow.', 'I might have renewed my passport.',
    'If I renewed my passport, I could travel.', 'Maya renewed my passport.',
    'I heard Maya renewed my passport.',
])
def test_uncertainty_negation_future_and_other_actors_never_close_tasks(client, text):
    add(client, 'Renew my passport.')
    add(client, text)
    assert feed(client)[0]['status'] == 'open'
    assert 'completion' not in feed(client)[0]


def test_near_match_is_not_enough_and_specific_completion_only_closes_one(client):
    add(client, 'Pay electricity bill.')
    add(client, 'Pay phone bill.')
    add(client, 'I paid the bill.')
    assert all(item['status'] == 'open' for item in feed(client))
    add(client, 'I paid electricity bill.')
    assert {item['sources'][0]['value']: item['status'] for item in feed(client)} == {
        'Pay electricity bill': 'done', 'Pay phone bill': 'open'}


def test_recurring_tasks_are_not_closed_from_one_instance(client):
    add(client, 'Renew my passport every year.')
    add(client, 'I renewed my passport.')
    assert feed(client)[0]['status'] == 'open'


def test_duplicate_sources_can_complete_together_and_later_new_task_stays_open(client):
    add(client, 'Renew my passport.')
    add(client, 'Renew my passport.')
    add(client, 'I renewed my passport.')
    assert feed(client)[0]['status'] == 'done'
    add(client, 'Renew my passport.')
    assert feed(client)[0]['status'] == 'open'


def test_ambiguous_dated_tasks_are_not_both_closed(client):
    add(client, 'Renew my passport by Friday.')
    add(client, 'Renew my passport by Saturday.')
    add(client, 'I renewed my passport.')
    assert all(item['status'] == 'open' for item in feed(client))


def test_backdated_completion_cannot_close_later_task(client):
    add(client, 'Renew my passport.', kind='journal', entry_date='2026-10-15')
    add(client, 'I renewed my passport.', kind='journal', entry_date='2026-10-10')
    assert feed(client)[0]['status'] == 'open'


def test_completion_does_not_apply_to_a_task_written_later(client):
    add(client, 'I renewed my passport.')
    add(client, 'Renew my passport.')
    assert feed(client)[0]['status'] == 'open'


def test_edit_delete_and_restore_completion_source_reconcile_automatic_state(client):
    add(client, 'Renew my passport.')
    done = add(client, 'I renewed my passport.')
    assert feed(client)[0]['status'] == 'done'
    client.patch(f"/api/notes/{done['id']}", json={'text': 'A quiet day.', 'expected_revision': 1})
    settle(client)
    assert feed(client)[0]['status'] == 'open'
    client.post(f"/api/notes/{done['id']}/restore", json={'revision': 1, 'expected_revision': 2})
    settle(client)
    assert feed(client)[0]['status'] == 'done'
    assert feed(client)[0]['completion']['note_revision'] == 3
    client.delete(f"/api/notes/{done['id']}")
    assert feed(client)[0]['status'] == 'open'
    assert client.get('/api/export').json()['personal_completions'] == []


@pytest.mark.parametrize('manual', ['open', 'dismissed', 'done'])
def test_manual_status_wins_and_restore_persists_across_reload(client, manual):
    add(client, 'Renew my passport.')
    add(client, 'I renewed my passport.')
    item, = feed(client)
    client.patch(f"/api/for-you/{item['id']}", json={'status': manual})
    main.initialize()
    assert feed(client)[0]['status'] == manual
    assert 'completion' not in feed(client)[0]


def test_editing_task_to_different_obligation_does_not_keep_old_completion(client):
    task = add(client, 'Renew my passport.')
    add(client, 'I renewed my passport.')
    client.patch(f"/api/notes/{task['id']}", json={'text': 'Pay phone bill.', 'expected_revision': 1})
    settle(client)
    assert feed(client)[0]['status'] == 'open'
    assert feed(client)[0]['sources'][0]['value'] == 'Pay phone bill'


def test_invalid_completion_quote_prevents_any_publication(client, monkeypatch):
    add(client, 'Renew my passport.')
    def invalid(text, known=None):
        return parse_extraction('{"memories":[],"completed_personal":[{"value":"Renew my passport","evidence":"invented"}]}', text)
    monkeypatch.setattr(main, 'extract_memories', invalid)
    note = add(client, 'I renewed my passport.')
    assert next(n for n in client.get('/api/state').json()['notes'] if n['id'] == note['id'])['status'] == 'failed'
    assert feed(client)[0]['status'] == 'open'


def test_stale_inflight_completion_cannot_close_a_task(client, monkeypatch):
    add(client, 'Renew my passport.')
    entered, release = threading.Event(), threading.Event()
    def blocked(text, known=None):
        if 'renewed' in text:
            entered.set()
            assert release.wait(timeout=4)
        return extract(text, known)
    monkeypatch.setattr(main, 'extract_memories', blocked)
    response = client.post('/api/notes', json={'text': 'I renewed my passport.'}).json()
    try:
        assert entered.wait(timeout=3)
        client.patch(f"/api/notes/{response['id']}", json={'text': 'A quiet day.', 'expected_revision': 1})
    finally:
        release.set()
    settle(client)
    assert feed(client)[0]['status'] == 'open'


def test_recurring_goal_never_closes_from_a_single_completed_instance(client, monkeypatch):
    def goal(text, known=None):
        if text.startswith('Renew'):
            return parse_extraction(json.dumps({'memories': [], 'personal': [
                {'category': 'goal', 'value': 'Renew my passport', 'evidence': 'Renew my passport'}]}), text)
        return extract(text, known)
    monkeypatch.setattr(main, 'extract_memories', goal)
    add(client, 'Renew my passport.')
    add(client, 'I renewed my passport.')
    assert feed(client)[0]['status'] == 'open'


def test_short_quote_cannot_hide_uncertainty_in_the_same_sentence(client, monkeypatch):
    add(client, 'Renew my passport.')
    def partial(text, known=None):
        return parse_extraction(json.dumps({'memories': [], 'completed_personal': [
            {'value': 'Renew my passport', 'evidence': 'I renewed my passport'}]}), text)
    monkeypatch.setattr(main, 'extract_memories', partial)
    add(client, 'I renewed my passport, or at least I think I did.')
    assert feed(client)[0]['status'] == 'open'


def test_manual_done_survives_removal_of_completion_source(client):
    add(client, 'Renew my passport.')
    done = add(client, 'I renewed my passport.')
    item, = feed(client)
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'done'})
    client.delete(f"/api/notes/{done['id']}")
    assert feed(client)[0]['status'] == 'done'


def test_completion_cannot_recreate_a_reminder_from_the_same_sentence():
    text = 'I renewed my passport.'
    result = parse_extraction(json.dumps({'memories': [], 'personal': [
        {'category': 'task', 'value': 'Renew my passport', 'evidence': 'I renewed my passport'}],
        'completed_personal': [{'value': 'Renew my passport', 'evidence': 'I renewed my passport'}]}), text)
    assert result.personal == []
    assert len(result.completed_personal) == 1


def test_a_separate_new_intention_is_not_removed_by_a_completed_action():
    text = 'I renewed my passport. Renew my passport tomorrow.'
    result = parse_extraction(json.dumps({'memories': [], 'personal': [
        {'category': 'task', 'value': 'Renew my passport tomorrow', 'evidence': 'Renew my passport tomorrow'}],
        'completed_personal': [{'value': 'Renew my passport', 'evidence': 'I renewed my passport'}]}), text)
    assert len(result.personal) == 1
