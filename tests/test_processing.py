import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import inference, main


def memory(note, value='Enjoys hiking'):
    return {'person': 'Maya', 'category': 'interest', 'value': value, 'evidence': note.strip()}


@pytest.fixture
def provider(monkeypatch):
    real_client = httpx.Client
    calls = []

    def install(handler):
        def respond(request):
            payload = json.loads(request.content)
            calls.append(payload)
            return handler(payload)
        monkeypatch.setattr(inference.httpx, 'Client', lambda **kwargs: real_client(
            transport=httpx.MockTransport(respond), **kwargs))
        return calls

    monkeypatch.setenv('NEBIUS_API_KEY', 'test-key')
    monkeypatch.setenv('NEBIUS_MODEL', 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B')
    monkeypatch.setattr(inference.time, 'sleep', lambda delay: None)
    return install


def answer(memories=(), reason='stop'):
    return httpx.Response(200, json={'choices': [{'finish_reason': reason,
        'message': {'content': json.dumps({'memories': list(memories)})}}]})


@pytest.mark.parametrize('text', [
    ('Maya enjoys hiking.\n\n' * 200),
    ('A sentence. Another thought! A question? ' * 100),
    'x' * 5000,
    ('🌱\n  \nquiet day  ' * 300),
])
def test_sections_preserve_every_source_character_and_are_bounded(text):
    parts = inference.split_note(text)
    assert ''.join(parts) == text
    assert all(0 < len(part) <= 1200 for part in parts)


def test_sections_are_combined_and_duplicate_facts_not_republished(provider):
    def respond(payload):
        note = json.loads(payload['messages'][1]['content'])['new_note']
        return answer([memory(note)])
    calls = provider(respond)
    note = 'Maya enjoys hiking.\n\n' * 100
    result = inference.extract_memories(note)
    assert len(calls) > 1
    assert len(result.memories) == 1
    assert result.memories[0].evidence in note
    assert all(call['chat_template_kwargs'] == {'enable_thinking': True} for call in calls)


def test_unfamiliar_lowercase_name_becomes_source_backed_profile(tmp_path, monkeypatch, provider):
    """Exercise provider parsing, automatic publication, and the People profile."""
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'new-name.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', inference.extract_memories)
    calls = provider(lambda payload: answer([{
        'person': 'stewy', 'category': 'context', 'value': 'Moved in',
        'evidence': 'stewy moved in',
    }]))
    with TestClient(main.app) as client:
        note = client.post('/api/notes', json={'text': 'stewy moved in'}).json()
        main.app.state.worker.submit(lambda: None).result(timeout=3)
        state = client.get('/api/state').json()
        assert state['notes'][0]['status'] == 'organized'
        assert len(state['people']) == 1
        person = state['people'][0]
        assert person['name'] == 'stewy'
        assert person['memories'][0]['note_id'] == note['id']
        assert person['memories'][0]['evidence'] == 'stewy moved in'
        assert person['about']['facts'][0]['value'] == 'Moved in'
        assert json.loads(calls[0]['messages'][1]['content'])['known_people'] == []


@pytest.mark.parametrize('unused', [
    {'relationships': []}, {'replaces_id': None, 'duplicate_of': None},
    {'metadata': {}},
])
def test_empty_provider_envelope_fields_do_not_fail_valid_extraction(unused):
    text = 'need to get peppers from Marc'
    candidate = {'person': 'Marc', 'category': 'plan', 'value': text, 'evidence': text}
    result = inference.parse_extraction(json.dumps({'memories': [candidate], **unused}), text)
    assert result.memories[0].person == 'Marc'
    assert result.memories[0].evidence == text


@pytest.mark.parametrize('extra', [
    {'relationships': [{'person': 'Marc'}]}, {'replaces_id': 3}, {'metadata': {'fact': 'extra'}},
])
def test_populated_unsupported_fields_are_rejected_instead_of_losing_facts(extra):
    with pytest.raises(inference.ExtractionValidationError, match='invalid response'):
        inference.parse_extraction(json.dumps({'memories': [], **extra}), 'Marc moved in')


def test_named_errand_with_empty_envelope_fields_is_published(tmp_path, monkeypatch, provider):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'errand.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', inference.extract_memories)
    text = 'need to get peppers from Marc'
    def respond(payload):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'memories': [{'person': 'Marc', 'category': 'plan',
                'value': text, 'evidence': text}], 'personal': [], 'relationships': [],
                'replaces_id': None, 'duplicate_of': None})}}]})
    provider(respond)
    with TestClient(main.app) as client:
        note = client.post('/api/notes', json={'text': text}).json()
        main.app.state.worker.submit(lambda: None).result(timeout=3)
        state = client.get('/api/state').json()
        assert state['notes'][0]['status'] == 'organized'
        person = state['people'][0]
        assert person['name'] == 'Marc'
        assert person['memories'][0]['note_id'] == note['id']
        assert person['memories'][0]['category'] == 'plan'
        with main.database() as db:
            assert db.execute('SELECT COUNT(*) FROM personal_reminders').fetchone()[0] == 0


