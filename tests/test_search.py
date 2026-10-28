from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.for_you import build_suggestions
from backend.search import score, excerpt


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'search.sqlite3')
    monkeypatch.setattr(main, 'build_suggestions', lambda db, timezone='America/New_York', include_all_plans=False:
        build_suggestions(db, today=date(2026, 10, 27), timezone=timezone, include_all_plans=include_all_plans))
    monkeypatch.setattr(main, 'extract_memories', lambda *args: pytest.fail('Search must not call inference'))
    with TestClient(main.app) as client:
        yield client


def seed(text='Maya loves hiking. I promised Maya a trail guide. Renew my passport tomorrow.', title='A walk with Maya'):
    with main.database() as db:
        note = db.execute("INSERT INTO notes(text,title,status,kind,entry_date) VALUES (?,?,'organized','journal','2026-10-27')", (text, title)).lastrowid
        main.archive_entry(db, main.note_or_404(db, note))
        person = db.execute("INSERT INTO people(name,name_key) VALUES ('Maya Chen','maya chen')").lastrowid
        db.execute("INSERT INTO person_aliases(person_id,name,name_key) VALUES (?,'May','may')", (person,))
        for category, value, evidence in [('interest', 'Loves hiking', 'Maya loves hiking'), ('commitment', 'I promised Maya a trail guide', 'I promised Maya a trail guide')]:
            db.execute('INSERT INTO memories(person_id,note_id,category,value,evidence) VALUES (?,?,?,?,?)', (person, note, category, value, evidence))
        db.execute("INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,'task','Renew my passport tomorrow','Renew my passport tomorrow')", (note,))
    return note, person


