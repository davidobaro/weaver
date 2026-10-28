from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.for_you import build_suggestions
from backend.notifications import claim, event_keys

TODAY = date(2026, 10, 27)


def item(**changes):
    return dict(id='a', status='open', snoozed=False, kind='date', due_start='2026-10-27', snoozed_until=None, **changes)


def feed(*items):
    return {'today': TODAY.isoformat(), 'suggestions': list(items)}


def test_eligible_events_skip_closed_future_undated_connections_and_snoozed():
    items = [item()]
    for changes in [{'status': 'done'}, {'status': 'dismissed'}, {'snoozed': True},
                    {'due_start': '2026-10-28'}, {'due_start': None}, {'kind': 'connection'}]:
        candidate = item()
        candidate.update(changes)
        items.append(candidate)
    assert len(list(event_keys(feed(*items)))) == 1


def test_snooze_can_return_undated_or_future_task_then_alert_at_later_due_date():
    candidate = item()
    candidate.update(due_start='2026-10-30', snoozed_until='2026-10-27')
    returned, = event_keys(feed(candidate))
    later, = event_keys({'today': '2026-10-30', 'suggestions': [candidate]})
    assert returned != later
    candidate['due_start'] = None
    assert list(event_keys(feed(candidate))) == [returned]


def test_overdue_event_does_not_repeat_every_day_but_new_dates_do():
    candidate = item()
    original = list(event_keys(feed(candidate)))
    assert original == list(event_keys({'today': '2026-10-29', 'suggestions': [candidate]}))
    candidate['due_start'] = '2026-10-26'
    assert original != list(event_keys(feed(candidate)))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'notifications.sqlite3')
    monkeypatch.setattr(main, 'build_suggestions', lambda db, timezone='America/New_York', include_all_plans=False:
        build_suggestions(db, today=TODAY, timezone=timezone, include_all_plans=include_all_plans))
    with TestClient(main.app) as client:
        yield client


def test_atomic_claim_across_tabs_receipts_survive_restart_and_devices_are_separate(client):
    device = str(uuid4())
    def reserve():
        with main.database() as db:
            db.execute('BEGIN IMMEDIATE')
            return claim(db, device, feed(item()), now=1000)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(result['count'] for result in results) == [0, 1]
    token = next(result['token'] for result in results if result['token'])
    assert client.post(f'/api/notifications/{device}/{token}/ack').status_code == 200
    main.initialize()
    with main.database() as db:
        assert claim(db, device, feed(item()), now=2000)['count'] == 0
        assert claim(db, str(uuid4()), feed(item()), now=2000)['count'] == 1


def test_failed_delivery_lease_expires_and_old_ack_cannot_ack_replacement(client):
    device = str(uuid4())
    with main.database() as db:
        first = claim(db, device, feed(item()), now=1000)
        assert claim(db, device, feed(item()), now=1119)['count'] == 0
        second = claim(db, device, feed(item()), now=1121)
        assert second['count'] == 1 and first['token'] != second['token']
    client.post(f"/api/notifications/{device}/{first['token']}/ack")
    with main.database() as db:
        assert claim(db, device, feed(item()), now=1242)['count'] == 1


def test_real_feed_claim_groups_counts_without_exposing_note_content(client):
    with main.database() as db:
        for text in ['Renew passport today', 'Call the dentist on 2026-10-26', 'Book a flight tomorrow']:
            note = db.execute("INSERT INTO notes(text,status,entry_date) VALUES (?,'organized',?)", (text, TODAY.isoformat())).lastrowid
            main.archive_entry(db, main.note_or_404(db, note))
            db.execute('INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,?,?,?)', (note, 'task', text, text))
    device = str(uuid4())
    result = client.post(f'/api/notifications/{device}/claim').json()
    assert result['count'] == 2
    assert set(result) == {'count', 'token'}
    assert client.post(f'/api/notifications/{device}/claim').json() == {'count': 0, 'token': None}
    assert client.post(f"/api/notifications/{device}/{result['token']}/ack").status_code == 200


def test_claim_rejects_invalid_device_timezone_and_cross_origin(client):
    assert client.post('/api/notifications/not-a-device/claim').status_code == 422
    device = str(uuid4())
    assert client.post(f'/api/notifications/{device}/claim?timezone=Nope').status_code == 422
    assert client.post(f'/api/notifications/{device}/claim', headers={'Origin': 'https://example.com'}).status_code == 403
