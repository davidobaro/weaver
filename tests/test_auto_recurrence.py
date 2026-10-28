from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.auto_recurrence import detect_repeat, discover_repeats
from backend.models import Extraction, PersonalCandidate, Candidate
from backend.recurrence import next_due

ANCHOR = date(2026, 10, 27)  # Tuesday


@pytest.mark.parametrize('text,frequency,due', [
    ('I need to water the plants every Saturday.', 'weekly', '2026-10-31'),
    ('Water the plants each Saturday.', 'weekly', '2026-10-31'),
    ('Water the plants on Saturdays.', 'weekly', '2026-10-31'),
    ('Every Tuesday, water the plants.', 'weekly', '2026-10-27'),
    ('I should stretch daily.', 'daily', '2026-10-27'),
    ('I want to meditate every day.', 'daily', '2026-10-27'),
    ('Read each day.', 'daily', '2026-10-27'),
    ('I need to pay rent on the first of each month.', 'monthly', '2026-11-01'),
    ('Pay rent every month on the 1st.', 'monthly', '2026-11-01'),
    ('Pay rent monthly on the twenty-first.', 'monthly', '2026-11-21'),
    ('Pay rent every 15th of the month.', 'monthly', '2026-11-15'),
    ('Pay rent on the 31st of every month.', 'monthly', '2026-10-31'),
    ('Pay rent on the last day of each month.', 'monthly', '2026-10-31'),
    ('I need to call Mira every Friday.', 'weekly', '2026-10-30'),
    ('I promised Mira a call every Friday.', 'weekly', '2026-10-30'),
    ('Call Mira every Friday starting November 7.', 'weekly', '2026-11-13'),
    ('Stretch daily starting tomorrow.', 'daily', '2026-10-28'),
    ('Review expenses weekly starting tomorrow.', 'weekly', '2026-10-28'),
    ('Review expenses monthly starting November 12.', 'monthly', '2026-11-12'),
])
def test_clear_source_phrases_create_calendar_schedules(text, frequency, due):
    rule = detect_repeat(text, text, text, ANCHOR)
    assert rule is not None
    assert rule['frequency'] == frequency and rule['next_due'] == due


@pytest.mark.parametrize('text', [
    "I don't need to water the plants every Saturday.",
    'Maybe I will water the plants every Saturday.',
    'I might water the plants every Saturday.',
    'I used to water the plants every Saturday.',
    'I stopped watering the plants every Saturday.',
    'Mira waters the plants every Saturday.',
    'Mira wants to water the plants every Saturday.',
    'Should I water the plants every Saturday?',
    'I need to water the plants every other Saturday.',
    'I want to run twice a week.',
    'Water the plants every Saturday and Sunday.',
    'Water the plants every Saturday and every Wednesday.',
    'Water the plants daily and weekly.',
    'Water the plants every Saturday until November 30.',
    'Water the plants daily for two weeks.',
    'Water the plants every Saturday for the next month.',
    'Water the plants every Saturday for next four weeks.',
    'Water the plants weekly.',
    'Pay rent monthly.',
    'Pay rent on the first of the month.',
    'Buy a daily newspaper.',
    'Water the plants every Saturday at 9am.',
    'Water the plants every Saturday at noon.',
    'Water the plants every Saturday starting next week.',
    'Water the plants every Saturday starting sometime in November.',
    'Pay rent on the 32nd of each month.',
    'Schedule a visit on the first Monday of each month.',
])
def test_ambiguous_third_party_negated_bounded_or_unsupported_schedules_stay_manual(text):
    assert detect_repeat(text, text, text, ANCHOR) is None


def test_short_evidence_cannot_hide_negation_in_its_source_sentence():
    evidence = 'water the plants every Saturday'
    text = "I don't need to " + evidence + '.'
    assert detect_repeat('Water the plants every Saturday', evidence, text, ANCHOR) is None


def test_source_evidence_must_be_present_and_have_unambiguous_context():
    evidence = 'Water the plants every Saturday.'
    assert detect_repeat(evidence, evidence, 'A different entry.', ANCHOR) is None
    assert detect_repeat(evidence, evidence, evidence + '\n' + evidence, ANCHOR) is None


def test_monthly_day_31_in_february_preserves_the_requested_day_after_short_month():
    text = 'Pay rent on the 31st of every month.'
    rule = detect_repeat(text, text, text, date(2027, 2, 10))
    assert rule['next_due'] == '2027-02-28'
    assert next_due(rule['next_due'], rule['anchor_date'], rule['frequency'], '2027-02-28') == '2027-03-31'


