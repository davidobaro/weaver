from fastapi.testclient import TestClient

from backend import main
from backend.profiles import profile_about


def memory(id, category, value, active=1):
    return {'id': id, 'category': category, 'value': value, 'active': active,
            'note_id': 1, 'evidence': 'Original source words.', 'edited': 0}


NOTES = {1: {'created_at': '2026-10-14T23:00:00Z'}}


def test_overview_preserves_uncertainty_and_keeps_plan_as_a_plan():
    result = profile_about([
        memory(1, 'context', 'May be starting college next year'),
        memory(2, 'plan', 'Wants to go to the mall'),
        memory(3, 'commitment', 'I promised to send a trail guide'),
    ], NOTES)
    assert [(f['label'], f['value']) for f in result['facts']] == [
        ('Background', 'May be starting college next year'),
        ('Current plans', 'Wants to go to the mall'),
    ]
    assert result['facts'][0]['evidence'] == 'Original source words.'
    assert result['facts'][0]['noted_at'] == NOTES[1]['created_at']


def test_overview_uses_current_facts_and_omits_missing_sources():
    records = [memory(1, 'birthday', 'June 12', active=0),
               memory(2, 'birthday', 'June 14'), memory(3, 'interest', 'Enjoys hiking')]
    records[2]['note_id'] = 99
    result = profile_about(records, NOTES)
    assert [f['value'] for f in result['facts']] == ['June 14']


def test_background_is_derived_even_from_older_miscategorized_entries():
    result = profile_about([
        memory(1, 'plan', 'started college'),
        memory(2, 'plan', 'ask Jason how his first day went'),
    ], NOTES)
    assert [(f['label'], f['value']) for f in result['facts']] == [('Background', 'started college')]


def test_overview_stays_short_and_diverse():
    records = [memory(i, 'context', f'Life update {i}') for i in range(1, 10)]
    records += [memory(10, 'interest', 'Likes hiking'), memory(11, 'birthday', 'June 12'),
                memory(12, 'relationship', 'Maya’s sister'), memory(13, 'plan', 'Visit a museum')]
    facts = profile_about(records, NOTES)['facts']
    assert len(facts) == 5
    assert [f['value'] for f in facts[:2]] == ['Life update 9', 'Life update 8']
    assert {f['label'] for f in facts} >= {'Birthday', 'Interests', 'Connections'}


def test_about_updates_after_edit_and_does_not_survive_deletion(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'profiles.sqlite3')
    with TestClient(main.app) as client:
        with main.database() as db:
            person = db.execute("INSERT INTO people(name,name_key) VALUES ('Vivian','vivian')").lastrowid
            note = db.execute("INSERT INTO notes(text,status) VALUES ('Vivian moved to a different state.','organized')").lastrowid
            fact = db.execute('''INSERT INTO memories(person_id,note_id,category,value,evidence)
                              VALUES (?,?,'context','Moved to a different state','Vivian moved to a different state.')''', (person, note)).lastrowid
        assert client.get('/api/state').json()['people'][0]['about']['facts'][0]['value'] == 'Moved to a different state'
        response = client.patch(f'/api/memories/{fact}', json={
            'person': 'Vivian', 'category': 'context', 'value': 'Moved to Vermont',
        })
        assert response.status_code == 200
        facts = client.get('/api/state').json()['people'][0]['about']['facts']
        assert [f['value'] for f in facts] == ['Moved to Vermont']
        assert facts[0]['edited'] is True
        assert facts[0]['note_id'] == note
        client.delete(f'/api/notes/{note}')
        assert client.get('/api/state').json()['people'] == []
