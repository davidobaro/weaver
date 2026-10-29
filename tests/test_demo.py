import json
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from backend import main, inference
from backend.demo import DemoError, SessionEnded, current_workspace


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv('WEAVER_MODE', 'demo')
    monkeypatch.setenv('WEAVER_DEMO_WORKERS', '1')
    monkeypatch.setenv('NEBIUS_API_KEY', 'test')
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'personal.sqlite3')
    monkeypatch.setattr(main, 'extract_memories', lambda *args: inference.parse_extraction(json.dumps({'memories': [], 'personal': []}), args[0]))
    with TestClient(main.app) as client:
        manager_root = main.app.state.demo.root
        yield client, main.app.state.demo
    assert not main.DB_PATH.exists()
    assert not manager_root.exists()


def session(client):
    response = client.post('/api/session')
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def workspace(manager, headers):
    with manager.lease(headers['Authorization']) as ws:
        return ws


def wait_jobs(manager):
    futures = [f for ws in list(manager.sessions.values()) for f in list(ws.futures)]
    for future in futures:
        future.result(timeout=3)


def test_bootstrap_does_not_touch_personal_database_and_health_creates_no_session(demo):
    client, manager = demo
    assert client.get('/healthz').json() == {'status': 'ok'}
    assert client.get('/api/config').json()['mode'] == 'demo'
    assert not manager.sessions
    assert client.get('/api/state').status_code == 401
    assert client.get('/api/export').status_code == 401
    for token in ['../../personal.sqlite3', 'Bearer abc', 'Bearer ' + '../' * 15]:
        assert client.get('/api/state', headers={'Authorization': token}).status_code == 401
    assert not manager.sessions


def test_every_workspace_endpoint_is_guarded(demo):
    client, _ = demo
    for route in main.app.routes:
        path = getattr(route, 'path', '')
        if not path.startswith('/api/') or path in {'/api/config', '/api/session'}:
            continue
        path = path.replace('{note_id}', '1').replace('{memory_id}', '1').replace('{person_id}', '1').replace('{suggestion_id}', 'anything').replace('{merge_id}', 'anything').replace('{device}', str(uuid4())).replace('{token}', str(uuid4()))
        for method in route.methods - {'HEAD', 'OPTIONS'}:
            assert client.request(method, path, json={}).status_code == 401, (method, path)


def test_two_workspaces_with_same_ids_are_isolated_across_state_sources_and_export(demo):
    client, manager = demo
    a, b = session(client), session(client)
    for headers, text in [(a, 'Maya loves pottery.'), (b, 'Leila loves jazz.')]:
        result = client.post('/api/notes', headers=headers, json={'text': text})
        assert result.status_code == 201, result.text
        assert result.json()['id'] == 1
        wait_jobs(manager)
    assert client.get('/api/notes/1', headers=a).json()['text'] == 'Maya loves pottery.'
    assert client.get('/api/notes/1', headers=b).json()['text'] == 'Leila loves jazz.'
    assert 'Leila' not in client.get('/api/export', headers=a).text
    assert 'Maya' not in client.get('/api/export', headers=b).text
    assert client.get('/api/search?q=Maya', headers=b).json()['total'] == 0
    assert client.delete('/api/notes/1', headers=a).status_code == 204
    assert client.get('/api/state', headers=a).json()['notes'] == []
    assert len(client.get('/api/state', headers=b).json()['notes']) == 1
    assert client.get('/api/state', headers=b).headers['cache-control'] == 'no-store'


def test_reset_while_worker_runs_blocks_publication_and_waits_for_job_lease(demo, monkeypatch):
    client, manager = demo
    headers = session(client)
    ws = workspace(manager, headers)
    started, finish = threading.Event(), threading.Event()
    def extract(text, *args):
        started.set()
        assert finish.wait(timeout=3)
        return inference.parse_extraction('{"memories": []}', text)
    monkeypatch.setattr(main, 'extract_memories', extract)
    try:
        assert client.post('/api/notes', headers=headers, json={'text': 'A quiet day.'}).status_code == 201
        assert started.wait(timeout=3)
        assert client.delete('/api/session', headers=headers).status_code == 204
        assert ws.path.exists()  # still leased by the running worker
        assert client.get('/api/state', headers=headers).status_code == 401
        fresh = session(client)
        assert client.get('/api/state', headers=fresh).json()['notes'] == []
    finally:
        futures = list(ws.futures)
        finish.set()
        for future in futures:
            future.result(timeout=3)
    deadline = time.monotonic() + 3
    while ws.path.parent.exists() and time.monotonic() < deadline:
        time.sleep(.005)
    assert not ws.path.parent.exists()
    assert not manager.admissions


