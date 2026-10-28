import json

import httpx
import pytest
from fastapi.testclient import TestClient
from backend import inference, main
from backend.profile_grounding import fact_hints, missing_facts

TEXT = ('I had coffee with stewy, who told me he’s learning photography. '
        'I promised I would send stewy a beginner’s guide.\n\n'
        'I met Leila at the café. She’s studying architecture and loves making pottery. '
        'Her birthday is November 12.')


def facts(complete=True):
    values = [
        ('stewy','commitment','Send a beginner’s guide','I promised I would send stewy a beginner’s guide.'),
        ('Leila','interest','Loves making pottery','loves making pottery'),
        ('Leila','birthday','Birthday November 12','Her birthday is November 12.'),
    ]
    if complete:
        values += [('stewy','interest','Learning photography','he’s learning photography'),
                   ('Leila','context','Studying architecture','She’s studying architecture')]
    return {'memories':[dict(zip(('person','category','value','evidence'), value)) for value in values]}


def test_source_profile_hints_cover_relative_pronouns_and_separate_studies():
    hints=fact_hints(TEXT)
    assert [(h['subject'],h['topic'],h['category']) for h in hints] == [
        ('he','photography','interest'),('She','architecture','context'),('She','making pottery','interest')]
    partial=inference.parse_extraction(json.dumps(facts(False)),TEXT)
    assert [(h['person'],h['category'],h['topic']) for h in missing_facts(partial,TEXT)] == [
        ('stewy','interest','photography'),('Leila','context','architecture')]
    complete=inference.parse_extraction(json.dumps(facts()),TEXT)
    inference.validate_meaning(complete,TEXT)


def test_broad_quote_and_pottery_interest_cannot_cover_missing_architecture_context():
    payload=facts(False)
    payload['memories'][1]['evidence']='She’s studying architecture and loves making pottery.'
    result=inference.parse_extraction(json.dumps(payload),TEXT)
    assert any(h['topic']=='architecture' for h in missing_facts(result,TEXT))


@pytest.mark.parametrize('text', [
    'I am studying architecture. We are learning photography.',
    'Maybe Leila is studying architecture.',
    'If Leila is studying architecture, I will ask her about it.',
    'Leila might be studying architecture.',
    'Leila is not studying architecture.',
    'Leila is studying architecture?',
    'I don’t think Leila is studying architecture.',
    'My brother is studying architecture.',
])
def test_uncertain_negated_or_author_studies_do_not_force_profile_facts(text):
    assert fact_hints(text)==[]


def test_ambiguous_or_unnamed_pronouns_do_not_force_person_attribution():
    for text in ['I met Maya and Noor. She’s studying architecture.',
                 'I met Maya and her sister. She’s studying architecture.']:
        people=['Maya','Noor'] if 'Noor' in text else ['Maya']
        result=inference.parse_extraction(json.dumps({'memories':[
            {'person':name,'category':'context','value':'Met today','evidence':text.split('.')[0]}
            for name in people]}),text)
        assert missing_facts(result,text)==[]


@pytest.fixture
def provider(monkeypatch):
    real=httpx.Client
    calls=[]
    monkeypatch.setenv('NEBIUS_API_KEY','test')
    def install(handler):
        def respond(request):
            payload=json.loads(request.content)
            calls.append(payload)
            response=handler(payload,len(calls))
            if isinstance(response,httpx.Response):
                return response
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(response)}}]})
        monkeypatch.setattr(inference.httpx,'Client',lambda **kwargs:real(transport=httpx.MockTransport(respond),**kwargs))
        return calls
    return install


def test_omissions_receive_targeted_retry_and_publish_both_people(tmp_path,monkeypatch,provider):
    calls=provider(lambda payload,attempt:facts(attempt>1))
    monkeypatch.setattr(main,'DB_PATH',tmp_path/'profiles.sqlite3')
    with TestClient(main.app) as client:
        response=client.post('/api/notes',json={'text':TEXT,'kind':'journal','entry_date':'2026-10-28'})
        assert response.status_code==201
        main.app.state.worker.submit(lambda:None).result(timeout=3)
        state=client.get('/api/state').json()
    assert state['notes'][0]['status']=='organized'
    by_name={p['name']:p for p in state['people']}
    assert any(m['category']=='interest' and 'photography' in m['value'] for m in by_name['stewy']['memories'])
    assert any(m['category']=='context' and 'architecture' in m['value'] for m in by_name['Leila']['memories'])
    assert any('photography' in fact['value'] and fact['evidence'] in TEXT for fact in by_name['stewy']['about']['facts'])
    assert any('architecture' in fact['value'] and fact['evidence'] in TEXT for fact in by_name['Leila']['about']['facts'])
    assert len(calls)==2
    assert calls[0]['messages'][1]['content']
    assert 'profile fact was omitted' in calls[1]['messages'][0]['content']


