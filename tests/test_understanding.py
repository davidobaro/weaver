"""Regression coverage for the real-model understanding audit."""
import json

import httpx
import pytest

from backend import inference


def parsed(note, **fields):
    return inference.parse_extraction(json.dumps({'memories': [], **fields}), note)


@pytest.mark.parametrize('source,returned', [("D’Arcy", "D'Arcy"), ("O'Neil", 'O’Neil')])
def test_apostrophe_variant_uses_exact_source_name(source, returned):
    note = f'{source} loves jazz.'
    result = parsed(note, memories=[{'person': returned, 'category': 'interest',
        'value': 'Loves jazz', 'evidence': note}])
    assert result.memories[0].person == source
    assert result.memories[0].evidence == note


def test_typographic_quote_is_restored_to_exact_source_without_rewriting_words():
    result = parsed('D’Arcy loves jazz.', memories=[{'person': "D'Arcy", 'category': 'interest',
        'value': 'Loves jazz', 'evidence': "D'Arcy loves jazz"}])
    assert result.memories[0].evidence == 'D’Arcy loves jazz'
    assert result.memories[0].person == 'D’Arcy'
    with pytest.raises(inference.ExtractionValidationError, match='source quotes'):
        parsed('D’Arcy loves jazz.', memories=[{'person': "D'Arcy", 'category': 'interest',
            'value': 'Loves jazz', 'evidence': "D'Arcy enjoys jazz"}])


def test_apostrophe_matching_does_not_expand_or_change_identity():
    with pytest.raises(inference.ExtractionValidationError):
        parsed('Darcy loves jazz.', memories=[{'person': "D'Arcy", 'category': 'interest',
            'value': 'Loves jazz', 'evidence': 'Darcy loves jazz.'}])


def test_exact_duplicate_is_not_a_correction_or_assigned_to_another_person():
    note = 'Lina enjoys ceramics. Zavi enjoys ceramics.'
    result = parsed(note, memories=[{'person': name, 'category': 'interest',
        'value': 'Enjoys ceramics', 'evidence': f'{name} enjoys ceramics.', 'replaces_id': 9 if name == 'Lina' else None}
        for name in ('Lina', 'Zavi')])
    inference.normalize_duplicates(result, [{'name': 'Lina', 'memories': [
        {'id': 9, 'category': 'interest', 'value': 'Enjoys ceramics'}]}])
    assert result.memories[0].duplicate_of == 9
    assert result.memories[0].replaces_id is None
    assert result.memories[1].duplicate_of is None


def test_real_correction_is_not_normalized_into_a_duplicate():
    result = parsed('Lina corrected her birthday to April 18.', memories=[{
        'person': 'Lina', 'category': 'birthday', 'value': 'April 18',
        'evidence': 'Lina corrected her birthday to April 18.', 'replaces_id': 9}])
    inference.normalize_duplicates(result, [{'name': 'Lina', 'memories': [
        {'id': 9, 'category': 'birthday', 'value': 'April 8'}]}])
    assert result.memories[0].replaces_id == 9
    assert result.memories[0].duplicate_of is None


def test_explicit_birthday_correction_gets_its_single_known_predecessor():
    result = parsed('Lina: April 18, not April 8.', memories=[{
        'person': 'Lina', 'category': 'birthday', 'value': 'April 18', 'evidence': 'April 18, not April 8.'}])
    inference.normalize_duplicates(result, [{'name': 'Lina', 'memories': [
        {'id': 9, 'category': 'birthday', 'value': 'April 8'}]}])
    assert result.memories[0].replaces_id == 9
    assert result.memories[0].duplicate_of is None


@pytest.mark.parametrize('category', ['interest', 'plan'])
def test_ongoing_study_is_background_not_a_future_activity(category):
    result = parsed('Noor is studying architecture.', memories=[{'person': 'Noor',
        'category': category, 'value': 'Studying architecture', 'evidence': 'studying architecture'}])
    assert result.memories[0].category == 'context'
    result = parsed('Noor enjoys studying architecture.', memories=[{'person': 'Noor',
        'category': 'interest', 'value': 'Enjoys studying architecture', 'evidence': 'Noor enjoys studying architecture'}])
    assert result.memories[0].category == 'interest'