def test_get_polling_and_notification_polling_do_not_extend_expiry(demo):
    client, manager = demo
    headers = session(client)
    ws = workspace(manager, headers)
    now = [manager.now()]
    manager.now = lambda: now[0]
    now[0] += manager.idle - 1
    assert client.get('/api/state', headers=headers).status_code == 200
    assert client.post(f'/api/notifications/{uuid4()}/claim', headers=headers).status_code == 200
    now[0] += 2
    assert client.get('/api/state', headers=headers).status_code == 401
    assert not ws.path.exists()


def test_explicit_activity_extends_idle_but_not_absolute_lifetime(demo):
    client, manager = demo
    headers = session(client)
    ws = workspace(manager, headers)
    now = [manager.now()]
    manager.now = lambda: now[0]
    now[0] += manager.idle - 1
    assert client.post('/api/session/activity', headers=headers).status_code == 200
    now[0] += 2
    assert client.get('/api/state', headers=headers).status_code == 200
    now[0] = ws.created + manager.lifetime
    assert client.get('/api/state', headers=headers).status_code == 401


def test_rejected_capacity_preserves_no_partial_entry_and_validation_releases_slot(demo):
    client, manager = demo
    headers = session(client)
    assert client.post('/api/notes', headers=headers, json={}).status_code == 422
    assert not manager.admissions
    manager.capacity = 0
    assert client.post('/api/notes', headers=headers, json={'text': 'My draft'}).status_code == 503
    assert client.get('/api/state', headers=headers).json()['notes'] == []
    manager.capacity = 6
    manager.max_entries = 0
    assert client.post('/api/notes', headers=headers, json={'text': 'My draft'}).status_code == 429
    assert not manager.admissions


def test_one_outstanding_job_and_session_budget_include_manual_extract(demo, monkeypatch):
    client, manager = demo
    headers = session(client)
    manager.max_starts = 1
    assert client.post('/api/notes', headers=headers, json={'text': 'A quiet day.', 'automatic': False}).status_code == 201
    assert client.post('/api/notes/1/extract', headers=headers).status_code == 429
    assert client.post('/api/notes', headers=headers, json={'text': 'Another thought.'}).status_code == 429
    assert not manager.admissions


