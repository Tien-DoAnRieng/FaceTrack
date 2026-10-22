import json
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.security import hash_password, verify_password
from app.validation import iso

PASSWORD = 'MyPassword123!'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('DB_TYPE', 'sqlite')
    monkeypatch.setenv('DATABASE_PATH', ':memory:')
    monkeypatch.setenv('JWT_SECRET', 'test-secret-at-least-thirty-two-bytes-long')
    monkeypatch.setenv('AI_SERVICE_KEY', 'test-ai-key-at-least-thirty-two-characters')
    with TestClient(create_app()) as client:
        yield client


def login(client, name='teacher'):
    result = client.post('/auth/login', json={'username': name, 'password': PASSWORD})
    assert result.status_code == 200
    return {'Authorization': 'Bearer ' + result.json()['accessToken']}


@pytest.fixture
def setup(client):
    assert client.post('/auth/register', json={'username': 'teacher', 'password': PASSWORD, 'fullName': 'Teacher'}).status_code == 201
    headers = login(client)
    s = client.post('/students', headers=headers, json={'studentCode': 'SV001', 'fullName': 'Sinh viên'}).json()
    r = client.post('/rooms', headers=headers, json={'roomCode': 'A101', 'name': 'Phòng học'}).json()
    return headers, s, r


def test_auth_and_existing_node_hash(client, setup):
    headers, _, _ = setup
    assert client.get('/auth/me', headers=headers).json()['role'] == 'teacher'
    assert client.get('/rooms').status_code == 401
    assert client.get('/rooms', headers={'Authorization': 'Bearer bad'}).status_code == 401
    assert client.post('/auth/login', json={'username': 'teacher', 'password': 'wrongpass'}).status_code == 401
    assert client.post('/auth/register', json={'username': 'TEACHER', 'password': PASSWORD, 'fullName': 'Other'}).status_code == 409
    encoded = subprocess.check_output(['node', '-e', "const c=require('crypto');const salt='0123456789abcdef0123456789abcdef';process.stdout.write('scrypt:'+salt+':'+c.scryptSync('MyPassword123!',salt,64).toString('hex'))"], text=True)
    assert verify_password(PASSWORD, encoded)
    client.app.state.db.execute('UPDATE users SET passwordHash=? WHERE username=?', [encoded, 'teacher'])
    login(client)
    python_hash = hash_password(PASSWORD)
    output = subprocess.check_output(['node', '-e', "const c=require('crypto');const [_,s,k]=process.argv[1].split(':');process.stdout.write(String(c.scryptSync('MyPassword123!',s,64).toString('hex')===k))", python_hash], text=True)
    assert output == 'true'


@pytest.mark.parametrize('body', [[], {}, {'username': 'user', 'password': PASSWORD, 'fullName': 'User', 'role': 'admin'}, {'username': 'x', 'password': PASSWORD, 'fullName': 'User'}])
def test_validation(client, body):
    result = client.post('/auth/register', json=body)
    assert result.status_code == 400
    assert result.json()['statusCode'] == 400


def provision(client, headers, student, name='student'):
    result = client.post('/auth/student-accounts', headers=headers, json={'username': name, 'password': PASSWORD, 'fullName': student['fullName'], 'studentId': student['id']})
    assert result.status_code == 201
    return login(client, name)


def test_roles_scope_and_event_retries(client, setup):
    headers, s, r = setup
    student_headers = provision(client, headers, s)
    assert client.get('/students', headers=student_headers).json() == [s]
    assert client.post('/rooms', headers=student_headers, json={}).status_code == 403
    event = {'studentId': s['id'], 'roomId': r['id'], 'direction': 'in', 'source': 'manual', 'eventKey': 'retry-1', 'occurredAt': '2026-10-21T07:00:00+07:00'}
    first = client.post('/room-events', headers=headers, json=event)
    assert first.status_code == 201
    assert first.json()['event']['occurredAt'] == '2026-10-21T00:00:00.000Z'
    retry = client.post('/room-events', headers=headers, json=event)
    assert retry.status_code == 200 and retry.json()['duplicate']
    assert client.post('/room-events', headers=headers, json={**event, 'direction': 'out'}).status_code == 409
    assert client.get('/room-events', headers=student_headers).json()['total'] == 1
    assert client.get('/room-events?studentId=999', headers=student_headers).status_code == 403
    assert client.get('/room-events?limit=101', headers=headers).status_code == 400
    assert client.post('/room-events', headers=headers, json={**event, 'occurredAt': '2026-02-30T00:00:00Z'}).status_code == 400
    client.app.state.db.execute("UPDATE users SET role='ai_service' WHERE username='teacher'")
    assert client.get('/room-events', headers=headers).status_code == 403
    assert client.post('/room-events', headers=headers, json=event).status_code == 403
    assert client.post('/rooms', headers=headers, json={}).status_code == 403


