from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.for_you import build_suggestions
from backend.recurrence import next_due


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'repeat.sqlite3')
    monkeypatch.setattr(main, 'build_suggestions', lambda db, timezone='America/New_York', include_all_plans=False:
        build_suggestions(db, today=date(2026, 10, 27), timezone=timezone, include_all_plans=include_all_plans))
    with TestClient(main.app) as client:
        yield client


def seed(text='Water the plants', person=None, category='task'):
    with main.database() as db:
        note = db.execute("INSERT INTO notes(text,status,entry_date) VALUES (?,'organized','2026-10-27')", (text,)).lastrowid
        main.archive_entry(db, main.note_or_404(db, note))
        if person:
            pid = db.execute('INSERT INTO people(name,name_key) VALUES (?,?)', (person, person.casefold())).lastrowid
            db.execute('INSERT INTO memories(person_id,note_id,category,value,evidence) VALUES (?,?,?,?,?)', (pid, note, category, text, text))
        else:
            db.execute('INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,?,?,?)', (note, category, text, text))
    return note


def feed(client):
    response = client.get('/api/for-you?include_all_plans=true')
    assert response.status_code == 200
    return response.json()['suggestions']


def current(client):
    return next(item for item in feed(client) if not item['past_occurrence'])


def repeat(client, item, frequency='daily', start_date='2026-10-27'):
    return client.patch(f"/api/for-you/{item['id']}/repeat", json={'frequency': frequency, 'start_date': start_date})


def act(client, item, status='done'):
    return client.patch(f"/api/for-you/{item['id']}?include_all_plans=true", json={'status': status})


@pytest.mark.parametrize('frequency,start,today,expected', [
    ('daily', '2026-10-27', '2026-10-27', '2026-10-28'),
    ('daily', '2026-10-20', '2026-10-27', '2026-10-28'),
    ('weekly', '2026-10-20', '2026-10-27', '2026-11-03'),
    ('weekly', '2026-10-20', '2026-10-28', '2026-11-03'),
    ('weekly', '2026-11-03', '2026-10-27', '2026-11-10'),
    ('monthly', '2026-01-31', '2026-01-31', '2026-02-28'),
    ('monthly', '2028-01-31', '2028-01-31', '2028-02-29'),
    ('monthly', '2026-01-31', '2026-02-28', '2026-03-31'),
    ('monthly', '2026-01-31', '2026-05-04', '2026-05-31'),
    ('monthly', '2026-12-31', '2026-12-31', '2027-01-31'),
])
def test_calendar_advancement_skips_missed_periods_and_preserves_anchor(frequency, start, today, expected):
    assert next_due(start, start, frequency, today) == expected


def test_monthly_february_completion_returns_to_original_day():
    assert next_due('2026-02-28', '2026-01-31', 'monthly', '2026-02-28') == '2026-03-31'


@pytest.mark.parametrize('status', ['done', 'dismissed'])
def test_handling_occurrence_advances_once_with_separate_persistent_history(client, status):
    seed()
    original = current(client)
    assert repeat(client, original).status_code == 200
    first = current(client)
    assert first['repeat'] == 'daily' and first['sources'] == original['sources']
    assert first['id'] != original['id']
    assert act(client, first, status).status_code == 200
    second = current(client)
    assert second['status'] == 'open' and second['due_start'] == '2026-10-28'
    assert second['id'] != first['id']
    past, = [item for item in feed(client) if item['past_occurrence']]
    assert past['id'] == first['id'] and past['status'] == status
    assert act(client, first, status).status_code == 200  # stale second tab / double-click
    assert current(client)['id'] == second['id']
    main.initialize()
    assert current(client)['id'] == second['id']
    assert len(client.get('/api/export').json()['reminder_occurrences']) == 1


def test_restore_past_occurrence_does_not_erase_or_advance_current_schedule(client):
    seed()
    repeat(client, current(client))
    first = current(client)
    act(client, first)
    second = current(client)
    assert act(client, first, 'open').status_code == 200
    restored, = [item for item in feed(client) if item['past_occurrence']]
    assert restored['status'] == 'open' and not restored['can_schedule']
    act(client, restored)
    assert current(client)['id'] == second['id']
    assert len(feed(client)) == 2