def test_provider_call_budget_counts_retries_and_stops_without_extra_http_call(demo, monkeypatch):
    client, manager = demo
    headers = session(client)
    manager.max_calls = 1
    calls = []
    real_client = httpx.Client
    def respond(request):
        calls.append(request)
        return httpx.Response(503)
    monkeypatch.setattr(inference.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(inference.time, 'sleep', lambda _: None)
    monkeypatch.setattr(main, 'extract_memories', inference.extract_memories)
    assert client.post('/api/notes', headers=headers, json={'text': 'A quiet day.'}).status_code == 201
    wait_jobs(manager)
    assert len(calls) == 1
    note = client.get('/api/state', headers=headers).json()['notes'][0]
    assert note['status'] == 'failed'
    assert 'allowance' in note['error']


def test_network_session_limit_survives_reset_and_body_size_is_bounded(demo):
    client, manager = demo
    manager.rate('sessions', manager.client_key('testclient'), 100)  # consumes one start
    headers = session(client)
    assert client.post('/api/notes', headers=headers, content='x' * 65537).status_code == 413
    assert not manager.admissions
    assert client.delete('/api/session', headers=headers).status_code == 204
    with pytest.raises(SessionEnded):
        with manager.lease(headers['Authorization']):
            pass


def test_host_and_origin_controls_remain_in_demo(demo, monkeypatch):
    client, _ = demo
    monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME', 'weaver-demo.onrender.com')
    assert client.get('/healthz', headers={'Host': 'weaver-demo.onrender.com'}).status_code == 200
    assert client.get('/healthz', headers={'Host': 'evil.example'}).status_code == 403
    assert client.post('/api/session', headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/session', headers={'Origin': 'http://127.0.0.1:8001', 'Host': '127.0.0.1:8001'}).status_code == 201
    assert client.post('/api/session', headers={'Origin': 'https://weaver-demo.onrender.com', 'Host': 'weaver-demo.onrender.com'}).status_code == 201


def test_reset_cancels_waiting_work_without_starting_a_provider_call(demo, monkeypatch):
    client, manager = demo
    a, b = session(client), session(client)
    ws_a, ws_b = workspace(manager, a), workspace(manager, b)
    started, finish = threading.Event(), threading.Event()
    calls = []
    def extract(text, *args):
        calls.append(text)
        started.set()
        assert finish.wait(timeout=3)
        return inference.parse_extraction('{"memories": []}', text)
    monkeypatch.setattr(main, 'extract_memories', extract)
    try:
        assert client.post('/api/notes', headers=a, json={'text': 'First visitor.'}).status_code == 201
        assert started.wait(timeout=3)
        assert client.post('/api/notes', headers=b, json={'text': 'Second visitor.'}).status_code == 201
        queued = next(iter(ws_b.futures))
        assert not queued.running()
        assert client.delete('/api/session', headers=b).status_code == 204
        assert queued.cancelled()
        assert not ws_b.path.parent.exists()
    finally:
        running = list(ws_a.futures)
        finish.set()
        for future in running:
            future.result(timeout=3)
    assert calls == ['First visitor.']


def test_session_reset_cannot_bypass_network_creation_limit(demo, monkeypatch):
    client, manager = demo
    monkeypatch.setenv('WEAVER_DEMO_SESSIONS_PER_HOUR', '2')
    for _ in range(2):
        headers = session(client)
        assert client.delete('/api/session', headers=headers).status_code == 204
    assert client.post('/api/session').status_code == 429
    assert not manager.sessions


def test_people_memory_task_timing_and_notification_mutations_stay_in_workspace(demo):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    client, manager = demo
    a, b = session(client), session(client)
    today = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    for headers, name in [(a, 'Maya'), (b, 'Leila')]:
        with main.database(workspace(manager, headers)) as db:
            db.execute("INSERT INTO notes(id,text,status,entry_date) VALUES (1,?,'organized',?)",(f'{name} loves pottery. I need to pay the electricity bill today.', today))
            main.archive_entry(db,main.note_or_404(db,1))
            db.execute('INSERT INTO people(id,name,name_key) VALUES (1,?,?)',(name,name.casefold()))
            db.execute("INSERT INTO memories(id,note_id,person_id,category,value,evidence) VALUES (1,1,1,'interest','Loves pottery',?)",(f'{name} loves pottery.',))
            db.execute("INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (1,1,'task','Pay the electricity bill today','I need to pay the electricity bill today.')")
    assert client.post('/api/people/1/aliases', headers=a, json={'name': 'May'}).status_code == 201
    assert client.patch('/api/memories/1', headers=a, json={'person':'Maya','category':'interest','value':'Loves jazz'}).status_code == 200
    people_b = client.get('/api/state',headers=b).json()['people']
    assert people_b[0]['name'] == 'Leila'
    assert people_b[0]['aliases'] == []
    assert people_b[0]['memories'][0]['value'] == 'Loves pottery'
    suggestion_a = client.get('/api/for-you',headers=a).json()['suggestions'][0]
    assert client.patch('/api/for-you/'+suggestion_a['id'],headers=a,json={'status':'done'}).status_code == 200
    assert client.get('/api/for-you',headers=b).json()['suggestions'][0]['status'] == 'open'
    device = str(uuid4())
    assert client.post(f'/api/notifications/{device}/claim',headers=b).json()['count'] == 1
    with main.database(workspace(manager,a)) as db:
        assert db.execute('SELECT COUNT(*) FROM notification_receipts').fetchone()[0] == 0


def test_concurrent_submissions_admit_only_one_job_for_a_session(demo, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    client, manager = demo
    headers = session(client)
    finish = threading.Event()
    def extract(text, *args):
        assert finish.wait(timeout=3)
        return inference.parse_extraction('{"memories": []}', text)
    monkeypatch.setattr(main,'extract_memories',extract)
    try:
        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [callers.submit(client.post,'/api/notes',headers=headers,json={'text': f'Thought {index}'}) for index in range(2)]
            statuses = sorted(f.result(timeout=3).status_code for f in futures)
        assert statuses == [201,429]
        assert len(client.get('/api/state',headers=headers).json()['notes']) == 1
    finally:
        finish.set()
        wait_jobs(manager)
