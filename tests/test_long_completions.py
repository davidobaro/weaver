"""Long-journal completion regressions; no provider calls or personal database."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import main, inference
from backend.completions import completed_action

JOURNAL = '''I got a few things off my list today. I booked my dentist appointment for next Thursday and watered the plants this afternoon.

I also paid rent for this month. I spent twenty minutes reading this evening and enjoyed having a quiet break.

I sent Maya the beginner ceramics class and emailed Priya my sourdough recipe. Priya replied with a photo of her latest loaf.

Stewy and I talked about his revised Vermont plans. He’s now aiming for the second weekend in December, though he hasn’t booked anything yet.'''


@pytest.mark.parametrize('text,value,evidence,expected', [
    (JOURNAL, 'Book dentist appointment', 'booked my dentist appointment for next Thursday', True),
    (JOURNAL, 'Water the plants', 'watered the plants this afternoon', True),
    (JOURNAL, 'Pay rent', 'paid rent for this month', True),
    (JOURNAL, 'Send Maya the beginner ceramics class', 'sent Maya the beginner ceramics class', True),
    (JOURNAL, 'Email Priya my sourdough recipe', 'emailed Priya my sourdough recipe', True),
    ('I paid the electricity bill but still need to pay rent.', 'Pay electricity bill', 'paid the electricity bill', True),
    ('I still need to pay rent but I paid the electricity bill.', 'Pay electricity bill', 'paid the electricity bill', True),
    ('I booked a dentist appointment and I paid the electricity bill.', 'Pay electricity bill', 'paid the electricity bill', True),
    ('I booked a dentist appointment and watered the plants.', 'Water plants', 'watered the plants', True),
    ('I booked a dentist appointment, then watered the plants.', 'Water plants', 'watered the plants', True),
    ('I paid the electricity bill and Maya paid the phone bill.', 'Pay phone bill', 'paid the phone bill', False),
    ('Maya booked a dentist appointment and watered the plants.', 'Water plants', 'watered the plants', False),
    ('I booked a dentist appointment and Maya watered the plants.', 'Water plants', 'watered the plants', False),
    ('I might have booked a dentist appointment and watered the plants.', 'Water plants', 'watered the plants', False),
    ('I will have booked a dentist appointment and watered the plants.', 'Water plants', 'watered the plants', False),
    ('I paid the electricity bill and Maya might pay rent.', 'Pay electricity bill', 'paid the electricity bill', True),
    ('I renewed my passport, or at least I think I did.', 'Renew passport', 'renewed my passport', False),
    ('If I booked the dentist appointment, I could relax.', 'Book dentist appointment', 'booked the dentist appointment', False),
    ('I have not watered the plants.', 'Water plants', 'watered the plants', False),
    ('I watered the plants?', 'Water plants', 'watered the plants', False),
    ('Priya emailed my sourdough recipe.', 'Email sourdough recipe', 'emailed my sourdough recipe', False),
    ('I paid rent. I still need to water the plants.', 'Pay rent', 'paid rent', True),
    ('I paid the phone bill and paid the electricity bill.', 'Pay electricity bill', 'paid the electricity bill', True),
    ('I paid the phone bill and Maya paid the electricity bill.', 'Pay electricity bill', 'paid the electricity bill', False),
    ('Maya booked a dentist appointment and I paid the electricity bill.', 'Pay electricity bill', 'paid the electricity bill', True),
    ('I booked my dentist appointment, but I still need to renew my passport.', 'Book dentist appointment', 'I booked my dentist appointment, but I still need to renew my passport.', True),
    ('I paid the phone bill and Maya paid the electricity bill.', 'Pay electricity bill', 'I paid the phone bill and Maya paid the electricity bill.', False),
    ('I paid the phone bill and she paid the electricity bill.', 'Pay electricity bill', 'paid the electricity bill', False),
    ('I have booked the dentist appointment and charged the laptop.', 'Charge laptop', 'charged the laptop', True),
    ('I watered the plants and refilled my prescription.', 'Refill prescription', 'refilled my prescription', True),
])
def test_completed_clauses_keep_their_own_actor_and_certainty(text, value, evidence, expected):
    assert bool(completed_action(text, {'value':value,'evidence':evidence})) is expected


@pytest.mark.parametrize('padding', ['', ('I felt grateful for a quiet afternoon. ' * 25) + '\n\n'])
def test_long_entry_closes_both_independent_one_off_tasks_and_preserves_history(tmp_path, monkeypatch, padding):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path/'long-completions.sqlite3')
    setup = 'Book a dentist appointment sometime next week. Water the plants.'
    done = padding + JOURNAL
    def extract(text, known=None):
        fields = {'personal': [
            {'category':'task','value':'Book a dentist appointment sometime next week','evidence':'Book a dentist appointment sometime next week.'},
            {'category':'task','value':'Water the plants','evidence':'Water the plants.'},
        ]} if text == setup else {'completed_personal': [
            {'value':'Book dentist appointment','evidence':'booked my dentist appointment for next Thursday'},
            {'value':'Water plants','evidence':'watered the plants this afternoon'},
        ]}
        return inference.parse_extraction(json.dumps({'memories':[],**fields}), text)
    monkeypatch.setattr(main, 'extract_memories', extract)
    with TestClient(main.app) as client:
        def add(text):
            response = client.post('/api/notes',json={'text':text,'kind':'journal','entry_date':'2026-10-29'})
            assert response.status_code == 201
            main.app.state.worker.submit(lambda:None).result(timeout=3)
            return response.json()['id']
        add(setup)
        completion = add(done)
        items = client.get('/api/for-you?include_all_plans=true').json()['suggestions']
        assert len(items) == 2
        assert all(item['status']=='done' for item in items)
        assert all(item['completion']['note_id']==completion for item in items)
        assert len(client.get('/api/export').json()['personal_completions']) == 2
        client.delete(f'/api/notes/{completion}')
        assert all(item['status']=='open' for item in client.get('/api/for-you').json()['suggestions'])


def test_broad_quote_for_first_completion_cannot_cover_a_different_second_action():
    text = 'I booked my dentist appointment and watered the plants.'
    result = inference.parse_extraction(json.dumps({'memories':[], 'completed_personal':[
        {'value':'Book dentist appointment','evidence':text}]}), text)
    with pytest.raises(inference.ExtractionValidationError, match='watered the plants'):
        inference.validate_meaning(result, text)


def test_omitted_completion_in_mixed_sentence_receives_targeted_retry(monkeypatch):
    import httpx
    text = 'I booked my dentist appointment for next Thursday, but I still need to renew my passport.'
    calls = []
    real_client = httpx.Client
    def respond(request):
        calls.append(json.loads(request.content))
        payload = {'memories':[], 'personal':[
            {'category':'task','value':'Renew my passport','evidence':'I still need to renew my passport'}]}
        if len(calls)>1:
            payload['completed_personal'] = [{'value':'Book dentist appointment',
                                            'evidence':'booked my dentist appointment for next Thursday'}]
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload)}}]})
    monkeypatch.setenv('NEBIUS_API_KEY','test')
    monkeypatch.setattr(inference.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(respond),**kw))
    result = inference.extract_memories(text)
    assert len(result.completed_personal) == 1
    assert len(result.personal) == 1
    assert len(calls) == 2
    assert len(json.loads(calls[0]['messages'][1]['content'])['completion_hints']) == 1
    assert 'completed author action was omitted' in calls[1]['messages'][0]['content']
