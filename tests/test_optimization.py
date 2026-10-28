import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import main, inference
from backend.completions import completed_action
from backend.auto_recurrence import detect_repeat
from backend.for_you import build_suggestions


def test_completed_sentence_does_not_absorb_the_next_unfinished_action():
    text = 'Maya renewed her passport. I paid the electricity bill. I still need to renew my passport.'
    for evidence in ['I paid the electricity bill.', 'I paid the electricity bill']:
        assert completed_action(text, {'value': 'Pay the electricity bill', 'evidence': evidence}) == {'pay','electricity','bill'}
    text = 'I will call Maya; I paid the electricity bill. I need to get water.'
    assert completed_action(text, {'value': 'Pay the electricity bill', 'evidence': 'I paid the electricity bill.'})


def test_source_deadline_and_repeat_do_not_borrow_the_next_sentence():
    text = 'Read a book. Pay the phone bill tomorrow.'
    result = inference.parse_extraction(json.dumps({'memories': [], 'personal': [{'category':'task','value':'Read a book','evidence':'Read a book.'}]}),text)
    inference.validate_meaning(result,text)
    assert result.personal[0].value == 'Read a book'
    text = 'Water the plants every Saturday. Maybe I will go hiking.'
    assert detect_repeat('Water the plants every Saturday','Water the plants every Saturday.',text,date(2026,10,27))['frequency']=='weekly'