def test_camera_training_and_schedule(client, setup, monkeypatch):
    headers, s, r = setup
    student_headers = provision(client, headers, s)
    calls = []
    def ai(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'studentCode': s['studentCode'], 'similarity': 0.99} if url.endswith('/recognize') else {'ok': True})
    monkeypatch.setattr(httpx, 'post', ai)
    photo = 'data:image/jpeg;base64,abc'
    assert client.post('/camera/enroll', headers=headers, json={'studentId': s['id'], 'images': [photo] * 5}).status_code == 201
    assert client.get('/ai-training', headers=headers).json() == {'ok': True}
    assert client.post('/ai-training/jobs', headers=headers, json={}).status_code == 201
    assert client.post('/ai-training/activate', headers=headers, json={'version': None}).status_code == 201
    assert client.get('/ai-training', headers=student_headers).status_code == 403
    recognized = client.post('/camera/recognize', headers=student_headers, json={'image': photo}).json()
    ticket = recognized['ticket']
    assert calls[-1][1]['headers']['X-AI-Key'].startswith('test-ai-key')
    db = client.app.state.db
    now = datetime.now(timezone.utc)
    session_id = db.execute('INSERT INTO learning_sessions(subjectCode,subjectName,teacherName,roomId,startsAt,endsAt) VALUES(?,?,?,?,?,?)', ['PY', 'Python', 'Teacher', r['id'], iso(now - timedelta(minutes=5)), iso(now + timedelta(minutes=55))])
    db.execute('INSERT INTO session_students(sessionId,studentId) VALUES(?,?)', [session_id, s['id']])
    month = (now + timedelta(hours=7)).strftime('%Y-%m')
    schedule = client.get('/schedule?month=' + month, headers=student_headers).json()
    assert not schedule['items'][0]['canAttend']
    window_url = f'/teaching-sessions/{session_id}/attendance-window'
    assert client.post(f'/schedule/{session_id}/attendance', headers=student_headers, json={'ticket': ticket}).status_code == 403
    assert client.put(window_url, headers=student_headers, json={'state': 'open'}).status_code == 403
    assert client.put(window_url, headers=headers, json={'state': 'open'}).status_code == 200
    assert client.get('/schedule?month=' + month, headers=student_headers).json()['items'][0]['canAttend']
    assert client.put(window_url, headers=headers, json={'state': 'closed'}).status_code == 200
    assert not client.get('/schedule?month=' + month, headers=student_headers).json()['items'][0]['canAttend']
    assert client.post(f'/schedule/{session_id}/attendance', headers=student_headers, json={'ticket': ticket}).status_code == 403
    assert client.put(window_url, headers=headers, json={'state': 'open'}).status_code == 200
    url = f'/schedule/{session_id}/attendance'
    assert client.post(url, headers=student_headers, json={'ticket': ticket + 'bad'}).status_code == 400
    assert client.post(url, headers=student_headers, json={'ticket': ticket}).status_code == 201
    assert client.post(url, headers=student_headers, json={'ticket': 'expired-retry'}).json()['duplicate']
    assert client.get('/schedule?month=' + month, headers=student_headers).json()['items'][0]['status'] == 'present'
    assert client.post('/camera/events', headers=headers, json={'ticket': ticket, 'roomId': r['id'], 'direction': 'in', 'eventKey': 'wrong-owner'}).status_code == 400
    staff_ticket = client.post('/camera/recognize', headers=headers, json={'image': photo}).json()['ticket']
    event = {'ticket': staff_ticket, 'roomId': r['id'], 'direction': 'in', 'eventKey': 'camera-1'}
    assert client.post('/camera/events', headers=headers, json=event).status_code == 201
    assert client.post('/camera/events', headers=headers, json=event).status_code == 200
    assert client.get('/docs').status_code == 200
    assert '/schedule/{id}/attendance' in client.get('/openapi.json').json()['paths']


def test_ai_unavailable(client, setup, monkeypatch):
    headers, _, _ = setup
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx, 'post', unavailable)
    assert client.get('/ai-training', headers=headers).status_code == 503


def test_cors(client):
    result = client.options('/auth/login', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type'})
    assert result.status_code == 200
    assert result.headers['access-control-allow-origin'] == 'http://localhost:5173'


def test_existing_database_and_node_jwt(tmp_path, monkeypatch):
    path = tmp_path / 'existing.sqlite'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE COLLATE NOCASE,fullName TEXT,passwordHash TEXT)')
    connection.execute('INSERT INTO users VALUES(?,?,?,?)', [42, 'legacy_user', 'Existing User', hash_password(PASSWORD)])
    connection.commit()
    connection.close()
    secret = 'existing-node-jwt-secret-at-least-32-bytes'
    monkeypatch.setenv('DB_TYPE', 'sqlite')
    monkeypatch.setenv('DATABASE_PATH', str(path))
    monkeypatch.setenv('JWT_SECRET', secret)
    node_script = "const c=require('crypto');const b=x=>Buffer.from(JSON.stringify(x)).toString('base64url');const body=b({alg:'HS256',typ:'JWT'})+'.'+b({sub:'42',exp:Math.floor(Date.now()/1000)+3600,iss:'faceid-api',aud:'faceid-clients'});process.stdout.write(body+'.'+c.createHmac('sha256',process.argv[1]).update(body).digest('base64url'))"
    token = subprocess.check_output(['node', '-e', node_script, secret], text=True)
    with TestClient(create_app()) as client:
        assert login(client, 'legacy_user')
        result = client.get('/auth/me', headers={'Authorization': 'Bearer ' + token})
        assert result.status_code == 200
        assert result.json() == {'id': 42, 'username': 'legacy_user', 'fullName': 'Existing User', 'role': 'student'}
    with TestClient(create_app()) as client:
        assert client.app.state.db.all('SELECT COUNT(*) AS total FROM users')[0]['total'] == 1
