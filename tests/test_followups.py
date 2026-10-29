import json

import httpx
import pytest

from backend import inference
from backend.followup_grounding import followup_hints


TRIP = ('I also met someone new, Stewy, who works with Maya. He loves hiking and is planning '
        'a trip to Vermont next month. I’d like to ask how the trip went afterward.')
BOOK = ('Maya mentioned a book I might enjoy, but I can’t remember its title. '
        'I should ask her about it when we next talk.')


def memory(person, value, evidence, category='plan'):
    return dict(person=person, category=category, value=value, evidence=evidence)


def validate(text, memories):
    result = inference.parse_extraction(json.dumps({'memories': memories}), text)
    inference.validate_meaning(result, text)
    return result


def test_trip_event_cannot_cover_omitted_author_followup_even_with_broad_quote():
    with pytest.raises(inference.ExtractionValidationError, match='follow-up was omitted'):
        validate(TRIP, [memory('Stewy', 'Trip to Vermont next month', TRIP)])


def test_book_followup_requires_clear_subject_but_does_not_invent_title():
    quote = 'I should ask her about it when we next talk.'
    with pytest.raises(inference.ExtractionValidationError, match='lost its subject'):
        validate(BOOK, [memory('Maya', 'Ask her about it when we next talk', quote)])
    result = validate(BOOK, [memory('Maya', 'Ask Maya about the book she mentioned when we next talk', quote)])
    assert result.memories[0].evidence == quote


@pytest.mark.parametrize('text', [
    'Maybe I should ask Maya about the book.',
    'If I see Maya, I should ask about the book.',
    'I should not ask Maya about the book.',
    'I might ask Maya about the book.',
    'Should I ask Maya about the book?',
    'I should ask Maya about the book?',
    'Maya should ask Stewy about the trip.',
    'I asked Maya about the book.',
    'Stewy is planning a trip to Vermont next month.',
])
def test_uncertain_negated_completed_and_third_party_sentences_do_not_force_followups(text):
    assert followup_hints(text) == []


def test_topic_does_not_leak_between_paragraphs_or_force_ambiguous_antecedent():
    for text in [
        'Maya mentioned a book.\n\nI should ask about it.',
        'Maya mentioned a book and a class. I should ask about it.',
    ]:
        assert followup_hints(text)[0]['topic'] is None


def test_followup_can_be_personal_without_inventing_named_person():
    text = 'I need to follow up about my application tomorrow.'
    result = inference.parse_extraction(json.dumps({'memories': [], 'personal': [
        dict(category='task', value='Follow up about my application tomorrow', evidence=text)]}), text)
    inference.validate_meaning(result, text)


def test_same_paragraph_context_can_resolve_topic_but_not_supply_evidence():
    text = 'I should ask her about it when we next talk.'
    context = 'Maya mentioned a book I might enjoy.'
    result = inference.parse_extraction(json.dumps({'memories': [
        memory('Maya', 'Ask Maya about the book when we next talk', text)]}), text, context)
    inference.validate_meaning(result, text, context)
    result.memories[0].value = 'Ask her about it when we next talk'
    with pytest.raises(inference.ExtractionValidationError, match='lost its subject'):
        inference.validate_meaning(result, text, context)


def test_targeted_provider_retries_restore_missing_trip_followup_and_book_subject(monkeypatch):
    note = TRIP + '\n\n' + BOOK
    trip_quote = 'I’d like to ask how the trip went afterward.'
    book_quote = 'I should ask her about it when we next talk.'
    responses = [
        [memory('Stewy', 'Trip to Vermont next month', 'is planning a trip to Vermont next month'),
         memory('Maya', 'Ask her about it when we next talk', book_quote)],
        [memory('Stewy', 'Ask Stewy how the trip to Vermont went afterward', trip_quote),
         memory('Maya', 'Ask her about it when we next talk', book_quote)],
        [memory('Stewy', 'Ask Stewy how the trip to Vermont went afterward', trip_quote),
         memory('Maya', 'Ask Maya about the book she mentioned when we next talk', book_quote)],
    ]
    calls = []
    real_client = httpx.Client

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'memories': responses[len(calls)-1]})}}]})

    monkeypatch.setenv('NEBIUS_API_KEY', 'test')
    monkeypatch.setattr(inference.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    result = inference.extract_memories(note)
    assert len(calls) == 3
    assert 'follow-up was omitted' in calls[1]['messages'][0]['content']
    assert 'lost its subject' in calls[2]['messages'][0]['content']
    assert len(json.loads(calls[0]['messages'][1]['content'])['followup_hints']) == 2
    assert len(result.memories) == 2
    assert all(m.evidence in note for m in result.memories)