def test_section_identity_context_keeps_name_but_not_old_paragraphs(provider):
    text='I met Leila at the café. '+('We talked about the weather. '*44)+'She’s studying architecture.'
    def respond(payload,attempt):
        source=json.loads(payload['messages'][1]['content'])
        if 'Leila is studying architecture.' in source['new_note']:
            return {'memories':[{'person':'Leila','category':'context','value':'Studying architecture','evidence':'Leila is studying architecture.'}]}
        if 'She’s studying architecture.' not in source['new_note']:
            return {'memories':[]}
        assert 'Leila' in source['identity_context']
        return {'memories':[{'person':'Leila','category':'context','value':'Studying architecture','evidence':'She’s studying architecture.'}]}
    calls=provider(respond)
    result=inference.extract_memories(text)
    assert result.memories[0].person=='Leila'
    assert result.memories[0].evidence=='She’s studying architecture.'
    assert len(calls)>=2
    calls.clear()
    inference.extract_memories(('A quiet day. '*90)+'\n\nLeila is studying architecture.')
    source=json.loads(calls[-1]['messages'][1]['content'])
    assert not source['identity_context']


def test_identity_context_cannot_supply_source_quotes(provider):
    provider(lambda payload,attempt:{'memories':[{'person':'Leila','category':'interest','value':'Likes pottery','evidence':'Leila likes pottery.'}]})
    with pytest.raises(inference.ExtractionValidationError,match='matching source quotes'):
        inference._request_chunk('She’s learning photography.',[],'Leila likes pottery.')


def test_full_names_are_not_shortened_by_coverage_hints():
    text='I met Mary Jane. Mary Jane is studying architecture.'
    assert fact_hints(text)[0]['subject']=='Mary Jane'
    result=inference.parse_extraction(json.dumps({'memories':[{'person':'Mary Jane','category':'context','value':'Studying architecture','evidence':'Mary Jane is studying architecture.'}]}),text)
    inference.validate_meaning(result,text)


def test_omitted_second_actor_does_not_force_ambiguous_pronoun_to_first():
    text='I met Maya and Noor. She’s studying architecture.'
    result=inference.parse_extraction(json.dumps({'memories':[{'person':'Maya','category':'context','value':'Met today','evidence':'I met Maya and Noor.'}]}),text)
    assert missing_facts(result,text)==[]


def test_combined_coverage_recovers_only_missing_paragraph_without_duplicate_facts(provider):
    text='I met Leila at the café. '+('We talked about the weather. '*44)+'She’s studying architecture.'
    def respond(payload,attempt):
        source=json.loads(payload['messages'][1]['content'])
        assert len(source['new_note'])<=inference.CHUNK_CHARACTERS
        if 'I met Leila' in source['new_note']:
            return {'memories':[{'person':'Leila','category':'context','value':'Met at the café','evidence':'I met Leila at the café.'}]}
        if attempt>2:
            return {'memories':[{'person':'Leila','category':'context','value':'Studying architecture','evidence':'She’s studying architecture.'}]}
        return {'memories':[]}
    calls=provider(respond)
    result=inference.extract_memories(text)
    assert len(calls)==4
    assert len(result.memories)==2
    assert any(item.value=='Studying architecture' for item in result.memories)
    assert all(item.evidence in text for item in result.memories)


def test_response_limit_fallback_keeps_same_paragraph_name_for_pronoun(provider):
    text='I met Leila at the café. '+('We talked about the weather. '*24)+'She’s studying architecture.'
    def respond(payload,attempt):
        source=json.loads(payload['messages'][1]['content'])
        if len(source['new_note'])>500:
            return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':''}}]})
        if 'She’s studying architecture.' in source['new_note']:
            assert 'Leila' in source['identity_context']
            return {'memories':[{'person':'Leila','category':'context','value':'Studying architecture','evidence':'She’s studying architecture.'}]}
        return {'memories':[]}
    calls=provider(respond)
    result=inference.extract_memories(text)
    assert 2 < len(calls) <= 4
    assert all(len(json.loads(call['messages'][1]['content'])['new_note']) <= 500 for call in calls[1:])
    assert result.memories[0].person=='Leila'
    assert result.memories[0].value=='Studying architecture'


def test_studies_cannot_hide_the_coordinated_hobby():
    payload=facts(True)
    payload['memories']=[item for item in payload['memories'] if 'pottery' not in item['value']]
    result=inference.parse_extraction(json.dumps(payload),TEXT)
    missing=missing_facts(result,TEXT)
    assert [(h['person'],h['category'],h['topic']) for h in missing]==[('Leila','interest','making pottery')]
    assert missing[0]['quote']=='loves making pottery'
    with pytest.raises(inference.ExtractionValidationError,match='loves making pottery'):
        inference.validate_meaning(result,TEXT)