def test_snooze_preserves_repeat_and_completion_clears_snooze(client):
    seed()
    repeat(client, current(client), 'weekly')
    first = current(client)
    path = f"/api/for-you/{first['id']}/timing"
    assert client.patch(path, json={'snoozed_until': '2026-11-20'}).status_code == 200
    assert current(client)['snoozed'] and current(client)['due_start'] == '2026-10-27'
    act(client, first)
    second = current(client)
    assert second['due_start'] == '2026-11-03' and not second['snoozed']
    assert second['snoozed_until'] is None


def test_change_date_resets_monthly_anchor_without_changing_current_id(client):
    seed()
    repeat(client, current(client), 'monthly', '2026-10-31')
    first = current(client)
    assert client.patch(f"/api/for-you/{first['id']}/timing", json={'due_date': '2026-10-30'}).status_code == 200
    assert current(client)['id'] == first['id']
    act(client, current(client))
    assert current(client)['due_start'] == '2026-11-30'
    act(client, current(client))
    assert current(client)['due_start'] == '2026-12-30'


def test_stop_repeat_keeps_pending_date_and_history_then_completes_as_one_off(client):
    seed()
    repeat(client, current(client))
    act(client, current(client))
    assert repeat(client, current(client), None, None).status_code == 200
    pending = current(client)
    assert pending['repeat'] is None and pending['due_start'] == '2026-10-28'
    act(client, pending)
    assert current(client)['status'] == 'done'
    assert len(feed(client)) == 2
    assert client.get('/api/export').json()['reminder_recurrence'] == []


def test_recurring_items_do_not_auto_complete_from_one_off_completion_records(client):
    seed()
    repeat(client, current(client))
    first = current(client)
    with main.database() as db:
        source = first['sources'][0]
        db.execute('INSERT INTO personal_completions(reminder_id,note_id,note_revision,evidence) VALUES (?,?,1,?)',
                   (source['id'], source['note_id'], 'Watered the plants'))
    assert current(client)['status'] == 'open'
    assert 'completion' not in current(client)


def test_deleting_source_removes_current_and_historical_occurrences(client):
    note = seed()
    repeat(client, current(client))
    act(client, current(client))
    client.delete(f'/api/notes/{note}')
    assert feed(client) == []


def test_notifications_are_independent_for_each_occurrence(client, monkeypatch):
    seed()
    repeat(client, current(client))
    device = str(uuid4())
    first = client.post(f'/api/notifications/{device}/claim').json()
    assert first['count'] == 1
    client.post(f"/api/notifications/{device}/{first['token']}/ack")
    act(client, current(client))
    assert client.post(f'/api/notifications/{device}/claim').json()['count'] == 0
    monkeypatch.setattr(main, 'build_suggestions', lambda db, timezone='America/New_York', include_all_plans=False:
        build_suggestions(db, today=date(2026, 10, 28), timezone=timezone, include_all_plans=include_all_plans))
    assert client.post(f'/api/notifications/{device}/claim').json()['count'] == 1


def test_validation_rejects_invalid_settings_completed_items_and_birthdays(client):
    seed()
    first = current(client)
    path = f"/api/for-you/{first['id']}/repeat"
    for body in [{}, {'frequency': 'hourly'}, {'frequency': 'daily'},
                 {'frequency': 'monthly', 'start_date': '9999-01-01'}, {'frequency': 'daily', 'start_date': 'invalid'}]:
        assert client.patch(path, json=body).status_code == 422
    assert client.patch(path+'?timezone=Nope', json={'frequency': None}).status_code == 422
    act(client, first)
    assert repeat(client, first).status_code == 422
    seed('Birthday October 29', 'Mira', 'birthday')
    birthday = next(item for item in feed(client) if item['sources'][0]['category'] == 'birthday')
    assert repeat(client, birthday).status_code == 422
    assert client.patch('/api/for-you/missing/repeat', json={'frequency': None}).status_code == 409


def test_recurring_date_cannot_be_cleared_or_restored_implicitly(client):
    seed()
    repeat(client, current(client))
    first = current(client)
    for patch in [{'due_date': None}, {'reset_due_date': True}]:
        assert client.patch(f"/api/for-you/{first['id']}/timing", json=patch).status_code == 422
    assert current(client)['due_start'] == '2026-10-27'


