from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend import for_you
from backend.for_you import build_suggestions

TODAY = date(2026, 10, 27)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'timing.sqlite3')
    monkeypatch.setattr(main, 'build_suggestions', lambda db, timezone='America/New_York', include_all_plans=False:
        build_suggestions(db, today=TODAY, timezone=timezone, include_all_plans=include_all_plans))
    with TestClient(main.app) as client:
        yield client


def seed(value='Renew my passport', person=None, category='task'):
    with main.database() as db:
        note_id = db.execute("INSERT INTO notes(text,status,entry_date) VALUES (?,'organized',?)", (value, TODAY.isoformat())).lastrowid
        main.archive_entry(db, main.note_or_404(db, note_id))
        if person:
            row = db.execute('SELECT id FROM people WHERE name_key=?', (person.casefold(),)).fetchone()
            person_id = row['id'] if row else db.execute('INSERT INTO people(name,name_key) VALUES (?,?)', (person, person.casefold())).lastrowid
            db.execute('INSERT INTO memories(person_id,note_id,category,value,evidence) VALUES (?,?,?,?,?)',
                       (person_id, note_id, category, value, value))
        else:
            db.execute('INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,?,?,?)',
                       (note_id, category, value, value))
    return note_id


def feed(client, all_plans=False):
    response = client.get('/api/for-you' + ('?include_all_plans=true' if all_plans else ''))
    assert response.status_code == 200
    return response.json()['suggestions']


def timing(client, item, **patch):
    return client.patch(f"/api/for-you/{item['id']}/timing", json=patch)


def test_due_date_is_shared_persistent_and_does_not_rewrite_sources(client):
    seed()
    original, = feed(client)
    assert original['due_start'] is None
    assert timing(client, original, due_date='2026-10-30').status_code == 200
    main.initialize()
    actual, = feed(client, True)
    assert actual['id'] == original['id']
    assert actual['due_start'] == actual['due_end'] == '2026-10-30'
    assert actual['due_date_overridden'] is True
    assert actual['original_due_start'] is None
    assert actual['sources'] == original['sources']
    assert client.get('/api/state').json()['notes'][0]['text'] == 'Renew my passport'


def test_clear_date_means_anytime_and_reset_restores_original_date(client):
    seed('Submit the application tomorrow')
    item, = feed(client)
    assert item['due_start'] == '2026-10-28'
    assert timing(client, item, due_date=None).status_code == 200
    cleared, = feed(client)
    assert cleared['id'] == item['id']
    assert cleared['due_start'] is None and cleared['kind'] == 'follow_up'
    assert cleared['due_date_overridden'] is True
    assert timing(client, item, reset_due_date=True).status_code == 200
    restored, = feed(client)
    assert restored['due_start'] == '2026-10-28'
    assert restored['due_date_overridden'] is False


def test_edited_date_does_not_reopen_done_task(client):
    seed()
    item, = feed(client)
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'done'})
    timing(client, item, due_date='2026-10-30')
    actual, = feed(client)
    assert actual['status'] == 'done' and actual['id'] == item['id']


def test_manual_date_orders_with_other_dated_personal_tasks(client):
    seed()
    item, = feed(client)
    seed('Submit the application tomorrow')
    timing(client, item, due_date='2026-10-30')
    assert [item['due_start'] for item in feed(client)] == ['2026-10-28', '2026-10-30']


def test_snooze_keeps_due_date_and_returns_on_the_chosen_day(client):
    seed('Submit the application tomorrow')
    item, = feed(client)
    assert timing(client, item, snoozed_until='2026-10-30').status_code == 200
    main.initialize()
    snoozed, = feed(client)
    assert snoozed['snoozed'] is True and snoozed['status'] == 'open'
    assert snoozed['due_start'] == '2026-10-28'
    with main.database() as db:
        returned, = build_suggestions(db, today=date(2026, 10, 30))['suggestions']
    assert returned['snoozed'] is False
    assert returned['due_start'] == '2026-10-28' and returned['overdue'] is True


def test_bring_back_and_done_clear_snooze_without_losing_manual_date(client):
    seed()
    item, = feed(client)
    timing(client, item, due_date='2026-10-29', snoozed_until='2026-10-30')
    assert timing(client, item, snoozed_until=None).status_code == 200
    actual, = feed(client)
    assert not actual['snoozed'] and actual['due_start'] == '2026-10-29'
    timing(client, item, snoozed_until='2026-10-30')
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'done'})
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'open'})
    actual, = feed(client)
    assert actual['snoozed_until'] is None and actual['due_start'] == '2026-10-29'


def test_named_undated_plan_can_be_scheduled_from_profile_into_feed(client):
    seed('Visit a museum with Mira', 'Mira', 'plan')
    assert feed(client) == []
    profile_item, = feed(client, True)
    assert timing(client, profile_item, due_date='2026-10-29').status_code == 200
    main_item, = feed(client)
    assert main_item['id'] == profile_item['id']
    assert main_item['due_start'] == '2026-10-29' and main_item['scope'] == 'others'


