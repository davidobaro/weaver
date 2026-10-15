from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.for_you import build_suggestions, date_window

TODAY = date(2026, 10, 14)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'suggestions.sqlite3')
    monkeypatch.setattr(main, 'build_suggestions', lambda db, timezone='America/New_York':
                        build_suggestions(db, today=TODAY, timezone=timezone))
    with TestClient(main.app) as client:
        yield client


def remember(name, category, value, *, active=1, noted_at='2026-10-14T16:00:00Z'):
    with main.database() as db:
        person = db.execute('SELECT id FROM people WHERE name_key = ?', (name.casefold(),)).fetchone()
        person_id = person['id'] if person else db.execute(
            'INSERT INTO people(name,name_key) VALUES (?,?)', (name, name.casefold())).lastrowid
        note_id = db.execute("INSERT INTO notes(text,status,created_at) VALUES (?,'organized',?)",
                             (value, noted_at)).lastrowid
        memory_id = db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence,active)
                               VALUES (?,?,?,?,?,?)''', (person_id, note_id, category, value, value, active)).lastrowid
        return memory_id, note_id


def suggestions(client):
    response = client.get('/api/for-you')
    assert response.status_code == 200
    return response.json()['suggestions']


def test_commitments_have_sources_without_inventing_a_deadline(client):
    memory_id, note_id = remember('Maya', 'commitment', 'I promised Maya a trail guide.')
    item, = suggestions(client)
    assert item['kind'] == 'follow_up'
    assert item['due_start'] is None
    assert item['sources'][0]['id'] == memory_id
    assert item['sources'][0]['note_id'] == note_id
    assert item['sources'][0]['evidence'] == 'I promised Maya a trail guide.'


def test_only_active_facts_generate_suggestions(client):
    remember('Maya', 'birthday', 'October 15', active=0)
    remember('Maya', 'birthday', 'December 15')
    assert suggestions(client) == []


def test_birthday_next_week_preserves_a_range(client):
    remember('Joshua', 'birthday', 'Birthday next week')
    item, = suggestions(client)
    assert item['due_start'] == '2026-10-19'
    assert item['due_end'] == '2026-10-25'


def test_relative_date_is_anchored_to_note_not_read_time(client):
    remember('Joshua', 'birthday', 'Birthday next week', noted_at='2026-09-01T16:00:00Z')
    assert suggestions(client) == []


def test_relative_date_uses_local_note_day_at_utc_boundary(client):
    remember('Joshua', 'birthday', 'Birthday next week', noted_at='2026-10-19T01:00:00Z')
    item, = suggestions(client)
    assert item['due_start'] == '2026-10-19'  # Still Sunday in New York.


def test_connections_require_two_explicit_complementary_facts(client):
    remember('Joshua', 'plan', 'Wants to go to the mall')
    remember('Stephen', 'interest', 'Enjoys shopping for shoes')
    remember('Maya', 'interest', 'Likes hiking')
    item, = suggestions(client)
    assert item['kind'] == 'connection'
    assert {s['person'] for s in item['sources']} == {'Joshua', 'Stephen'}
    assert 'possible' in item['title'].lower()
    assert 'shopping' in item['why']


def test_no_connection_from_cooccurrence_or_obvious_short_name_alias(client):
    remember('Joshua', 'plan', 'Wants to play soccer')
    remember('Josh', 'interest', 'Likes soccer')
    remember('Stephen', 'context', 'Met Joshua for soccer')
    assert suggestions(client) == []


def test_past_plans_do_not_recur_but_past_commitments_can_be_revisited(client):
    remember('Maya', 'plan', 'Visit a garden on October 12')
    remember('Stephen', 'commitment', 'Send the photos by October 12')
    item, = suggestions(client)
    assert item['kind'] == 'follow_up'
    assert item['overdue'] is True
    assert item['due_start'] == '2026-10-12'


def test_mark_done_dismiss_restore_and_reopen(client):
    remember('Maya', 'commitment', 'I promised Maya a trail guide.')
    item, = suggestions(client)
    path = f"/api/for-you/{item['id']}"
    assert client.patch(path, json={'status': 'done'}).status_code == 200
    main.initialize()
    assert suggestions(client)[0]['status'] == 'done'
    assert client.patch(path, json={'status': 'dismissed'}).status_code == 200
    assert suggestions(client)[0]['status'] == 'dismissed'
    assert client.patch(path, json={'status': 'open'}).status_code == 200
    assert suggestions(client)[0]['status'] == 'open'


def test_repeated_fact_keeps_dismissal_and_deleted_note_disappears(client):
    memory, old_note = remember('Maya', 'commitment', 'I promised Maya a trail guide.')
    item, = suggestions(client)
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'dismissed'})
    with main.database() as db:
        db.execute('UPDATE memories SET active=0 WHERE id=?', (memory,))
    _, new_note = remember('Maya', 'commitment', 'I promised Maya a trail guide.')
    repeated, = suggestions(client)
    assert repeated['id'] == item['id']
    assert repeated['status'] == 'dismissed'
    client.delete(f'/api/notes/{new_note}')
    assert suggestions(client) == []
    assert client.patch(f"/api/for-you/{item['id']}", json={'status': 'done'}).status_code == 409


def test_birthday_rollover_leap_day_and_ambiguous_dates():
    assert date_window('January 2', TODAY, date(2026, 12, 30), True) == (date(2027, 1, 2),) * 2
    assert date_window('February 29', TODAY, date(2028, 2, 27), True) == (date(2028, 2, 29),) * 2
    assert date_window('February 30', TODAY, TODAY, True) is None
    assert date_window('03/04', TODAY, TODAY, True) is None
    assert date_window('maybe October 16', TODAY, TODAY, True) is None
    assert date_window('probably tomorrow', TODAY, TODAY) is None
    assert date_window('not on October 16', TODAY, TODAY, True) is None
    assert date_window('in 3 days', TODAY, TODAY) == (TODAY + timedelta(days=3),) * 2


def test_invalid_timezone_and_actions_are_rejected(client):
    assert client.get('/api/for-you?timezone=Invalid/Zone').status_code == 422
    assert client.patch('/api/for-you/unknown', json={'status': 'done'}).status_code == 409
    assert client.patch('/api/for-you/unknown', json={'status': 'send_message'}).status_code == 422


def test_negative_interest_does_not_create_a_connection(client):
    remember('Joshua', 'plan', 'Wants to go to the mall')
    remember('Stephen', 'interest', 'Does not enjoy shopping')
    assert suggestions(client) == []


def test_next_year_birthday_is_a_new_occurrence(client):
    remember('Joshua', 'birthday', 'October 15')
    item, = suggestions(client)
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'done'})
    with main.database() as db:
        next_year = build_suggestions(db, today=date(2027, 10, 14))['suggestions']
    assert next_year[0]['id'] != item['id']
    assert next_year[0]['status'] == 'open'


def test_explicit_weekday_is_anchored_to_source_but_next_weekday_is_ambiguous(client):
    remember('Grandma', 'plan', 'Leaving on Friday')
    item, = suggestions(client)
    assert item['due_start'] == '2026-10-16'
    assert item['due_end'] == '2026-10-16'
    assert date_window('Next Friday', TODAY, TODAY) is None
    assert date_window('not on Friday', TODAY, TODAY) is None
    assert date_window('next week on Friday', TODAY, TODAY) == (date(2026, 10, 23),) * 2