def test_profile_merge_and_undo_preserve_repeat_and_history(client):
    seed('Visit a museum', 'Mira', 'plan')
    seed('Enjoys jazz', 'Mira Ellis', 'interest')
    assert repeat(client, current(client), 'weekly').status_code == 200
    act(client, current(client))
    people = {p['name']: p['id'] for p in client.get('/api/state').json()['people']}
    merged = client.post('/api/people/merge', json={'source_id': people['Mira'], 'target_id': people['Mira Ellis']})
    assert merged.status_code == 200
    assert current(client)['repeat'] == 'weekly' and current(client)['due_start'] == '2026-11-03'
    assert len(feed(client)) == 2
    assert client.post(f"/api/people/merges/{merged.json()['id']}/undo").status_code == 200
    assert current(client)['repeat'] == 'weekly' and current(client)['due_start'] == '2026-11-03'
    assert len(feed(client)) == 2


@pytest.mark.parametrize('stop', [False, True])
def test_undo_merge_keeps_occurrences_handled_or_repeat_stopped_while_merged(client, stop):
    seed('Visit a museum', 'Mira', 'plan')
    seed('Enjoys jazz', 'Mira Ellis', 'interest')
    repeat(client, current(client), 'weekly')
    people = {p['name']: p['id'] for p in client.get('/api/state').json()['people']}
    merged = client.post('/api/people/merge', json={'source_id': people['Mira'], 'target_id': people['Mira Ellis']}).json()
    act(client, current(client))
    if stop:
        repeat(client, current(client), None, None)
    assert client.post(f"/api/people/merges/{merged['id']}/undo").status_code == 200
    assert current(client)['due_start'] == '2026-11-03'
    assert current(client)['repeat'] == (None if stop else 'weekly')
    assert len(feed(client)) == 2


def test_resaving_monthly_settings_preserves_original_month_end_anchor(client):
    seed()
    repeat(client, current(client), 'monthly', '2026-01-31')
    # Deliberately set the persisted pointer to February, simulating a prior completion.
    with main.database() as db:
        db.execute("UPDATE reminder_recurrence SET next_due='2026-02-28'")
    assert repeat(client, current(client), 'monthly', '2026-02-28').status_code == 200
    with main.database() as db:
        rule = db.execute('SELECT * FROM reminder_recurrence').fetchone()
        assert rule['anchor_date'] == '2026-01-31'
        assert next_due(rule['next_due'], rule['anchor_date'], rule['frequency'], '2026-02-28') == '2026-03-31'


def test_dismiss_repeat_stops_group_and_stays_off_after_restore_and_rediscovery(client):
    from backend.auto_recurrence import discover_repeats
    ids = [seed('I need to water the plants every Saturday', category=category) for category in ['task','reminder']]
    assert len(current(client)['related_ids']) == 2
    assert repeat(client, current(client), 'weekly', '2026-10-31').status_code == 200
    with main.database() as db:
        db.execute("UPDATE reminder_recurrence SET origin='writing'")
    first = current(client)
    assert len(first['related_ids']) == 2
    assert act(client, first, 'done').status_code == 200
    active = current(client)
    due = active['due_start']
    assert client.patch(f"/api/for-you/{active['id']}", json={'status':'dismissed','stop_repeat':True}).status_code == 200
    stopped = current(client)
    assert stopped['status'] == 'dismissed' and stopped['repeat'] is None
    assert stopped['due_start'] == due
    assert len(stopped['related_ids']) == 2
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM reminder_recurrence').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM reminder_repeat_choices').fetchone()[0] == 2
        for note_id in ids:
            discover_repeats(db, main.note_or_404(db,note_id))
    main.initialize()
    assert current(client)['status'] == 'dismissed'
    assert act(client, current(client), 'open').status_code == 200
    restored = current(client)
    assert restored['status'] == 'open' and restored['repeat'] is None
    with main.database() as db:
        for note_id in ids:
            discover_repeats(db, main.note_or_404(db,note_id))
        assert db.execute('SELECT COUNT(*) FROM reminder_recurrence').fetchone()[0] == 0
    assert all(item['status']=='done' for item in feed(client) if item['past_occurrence'])
    assert act(client, first, 'open').status_code == 200
    assert current(client)['repeat'] is None


def test_stop_repeat_rejects_nonrepeating_and_non_dismiss_actions(client):
    seed()
    item = current(client)
    assert client.patch(f"/api/for-you/{item['id']}",json={'status':'dismissed','stop_repeat':True}).status_code == 422
    repeat(client,item)
    item=current(client)
    for status in ['open','done']:
        assert client.patch(f"/api/for-you/{item['id']}",json={'status':status,'stop_repeat':True}).status_code == 422
    assert current(client)['repeat']=='daily'