def test_response_limit_splits_only_failing_section_and_retains_other_facts(provider):
    def respond(payload):
        note = json.loads(payload['messages'][1]['content'])['new_note']
        if len(note) > 600:
            return answer(reason='length')
        return answer([memory(note, 'Maya ' + note.strip()[:20])])
    calls = provider(respond)
    note = ('Maya likes hiking. ' * 30) + '\n\n' + ('Maya likes ceramics. ' * 30)
    result = inference.extract_memories(note)
    assert len(calls) > 2
    assert len(result.memories) >= 2
    assert all(item.evidence in note for item in result.memories)


@pytest.mark.parametrize('failure', [429, 503, 'timeout'])
def test_transient_failure_retries_automatically(provider, failure):
    attempts = 0
    def respond(payload):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            if failure == 'timeout':
                raise httpx.ReadTimeout('interrupted')
            return httpx.Response(failure)
        return answer([memory('Maya enjoys hiking.')])
    provider(respond)
    assert len(inference.extract_memories('Maya enjoys hiking.').memories) == 1
    assert attempts == 3


def test_authentication_error_is_not_retried(provider):
    calls = provider(lambda payload: httpx.Response(401))
    with pytest.raises(inference.InferenceError, match='rejected the API key'):
        inference.extract_memories('Maya enjoys hiking.')
    assert len(calls) == 1


def test_persistent_limits_stop_after_bounded_splitting(provider):
    calls = provider(lambda payload: answer(reason='length'))
    with pytest.raises(inference.ResponseLimitError):
        inference.extract_memories('Maya enjoys hiking. ' * 50)
    assert len(calls) <= 3


def test_source_validation_is_enforced_for_each_section(provider):
    provider(lambda payload: answer([memory('Maya enjoys swimming.')]))
    with pytest.raises(inference.InferenceError, match='matching source quotes'):
        inference.extract_memories('Maya enjoys hiking.')


def test_failed_later_section_publishes_nothing_and_retry_saves_all(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'sections.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', inference.extract_memories)
    fail = True
    sections = []
    def extract(note, known, identity_context=''):
        sections.append(note)
        if 'ceramics' in note and fail:
            raise inference.InferenceError('Temporary interruption; writing is saved.')
        return inference.parse_extraction(json.dumps({'memories': [memory(note,
            'Enjoys ceramics' if 'ceramics' in note else 'Enjoys hiking')]}), note)
    monkeypatch.setattr(inference, '_request_chunk', extract)
    text = (('Maya enjoys hiking. ' * 45) + '\n\n' + ('Maya enjoys ceramics. ' * 45)).strip()
    with TestClient(main.app) as client:
        created = client.post('/api/notes', json={'text': text, 'kind': 'journal'}).json()
        main.app.state.worker.submit(lambda: None).result(timeout=3)
        state = client.get('/api/state').json()
        assert state['notes'][0]['status'] == 'failed'
        assert state['notes'][0]['text'] == text
        assert state['people'] == []
        assert len(sections) >= 2
        fail = False
        client.post(f"/api/notes/{created['id']}/organize")
        main.app.state.worker.submit(lambda: None).result(timeout=3)
        state = client.get('/api/state').json()
        assert state['notes'][0]['status'] == 'organized'
        assert {m['value'] for m in state['people'][0]['memories']} == {'Enjoys hiking', 'Enjoys ceramics'}


def test_invalid_evidence_gets_a_corrective_retry(provider):
    attempts = 0
    def respond(payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return answer([memory('Maya enjoys swimming.')])
        assert 'previous attempt failed validation' in payload['messages'][0]['content']
        assert all('memories' not in person for person in json.loads(payload['messages'][1]['content'])['known_people'])
        return answer([memory('Maya enjoys hiking.')])
    provider(respond)
    result = inference.extract_memories('Maya enjoys hiking.', [{'name': 'Maya', 'memories': [{'id': 1, 'value': 'Enjoys swimming'}]}])
    assert attempts == 2
    assert result.memories[0].evidence == 'Maya enjoys hiking.'


def test_transient_failures_eventually_stop(provider):
    calls = provider(lambda payload: httpx.Response(503))
    with pytest.raises(inference.InferenceError, match='writing is saved'):
        inference.extract_memories('Maya enjoys hiking.')
    assert len(calls) == 3


def test_more_than_40_distinct_facts_are_not_silently_dropped(monkeypatch):
    def extract(note, known, identity_context=''):
        return inference.parse_extraction(json.dumps({'memories': [memory(note,
            f'Detail {index} from {note.strip()[-25:]}') for index in range(30)]}), note)
    monkeypatch.setattr(inference, '_request_chunk', extract)
    note = ('Maya likes hiking. ' * 45) + '\n\n' + ('Maya likes ceramics. ' * 45)
    # Different source passages make distinct facts across the two sections.
    note = note.replace('Maya likes ceramics.', 'Maya enjoys ceramics.')
    with pytest.raises(inference.InferenceError, match='more than 40'):
        inference.extract_memories(note)


def test_only_people_mentioned_in_section_are_sent_as_context(provider):
    calls = provider(lambda payload: answer())
    inference.extract_memories('Maya enjoys hiking.', [
        {'name': 'Maya', 'aliases': [], 'memories': []},
        {'name': 'Theo', 'aliases': [], 'memories': [{'value': 'A different fact'}]},
    ])
    context = json.loads(calls[0]['messages'][1]['content'])['known_people']
    assert [person['name'] for person in context] == ['Maya']
