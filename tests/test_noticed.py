import json
import pytest
from fastapi.testclient import TestClient
from backend import main

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB_PATH',tmp_path/'noticed.sqlite3')
    with TestClient(main.app) as client:
        yield client


def seed(text='I met Leila. Leila loves pottery. I need to book a dentist appointment.',status='organized'):
    with main.database() as db:
        id=db.execute("INSERT INTO notes(text,status,kind,entry_date) VALUES (?,?,'journal','2026-10-28')",(text,status)).lastrowid
        main.archive_entry(db,main.note_or_404(db,id))
        return id


def noticed(client,id):
    return client.get(f'/api/notes/{id}/noticed').json()


def test_noticed_counts_and_quotes_come_from_stored_current_version(client):
    id=seed()
    with main.database() as db:
        person=db.execute("INSERT INTO people(name,name_key) VALUES ('Leila','leila')").lastrowid
        db.execute("INSERT INTO memories(person_id,note_id,note_revision,category,value,evidence) VALUES (?,?,1,'interest','Loves pottery','Leila loves pottery.')",(person,id))
        db.execute("INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,'task','Book a dentist appointment','I need to book a dentist appointment.')",(id,))
    result=noticed(client,id)
    assert result['counts']=={'people':1,'facts':1,'tasks':1,'completed':0}
    assert result['people']==[{'id':person,'name':'Leila'}]
    assert {item['evidence'] for item in result['items']}=={'Leila loves pottery.','I need to book a dentist appointment.'}
    note=client.get('/api/state').json()['notes'][0]
    assert note['noticed']=={key:result[key] for key in ('counts','version')}
    assert 'items' not in note['noticed']


def test_noticed_retains_updated_later_fact_and_refreshes_version(client):
    id=seed()
    with main.database() as db:
        person=db.execute("INSERT INTO people(name,name_key) VALUES ('Leila','leila')").lastrowid
        db.execute("INSERT INTO memories(person_id,note_id,note_revision,category,value,evidence) VALUES (?,?,1,'interest','Loves pottery','Leila loves pottery.')",(person,id))
    before=noticed(client,id)
    with main.database() as db:db.execute('UPDATE memories SET active=0 WHERE note_id=?',(id,))
    after=noticed(client,id)
    assert after['counts']==before['counts']
    assert after['items'][0]['active'] is False
    assert after['version']!=before['version']


def test_noticed_excludes_old_revision_and_deduplicates_equivalent_tasks(client):
    id=seed()
    with main.database() as db:
        db.execute('UPDATE notes SET revision=2 WHERE id=?',(id,))
        for revision,category,value in [(1,'task','An old task'),(2,'task','Book a dentist appointment'),(2,'reminder','I need to book a dentist appointment')]:
            db.execute('INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,?,?,?,?)',(id,revision,category,value,value))
    result=noticed(client,id)
    assert result['counts']['tasks']==1
    assert len(result['items'])==1
    assert 'old' not in result['items'][0]['value']


def test_completed_action_receipt_does_not_claim_an_unmatched_task_was_closed(client):
    id=seed('I paid the electricity bill. Maya renewed her passport.')
    candidates=[{'value':'Pay the electricity bill','evidence':'I paid the electricity bill.'},
                {'value':'Renew my passport','evidence':'Maya renewed her passport.'}]
    with main.database() as db:db.execute('UPDATE notes SET completion_candidates=? WHERE id=?',(json.dumps(candidates),id))
    result=noticed(client,id)
    assert result['counts']['completed']==1
    assert result['counts']['tasks']==0
    assert result['items'][0]['kind']=='completed'
    assert result['items'][0]['value']=='Pay the electricity bill'


@pytest.mark.parametrize('status',['queued','processing','pending','failed'])
def test_unorganized_entries_do_not_present_candidates_as_confirmed_results(client,status):
    id=seed(status=status)
    assert noticed(client,id)['counts'] is None
    assert client.get('/api/state').json()['notes'][0]['noticed'] is None


def test_reflection_has_an_empty_receipt_and_deleted_entry_has_none(client):
    id=seed('A quiet day, and I feel grateful.')
    assert noticed(client,id)['counts']=={'people':0,'facts':0,'tasks':0,'completed':0}
    assert noticed(client,id)['items']==[]
    assert client.get('/api/notes/999/noticed').status_code==404
    client.delete(f'/api/notes/{id}')
    assert client.get(f'/api/notes/{id}/noticed').status_code==404