def test_manually_snoozed_undated_plan_returns_to_main_feed(client):
    seed('Visit a museum with Mira', 'Mira', 'plan')
    item, = feed(client, True)
    timing(client, item, snoozed_until='2026-10-29')
    assert feed(client)[0]['snoozed'] is True
    with main.database() as db:
        item, = build_suggestions(db, today=date(2026, 10, 29))['suggestions']
    assert item['snoozed'] is False and item['due_start'] is None


def test_past_plan_with_manual_date_stays_visible(client):
    seed('Museum visit on October 12', 'Mira', 'plan')
    assert feed(client) == []
    item, = feed(client, True)
    timing(client, item, due_date='2026-10-26')
    actual, = feed(client)
    assert actual['due_start'] == '2026-10-26' and actual['overdue'] is True


def test_duplicate_sources_share_settings_and_deleted_facts_do_not_reappear(client):
    first = seed()
    second = seed()
    item, = feed(client)
    assert len(item['sources']) == 2
    timing(client, item, due_date='2026-10-30', snoozed_until='2026-10-29')
    client.delete(f'/api/notes/{first}')
    actual, = feed(client)
    assert len(actual['sources']) == 1 and actual['due_start'] == '2026-10-30'
    client.delete(f'/api/notes/{second}')
    assert feed(client, True) == []
    assert timing(client, item, due_date=None).status_code == 409


def test_export_includes_timing(client):
    seed()
    item, = feed(client)
    timing(client, item, due_date='2026-10-30')
    exported = client.get('/api/export').json()['suggestion_timing']
    assert exported[0]['suggestion_id'] == item['id']
    assert exported[0]['due_date'] == '2026-10-30'


@pytest.mark.parametrize('patch', [
    {}, {'due_date': '2026-02-30'}, {'due_date': 'Friday'},
    {'snoozed_until': TODAY.isoformat()}, {'snoozed_until': (TODAY-timedelta(days=1)).isoformat()},
    {'reset_due_date': True, 'due_date': None}, {'reset_due_date': False}, {'unexpected': True},
])
def test_invalid_updates_do_not_change_existing_timing(client, patch):
    seed()
    item, = feed(client)
    timing(client, item, due_date='2026-10-30')
    assert client.patch(f"/api/for-you/{item['id']}/timing", json=patch).status_code == 422
    assert feed(client)[0]['due_start'] == '2026-10-30'


def test_birthdays_connections_and_unknown_suggestions_cannot_be_scheduled(client):
    seed('Birthday October 29', 'Mira', 'birthday')
    item, = feed(client)
    assert item['can_schedule'] is False
    assert timing(client, item, due_date=None).status_code == 422
    assert client.patch('/api/for-you/missing/timing', json={'due_date': None}).status_code == 409
    assert client.patch(f"/api/for-you/{item['id']}/timing?timezone=Invalid/Zone", json={'due_date': None}).status_code == 422


def test_possible_connection_cannot_be_given_a_task_due_date(client):
    seed('Wants to go to the mall', 'Mira', 'plan')
    seed('Enjoys shopping for shoes', 'Noor', 'interest')
    connection, = feed(client)
    assert connection['kind'] == 'connection' and not connection['can_schedule']
    assert timing(client, connection, due_date='2026-10-30').status_code == 422


def test_snooze_validation_uses_the_viewers_local_day(client, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 28, 1, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(for_you, 'datetime', Clock)
    monkeypatch.setattr(main, 'build_suggestions', build_suggestions)
    seed()
    item, = feed(client)
    path = f"/api/for-you/{item['id']}/timing"
    assert client.patch(path+'?timezone=America/New_York', json={'snoozed_until': '2026-10-28'}).status_code == 200
    assert client.patch(path+'?timezone=Asia/Tokyo', json={'snoozed_until': '2026-10-28'}).status_code == 422


def test_merge_and_undo_keep_manual_timing(client):
    seed('Visit a museum', 'Mira', 'plan')
    seed('Enjoys jazz', 'Mira Ellis', 'interest')
    item, = feed(client, True)
    timing(client, item, due_date='2026-10-30', snoozed_until='2026-10-29')
    people = client.get('/api/state').json()['people']
    ids = {p['name']: p['id'] for p in people}
    response = client.post('/api/people/merge', json={'source_id': ids['Mira'], 'target_id': ids['Mira Ellis']})
    assert response.status_code == 200
    merged, = feed(client)
    assert merged['due_start'] == '2026-10-30' and merged['snoozed'] is True
    response = client.post(f"/api/people/merges/{response.json()['id']}/undo")
    assert response.status_code == 200
    restored, = feed(client)
    assert restored['due_start'] == '2026-10-30' and restored['snoozed'] is True