def extraction(text, known_people=None):
    # Stand-in model output passes through the real source-preserving pipeline.
    text = text.split('\n\n')[-1]
    if 'Mira' in text:
        return Extraction(memories=[Candidate(person='Mira', category='plan', value=text, evidence=text)])
    return Extraction(memories=[], personal=[PersonalCandidate(category='task', value=text, evidence=text)])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'auto-repeat.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', extraction)
    with TestClient(main.app) as client:
        yield client


def add(client, text='Water the plants every Saturday.', **fields):
    response = client.post('/api/notes', json={'text': text, 'kind': 'journal', 'entry_date': ANCHOR.isoformat(), **fields})
    assert response.status_code == 201
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    return response.json()


def feed(client):
    return client.get('/api/for-you?include_all_plans=true').json()['suggestions']


def test_organizing_creates_source_backed_repeat_that_advances_independently(client):
    note = add(client)
    item, = feed(client)
    assert item['repeat'] == 'weekly' and item['repeat_origin'] == 'writing'
    assert item['due_start'] == '2026-10-31'
    assert item['sources'][0]['note_id'] == note['id'] and item['sources'][0]['evidence'] == note['text']
    assert 'Your writing' in item['why']
    client.patch(f"/api/for-you/{item['id']}", json={'status': 'done'})
    next_item = next(item for item in feed(client) if not item['past_occurrence'])
    assert next_item['due_start'] > '2026-10-31' and next_item['status'] == 'open'
    assert next_item['repeat_origin'] == 'writing'
    assert len(feed(client)) == 2


def test_monthly_and_daily_entries_work_without_manual_timing_setup(client):
    add(client, 'Pay rent on the first of each month.')
    monthly, = feed(client)
    assert monthly['repeat'] == 'monthly' and monthly['due_start'] == '2026-11-01'
    add(client, 'Stretch daily.')
    assert {item['repeat'] for item in feed(client)} == {'daily', 'monthly'}


def test_author_intention_involving_named_person_repeats_but_other_person_habit_does_not(client):
    add(client, 'I need to call Mira every Friday.')
    item, = feed(client)
    assert item['scope'] == 'others' and item['repeat'] == 'weekly'
    assert item['sources'][0]['person'] == 'Mira'
    add(client, 'Mira wants to run every Saturday.')
    assert len([item for item in feed(client) if item['repeat']]) == 1


def test_manual_off_persists_after_reprocessing_and_reads_do_not_reenable(client):
    note = add(client)
    first, = feed(client)
    assert client.patch(f"/api/for-you/{first['id']}/repeat", json={'frequency': None}).status_code == 200
    with main.database() as db:
        discover_repeats(db, main.note_or_404(db, note['id']))
    assert feed(client)[0]['repeat'] is None
    assert client.get('/api/export').json()['reminder_repeat_choices']
    main.initialize()
    assert feed(client)[0]['repeat'] is None


def test_manual_changes_win_and_reprocessing_preserves_current_occurrence(client):
    note = add(client)
    first, = feed(client)
    client.patch(f"/api/for-you/{first['id']}/repeat", json={'frequency': 'monthly', 'start_date': '2026-11-12'})
    actual, = feed(client)
    with main.database() as db:
        discover_repeats(db, main.note_or_404(db, note['id']))
    after, = feed(client)
    assert after['id'] == actual['id'] and after['repeat'] == 'monthly'
    assert after['repeat_origin'] == 'manual' and after['due_start'] == '2026-11-12'


def test_editing_a_repeat_due_date_marks_schedule_as_manual(client):
    add(client)
    item, = feed(client)
    client.patch(f"/api/for-you/{item['id']}/timing", json={'due_date': '2026-11-05'})
    actual, = feed(client)
    assert actual['repeat_origin'] == 'manual' and actual['due_start'] == '2026-11-05'


def test_editing_source_retires_stale_series_and_restore_keeps_stop_preference(client):
    note = add(client)
    item, = feed(client)
    client.patch(f"/api/for-you/{item['id']}/repeat", json={'frequency': None})
    response = client.patch(f"/api/notes/{note['id']}", json={'text': 'A quiet afternoon.', 'expected_revision': 1})
    assert response.status_code == 200
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    assert not any(item['repeat'] for item in feed(client))
    response = client.post(f"/api/notes/{note['id']}/restore", json={'revision': 1, 'expected_revision': 2})
    assert response.status_code == 200
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    restored, = feed(client)
    assert restored['repeat'] is None


def test_getting_existing_old_entries_does_not_retroactively_schedule_them(client):
    with main.database() as db:
        note = db.execute("INSERT INTO notes(text,status,entry_date) VALUES ('Stretch daily.','organized','2026-10-27')").lastrowid
        main.archive_entry(db, main.note_or_404(db, note))
        db.execute("INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,'task','Stretch daily.','Stretch daily.')", (note,))
    assert feed(client)[0]['repeat'] is None
    add(client)
    assert len([item for item in feed(client) if item['repeat']]) == 1