def test_quote_formatting_and_unused_record_id_are_repaired_without_a_model_retry(monkeypatch):
    import httpx
    real_client=httpx.Client
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'memories':[{'id':77,'person':'Maya','category':'interest','value':'Loves hiking','evidence':'Maya loves hiking.'}]})}}]})
    monkeypatch.setenv('NEBIUS_API_KEY','test')
    monkeypatch.setattr(inference.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    result=inference.extract_memories('Maya  loves\nhiking.')
    assert result.memories[0].evidence=='Maya  loves\nhiking.'
    assert len(calls)==1


def test_compound_or_partial_evidence_still_requires_deadline_validation():
    text='Refill my prescription tomorrow.'
    result=inference.parse_extraction(json.dumps({'memories':[],'personal':[{'category':'task','value':'Refill my prescription','evidence':'Refill my prescription'}]}),text)
    with pytest.raises(inference.ExtractionValidationError,match='deadline'):
        inference.validate_meaning(result,text)
    text='Renew my passport tomorrow and clean the kitchen on Friday.'
    result=inference.parse_extraction(json.dumps({'memories':[],'personal':[{'category':'task','value':'Renew my passport','evidence':text}]}),text)
    with pytest.raises(inference.ExtractionValidationError,match='deadline'):
        inference.validate_meaning(result,text)


def test_existing_profile_context_keeps_relevant_corrections_without_entire_history():
    people=[{'id':1,'name':'Maya','aliases':['May','M'],'memories':[
        {'id':1,'category':'birthday','value':'Birthday April 8'},
        {'id':2,'category':'interest','value':'Loves hiking'},
        *[{'id':i+3,'category':'context','value':f'Workshop number {i} on another craft'} for i in range(100)]
    ]},{'id':2,'name':'Noor','memories':[{'value':'An unrelated note'}]}]
    compact=inference.context_for_section(people,'Maya corrected her birthday: April 18, not April 8. Maya still loves hiking.')
    assert [person['name'] for person in compact]==['Maya']
    assert {memory['id'] for memory in compact[0]['memories']}=={1,2}
    assert compact[0]['aliases']==[]
    assert len(people[0]['memories'])==102
    assert len(json.dumps(compact)) < len(json.dumps(people))/5


def test_move_in_is_background_rather_than_an_invented_relationship():
    text='eli moved in today.'
    result=inference.parse_extraction(json.dumps({'memories':[{'person':'eli','category':'relationship','value':'moved in today.','evidence':text}]}),text)
    assert result.memories[0].category=='context'
    text='Maya moved in with her brother.'
    result=inference.parse_extraction(json.dumps({'memories':[{'person':'Maya','category':'relationship','value':'Has a brother','evidence':text}]}),text)
    assert result.memories[0].category=='relationship'


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB_PATH',tmp_path/'quality.sqlite3')
    monkeypatch.setattr(main,'build_suggestions',lambda db,timezone='America/New_York',include_all_plans=False:build_suggestions(db,today=date(2026,10,27),timezone=timezone,include_all_plans=include_all_plans))
    with TestClient(main.app) as client:
        yield client


def seed(value,category='task',person=None,entry_date='2026-10-27'):
    with main.database() as db:
        note=db.execute("INSERT INTO notes(text,status,entry_date) VALUES (?,'organized',?)",(value,entry_date)).lastrowid
        main.archive_entry(db,main.note_or_404(db,note))
        if person:
            found=db.execute('SELECT id FROM people WHERE name_key=?',(person.casefold(),)).fetchone()
            pid=found['id'] if found else db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',(person,person.casefold())).lastrowid
            db.execute('INSERT INTO memories(person_id,note_id,category,value,evidence) VALUES (?,?,?,?,?)',(pid,note,category,value,value))
        else:
            db.execute('INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,?,?,?)',(note,category,value,value))
    return note


def feed(client):
    return client.get('/api/for-you?include_all_plans=true').json()['suggestions']


def test_equivalent_cards_preserve_all_sources_and_actions_update_the_whole_group(client):
    seed('Renew my passport')
    seed('I need to renew my passport','reminder')
    item,=feed(client)
    assert len(item['sources'])==len(item['related_ids'])==2
    assert client.patch(f"/api/for-you/{item['id']}",json={'status':'done'}).status_code==200
    done,=feed(client)
    assert done['status']=='done'
    assert client.patch(f"/api/for-you/{item['related_ids'][1]}",json={'status':'open'}).status_code==200
    assert feed(client)[0]['status']=='open'
    assert client.get('/api/search',params={'q':'passport','kind':'task'}).json()['total']==1


def test_grouped_due_dates_snooze_repeat_stop_and_history_stay_synchronized(client):
    seed('Water the plants')
    seed('I need to water the plants','reminder')
    first,=feed(client)
    assert client.patch(f"/api/for-you/{first['id']}/timing",json={'due_date':'2026-10-28','snoozed_until':'2026-10-30'}).status_code==200
    snoozed,=feed(client)
    assert len(snoozed['related_ids'])==2 and snoozed['snoozed']
    assert client.patch(f"/api/for-you/{snoozed['id']}/timing",json={'snoozed_until':None}).status_code==200
    assert client.patch(f"/api/for-you/{snoozed['id']}/repeat",json={'frequency':'weekly','start_date':'2026-10-28'}).status_code==200
    repeating,=feed(client)
    assert repeating['repeat']=='weekly' and len(repeating['related_ids'])==2
    assert client.patch(f"/api/for-you/{repeating['id']}",json={'status':'done'}).status_code==200
    current,history=sorted(feed(client),key=lambda item:item['past_occurrence'])
    assert current['due_start']=='2026-11-04' and history['status']=='done'
    assert len(history['related_ids'])==2
    assert client.patch(f"/api/for-you/{current['id']}/repeat",json={'frequency':None}).status_code==200
    assert not next(item for item in feed(client) if not item['past_occurrence'])['repeat']


def test_distinct_people_dates_goals_and_author_roles_are_not_merged(client):
    seed('Send Maya the guide','plan','Maya')
    seed('I need to send Maya the guide','commitment','Maya')
    seed('Maya promised to send me the guide','commitment','Maya')
    seed('Send Maya the guide','plan','Noor')
    items=feed(client)
    assert len(items)==3
    assert len(next(item for item in items if len(item['related_ids'])==2)['sources'])==2
    seed('Renew my passport tomorrow',entry_date='2026-10-26')
    seed('Renew my passport tomorrow',entry_date='2026-10-27')
    seed('Renew my passport','goal')
    seed('Renew my passport','task')
    assert len(feed(client))==7


def test_future_monthly_occurrences_with_different_anchor_days_are_separate(client):
    seed('Water plants')
    seed('I need to water plants','reminder')
    grouped,=feed(client)
    client.patch(f"/api/for-you/{grouped['id']}/repeat",json={'frequency':'monthly','start_date':'2026-10-30'})
    with main.database() as db:
        rows=db.execute('SELECT suggestion_id FROM reminder_recurrence').fetchall()
        db.execute("UPDATE reminder_recurrence SET next_due='2027-02-28'")
        db.execute("UPDATE reminder_recurrence SET anchor_date='2026-10-31' WHERE suggestion_id=?",(rows[0]['suggestion_id'],))
    assert len(feed(client))==2


def test_ranking_puts_overdue_today_and_soon_ahead_of_open_ended_items(client):
    for value,category,person in [
        ('Renew my passport','task',None),
        ('Submit the application on 2026-10-30','task',None),
        ('Pay the bill on 2026-10-25','task',None),
        ('Call the dentist today','task',None),
        ('Send Mira the guide','commitment','Mira'),
        ('Review budget on 2027-02-01','task',None),
        ('Wants to go shopping','plan','Maya'),
        ('Enjoys shopping','interest','Noor'),
    ]: seed(value,category,person)
    items=feed(client)
    values=[item['sources'][0]['value'] for item in items]
    assert values[:5]==['Pay the bill on 2026-10-25','Call the dentist today','Submit the application on 2026-10-30','Send Mira the guide','Renew my passport']
    assert items[-1]['kind']=='connection'


def test_delete_one_duplicate_keeps_the_other_source_and_its_saved_status(client):
    first=seed('Renew my passport')
    seed('I need to renew my passport','reminder')
    item,=feed(client)
    client.patch(f"/api/for-you/{item['id']}",json={'status':'done'})
    client.delete(f'/api/notes/{first}')
    remaining,=feed(client)
    assert remaining['status']=='done' and len(remaining['sources'])==1


def test_omitted_lowercase_life_update_requires_source_backed_correction():
    text='Maya loves hiking. eli moved in today.'
    result=inference.parse_extraction(json.dumps({'memories':[{'person':'Maya','category':'interest','value':'Loves hiking','evidence':'Maya loves hiking.'}]}),text)
    with pytest.raises(inference.ExtractionValidationError,match='eli'):
        inference.validate_meaning(result,text)
    result=inference.parse_extraction(json.dumps({'memories':[{'person':'eli','category':'context','value':'Moved in today','evidence':'eli moved in today.'}]}),text)
    inference.validate_meaning(result,text)
    assert inference.subject_hints('I visited Microsoft in Seattle.')==[]


def test_grouped_mutation_rolls_back_if_any_member_cannot_be_saved(client):
    import sqlite3
    seed('Renew my passport')
    seed('I need to renew my passport','reminder')
    item,=feed(client)
    blocked=item['related_ids'][1]
    with main.database() as db:
        # Fixture-only trigger simulates a failure after the first member update.
        db.execute("CREATE TRIGGER reject_group_member BEFORE INSERT ON suggestion_actions WHEN NEW.suggestion_id = '"+blocked+"' BEGIN SELECT RAISE(ABORT, 'fixture failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        client.patch(f"/api/for-you/{item['id']}",json={'status':'done'})
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM suggestion_actions').fetchone()[0]==0
    assert feed(client)[0]['status']=='open'


def test_omitted_explicit_intention_is_retried_instead_of_silently_lost():
    text='I need to water plants every Saturday. I need to pay rent on the first of each month.'
    result=inference.parse_extraction(json.dumps({'memories':[],'personal':[{'category':'task','value':'Water plants every Saturday','evidence':'I need to water plants every Saturday.'}]}),text)
    with pytest.raises(inference.ExtractionValidationError,match='rent'):
        inference.validate_meaning(result,text)


def test_timing_repair_cannot_replace_an_action_with_a_date_only_quote():
    text='I need to pay the phone bill tomorrow.'
    result=inference.parse_extraction(json.dumps({'memories':[],'personal':[{'category':'task','value':'Pay the phone bill','evidence':'tomorrow'}]}),text)
    assert result.personal[0].value=='Pay the phone bill'
    with pytest.raises(inference.ExtractionValidationError,match='deadline'):
        inference.validate_meaning(result,text)