def search(client, q, kind='all', **params):
    response = client.get('/api/search', params={'q': q, 'kind': kind, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_workspace_search_returns_source_backed_entries_people_memories_and_tasks(client):
    note, person = seed()
    result = search(client, 'Maya')
    assert set(item['kind'] for item in result['results']) == {'entry', 'person', 'memory', 'task'}
    assert result['total'] == sum(result['counts'].values())
    assert len({item['id'] for item in result['results']}) == result['total']
    assert all(item['note_id'] == note and item['note_revision'] == 1 for item in result['results'])
    assert next(item for item in result['results'] if item['kind'] == 'person')['person_id'] == person


def test_aliases_match_profiles_memories_and_named_tasks(client):
    seed()
    result = search(client, 'May trail')
    assert result['counts']['person'] == 1
    assert result['counts']['memory'] == result['counts']['task'] == 1
    assert search(client, 'Chen')['results'][0]['kind'] == 'person'


@pytest.mark.parametrize('query', ['passport renew', 'PASSP renew', 'renew, passport!'])
def test_tasks_match_all_words_in_any_order_with_prefixes(client, query):
    seed()
    result = search(client, query, 'task')
    assert result['total'] == 1
    task = result['results'][0]
    assert task['person'] == 'You' and task['person_id'] is None
    assert task['due_start'] == '2026-10-28' and task['status'] == 'open'
    assert search(client, query + ' unicorn')['total'] == 0


def test_accent_and_case_insensitive_search_and_excerpt_near_match(client):
    seed(text='A quiet morning. ' * 40 + 'Café with Zoë.', title='Café notes')
    result = search(client, 'CAFE ZOE', 'entry')
    assert result['total'] == 1
    assert 'Café with Zoë' in result['results'][0]['excerpt']
    assert result['results'][0]['excerpt'].startswith('…')
    assert len(result['results'][0]['excerpt']) <= 242


def test_exact_name_ranks_ahead_of_entry_mentions(client):
    seed()
    result = search(client, 'Maya Chen')
    assert result['results'][0]['kind'] == 'person'


def test_filters_preserve_counts_and_total_matches_selected_type(client):
    seed()
    all_results = search(client, 'Maya')
    for kind in ['entry', 'person', 'memory', 'task']:
        filtered = search(client, 'Maya', kind)
        assert filtered['counts'] == all_results['counts']
        assert filtered['total'] == all_results['counts'][kind]
        assert all(item['kind'] == kind for item in filtered['results'])


def test_limit_is_bounded_and_counts_are_not_truncated(client):
    seed()
    result = search(client, 'Maya', limit=1)
    assert len(result['results']) == 1 and result['total'] > 1
    full = search(client, 'Maya', limit=100)
    assert full['total'] == result['total']
    assert len(full['results']) == full['total']


@pytest.mark.parametrize('query', ['', '   ', '%%%'])
def test_empty_or_non_word_query_returns_no_workspace_dump(client, query):
    seed()
    result = search(client, query)
    assert result == {'results': [], 'counts': {'entry': 0, 'person': 0, 'memory': 0, 'task': 0}, 'total': 0}


def test_inactive_facts_do_not_match_profiles_or_memories(client):
    seed()
    with main.database() as db:
        db.execute("UPDATE memories SET active=0 WHERE category='interest'")
    result = search(client, 'hiking')
    assert result['counts'] == {'entry': 1, 'person': 0, 'memory': 0, 'task': 0}


def test_deleted_entries_and_their_extracted_facts_disappear(client):
    note, _ = seed()
    assert client.delete(f'/api/notes/{note}').status_code == 204
    assert search(client, 'Maya')['total'] == 0
    assert search(client, 'passport')['total'] == 0


def test_pending_entry_is_searchable_before_ai_organization(client):
    with main.database() as db:
        db.execute("INSERT INTO notes(text,title,status) VALUES ('A quiet orchard walk','Sunday','queued')")
    result = search(client, 'orchard')
    assert result['total'] == 1 and result['results'][0]['kind'] == 'entry'


def test_done_dismissed_and_snoozed_tasks_have_current_status(client):
    seed()
    task = search(client, 'passport', 'task')['results'][0]
    suggestion_id = task['id'].removeprefix('task:')
    client.patch(f'/api/for-you/{suggestion_id}/timing', json={'snoozed_until': '2026-10-30'})
    assert search(client, 'passport', 'task')['results'][0]['snoozed']
    for status in ['done', 'dismissed', 'open']:
        client.patch(f'/api/for-you/{suggestion_id}', json={'status': status})
        result = search(client, 'passport', 'task')['results'][0]
        assert result['status'] == status and not result['snoozed']


def test_recurring_tasks_include_distinct_history_and_live_occurrence(client):
    seed()
    task = search(client, 'passport', 'task')['results'][0]
    client.patch(f"/api/for-you/{task['id'].removeprefix('task:')}/repeat", json={'frequency': 'weekly', 'start_date': '2026-10-27'})
    task = search(client, 'passport', 'task')['results'][0]
    client.patch(f"/api/for-you/{task['id'].removeprefix('task:')}", json={'status': 'done'})
    result = search(client, 'passport', 'task')
    assert result['total'] == 2
    pending, past = result['results']
    assert pending['status'] == 'open' and pending['due_start'] == '2026-11-03'
    assert past['past_occurrence'] and past['status'] == 'done'
    assert pending['id'] != past['id']


def test_memory_result_links_to_the_actual_source_revision(client):
    note, _ = seed()
    with main.database() as db:
        db.execute('UPDATE notes SET revision=2, text=? WHERE id=?', ('A revised entry', note))
    result = search(client, 'hiking', 'memory')['results'][0]
    assert result['note_revision'] == 1
    source = client.get(f"/api/notes/{note}?revision={result['note_revision']}")
    assert source.status_code == 200 and 'Maya loves hiking' in source.json()['text']
    assert search(client, 'hiking', 'entry')['total'] == 0


def test_validation_rejects_invalid_scope_timezone_length_and_limits(client):
    for params in [{'kind': 'unknown'}, {'timezone': 'Nope'}, {'q': 'a' * 201}, {'limit': 0}, {'limit': 101}]:
        assert client.get('/api/search', params=params).status_code == 422


def test_person_without_facts_can_be_found_and_has_no_invented_source(client):
    with main.database() as db:
        db.execute("INSERT INTO people(name,name_key) VALUES ('Noor','noor')")
    result = search(client, 'Noor')['results'][0]
    assert result['kind'] == 'person' and result['note_id'] is None


def test_matching_does_not_treat_middle_of_word_as_a_name():
    assert score('Ann', 'Annabelle') is not None
    assert score('Ann', 'Joanne') is None
    assert score('cafe', 'Café') is not None
    assert '<script>' in excerpt('<script>alert("x")</script>', 'alert')  # Returned as text, never HTML.


def test_persistent_you_profile_is_searchable_and_links_personal_source(client):
    result = search(client, 'You', 'person')['results'][0]
    assert result['person_id'] == 0 and result['note_id'] is None
    note, _ = seed()
    result = search(client, 'passport', 'person')['results'][0]
    assert result['title'] == 'You' and result['person_id'] == 0
    assert result['note_id'] == note