def test_auto_repeat_is_idempotent_and_uses_entry_date_instead_of_read_date(client):
    note = add(client, entry_date='2026-10-01')
    original, = feed(client)
    assert original['due_start'] == '2026-10-03'
    with main.database() as db:
        discover_repeats(db, main.note_or_404(db, note['id']))
    assert feed(client)[0]['id'] == original['id']


def test_month_end_overflow_stays_unscheduled_instead_of_failing_the_entry(client):
    note = add(client, 'Pay rent on the first of each month.', entry_date='9999-12-31')
    actual = client.get(f"/api/notes/{note['id']}").json()
    assert actual['status'] == 'organized'
    assert feed(client)[0]['repeat'] is None


def test_short_evidence_cannot_hide_question_mark_or_extreme_future_start():
    evidence = 'I need to water the plants every Saturday'
    assert detect_repeat(evidence, evidence, evidence + '?', ANCHOR) is None
    evidence = 'Water the plants every Saturday starting 9999-12-31.'
    assert detect_repeat(evidence, evidence, evidence, ANCHOR) is None


def test_quick_note_schedule_and_stop_preference_are_stable_across_viewer_timezones(client):
    text = 'Water the plants every Saturday.'
    with main.database() as db:
        note = db.execute("INSERT INTO notes(text,status,created_at) VALUES (?,'organized','2026-11-01T02:00:00Z')", (text,)).lastrowid
        main.archive_entry(db, main.note_or_404(db, note))
        db.execute("INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,'task',?,?)", (note, text, text))
        discover_repeats(db, main.note_or_404(db, note))
    ny = client.get('/api/for-you?timezone=America/New_York').json()['suggestions'][0]
    tokyo = client.get('/api/for-you?timezone=Asia/Tokyo').json()['suggestions'][0]
    assert ny['id'] == tokyo['id'] and ny['due_start'] == tokyo['due_start'] == '2026-10-31'
    assert client.patch(f"/api/for-you/{tokyo['id']}/repeat?timezone=Asia/Tokyo", json={'frequency': None}).status_code == 200
    assert client.get('/api/for-you?timezone=Asia/Tokyo').json()['suggestions'][0]['repeat'] is None


def test_existing_database_migration_preserves_manual_schedules(client):
    with main.database() as db:
        db.execute('DROP TABLE reminder_recurrence')
        db.execute('CREATE TABLE reminder_recurrence(suggestion_id TEXT PRIMARY KEY,frequency TEXT NOT NULL,anchor_date TEXT NOT NULL,next_due TEXT NOT NULL,occurrence_key TEXT NOT NULL)')
        db.execute("INSERT INTO reminder_recurrence VALUES ('old','monthly','2026-10-31','2026-11-30','old-key')")
    main.initialize()
    with main.database() as db:
        rule = db.execute('SELECT * FROM reminder_recurrence').fetchone()
        assert rule['origin'] == 'manual' and rule['next_due'] == '2026-11-30'


def test_auto_origin_and_stop_preferences_survive_profile_merge_and_undo(client):
    add(client, 'I need to call Mira every Friday.')
    with main.database() as db:
        db.execute("INSERT INTO people(name,name_key) VALUES ('Mira Ellis','mira ellis')")
    people = {p['name']: p['id'] for p in client.get('/api/state').json()['people']}
    response = client.post('/api/people/merge', json={'source_id': people['Mira'], 'target_id': people['Mira Ellis']})
    assert response.status_code == 200
    item, = feed(client)
    assert item['repeat_origin'] == 'writing'
    client.patch(f"/api/for-you/{item['id']}/repeat", json={'frequency': None})
    assert client.post(f"/api/people/merges/{response.json()['id']}/undo").status_code == 200
    assert feed(client)[0]['repeat'] is None
    with main.database() as db:
        note = db.execute('SELECT id FROM notes').fetchone()
        discover_repeats(db, main.note_or_404(db, note['id']))
    assert feed(client)[0]['repeat'] is None


def test_reorganizing_unchanged_intention_keeps_current_occurrence_and_history(client):
    note = add(client)
    first, = feed(client)
    client.patch(f"/api/for-you/{first['id']}", json={'status': 'done'})
    before = next(item for item in feed(client) if not item['past_occurrence'])
    response = client.patch(f"/api/notes/{note['id']}", json={'text': note['text'], 'title': 'A routine worth keeping', 'expected_revision': 1})
    assert response.status_code == 200
    main.app.state.worker.submit(lambda: None).result(timeout=3)
    after = next(item for item in feed(client) if not item['past_occurrence'])
    assert after['id'] == before['id'] and after['due_start'] == before['due_start']
    assert after['repeat_origin'] == 'writing'
    assert after['sources'][0]['note_revision'] == 2
    assert len(feed(client)) == 2