@pytest.mark.parametrize('value', ['Submit the form by Friday', 'Pay the rent tomorrow', 'Renew my license'])
def test_administrative_task_stays_a_task_even_with_timing(value):
    result = parsed(value, personal=[{'category': 'plan', 'value': value, 'evidence': value}])
    assert result.personal[0].category == 'task'


@pytest.mark.parametrize('text,value', [
    ('I will pay the phone bill tomorrow.', 'Pay the phone bill'),
    ('Submit the form by Friday.', 'Submit the form'),
])
def test_missing_deadline_is_restored_from_a_single_exact_source_intention(text, value):
    result = parsed(text, personal=[{'category': 'task', 'value': value, 'evidence': text}])
    assert result.personal[0].value == text.rstrip('.')
    inference.validate_meaning(result, text)


def test_short_quote_cannot_hide_deadline_or_borrow_one_from_another_sentence():
    text = 'Submit the application by Friday.'
    result = parsed(text, personal=[{'category': 'task', 'value': 'Submit the application',
        'evidence': 'Submit the application'}])
    with pytest.raises(inference.ExtractionValidationError, match='deadline'):
        inference.validate_meaning(result, text)
    text = 'Buy bread. Submit the application by Friday.'
    result = parsed(text, personal=[{'category': 'task', 'value': 'Buy bread', 'evidence': 'Buy bread'}])
    inference.validate_meaning(result, text)


def test_other_persons_plan_cannot_be_published_under_you():
    text = 'Zavi wants to go to the mall.'
    result = parsed(text, personal=[{'category': 'plan', 'value': text, 'evidence': text}])
    with pytest.raises(inference.ExtractionValidationError, match='named other person'):
        inference.validate_meaning(result, text)


def test_other_persons_completion_requires_a_corrected_answer():
    text = 'Zavi renewed their passport.'
    result = parsed(text, completed_personal=[{'value': 'Renew my passport', 'evidence': text}])
    with pytest.raises(inference.ExtractionValidationError, match='by the author'):
        inference.validate_meaning(result, text)


@pytest.mark.parametrize('text,values', [
    ('I mailed the letter.', ['Mail the letter']),
    ('I renewed my passport and paid the bill.', ['Renew my passport', 'Pay the bill']),
    ('I have just renewed my passport.', ['Renew my passport']),
])
def test_role_guard_accepts_author_actions_with_complete_coverage(text, values):
    result = parsed(text, completed_personal=[{'value': value, 'evidence': text} for value in values])
    inference.validate_meaning(result, text)


def test_role_validation_retries_with_specific_feedback(monkeypatch):
    real_client = httpx.Client
    calls = []
    text = 'Zavi renewed their passport.'
    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            output = {'memories': [], 'completed_personal': [{'value': 'Renew my passport', 'evidence': text}]}
        else:
            assert 'Specific validation failure' in payload['messages'][0]['content']
            assert 'by the author' in payload['messages'][0]['content']
            output = {'memories': [{'person': 'Zavi', 'category': 'context',
                'value': 'Renewed their passport', 'evidence': text}]}
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(output)}}]})
    monkeypatch.setenv('NEBIUS_API_KEY', 'test-key')
    monkeypatch.setattr(inference.httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(respond), **kwargs))
    result = inference.extract_memories(text)
    assert len(calls) == 2
    assert result.memories[0].person == 'Zavi'
    assert result.completed_personal == []


def test_unsupported_completed_activity_is_not_published_as_a_task_completion(monkeypatch):
    real_client = httpx.Client
    text = 'I went to a store today.'
    def respond(request):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'memories': [], 'completed_personal': [
                {'value': 'Go to a store', 'evidence': text}]})}}]})
    monkeypatch.setenv('NEBIUS_API_KEY', 'test-key')
    monkeypatch.setattr(inference.httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(respond), **kwargs))
    result = inference.extract_memories(text)
    assert result.memories == []
    assert result.personal == []
    assert result.completed_personal == []
