from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.local_ai import LocalAI
from app.main import create_app


def test_direct_ai_route_keeps_auth_and_ticket(monkeypatch):
    monkeypatch.setenv('DB_TYPE', 'sqlite')
    monkeypatch.setenv('DATABASE_PATH', ':memory:')
    monkeypatch.setenv('JWT_SECRET', 'unified-test-secret-at-least-32-bytes')
    handler = Mock(return_value={'studentCode': 'SV001', 'similarity': 0.95})
    with TestClient(create_app(ai_handler=handler)) as client:
        client.post('/auth/register', json={'username': 'teacher', 'password': 'password123', 'fullName': 'Teacher'})
        token = client.post('/auth/login', json={'username': 'teacher', 'password': 'password123'}).json()['accessToken']
        headers = {'Authorization': 'Bearer ' + token}
        client.post('/students', headers=headers, json={'studentCode': 'SV001', 'fullName': 'Student'})
        body = {'image': 'data:image/jpeg;base64,AAAA'}
        assert client.post('/camera/recognize', json=body).status_code == 401
        handler.assert_not_called()
        response = client.post('/camera/recognize', headers=headers, json=body)
        assert response.status_code == 201
        assert response.json()['student']['studentCode'] == 'SV001'
        assert response.json()['ticket']
        handler.assert_called_once_with('/recognize', body)
        handler.side_effect = ValueError('Show exactly one face')
        assert client.post('/camera/recognize', headers=headers, json=body).status_code == 400
        handler.side_effect = RuntimeError('model unavailable')
        assert client.post('/camera/recognize', headers=headers, json=body).status_code == 503


def test_local_ai_reuses_engine(monkeypatch):
    import ai.web_server
    engine = Mock()
    constructor = Mock(return_value=engine)
    monkeypatch.setattr(ai.web_server, 'WebEngine', constructor)
    handler = LocalAI()
    handler('/training/status', {})
    handler('/training/status', {})
    constructor.assert_called_once_with()
    assert engine.handle.call_count == 2


def test_mounted_ui_and_api(monkeypatch):
    monkeypatch.setenv('DB_TYPE', 'sqlite')
    monkeypatch.setenv('DATABASE_PATH', ':memory:')
    monkeypatch.setenv('JWT_SECRET', 'unified-test-secret-at-least-32-bytes')
    from server import create_application
    with TestClient(create_application()) as client:
        assert client.get('/ui/').status_code == 200
        assert client.get('/docs').status_code == 200
        assert client.get('/students').status_code == 401
        assert client.get('/ui/camera', follow_redirects=False).headers['location'] == '/login'
        assert client.get('/_pages/camera/').status_code == 401
        assert client.get('/login').status_code == 200
        client.post('/auth/register', json={'username': 'teacher', 'password': 'password123', 'fullName': 'Teacher'})
        failed = client.post('/login', data={'username': 'teacher', 'password': 'wrong'})
        assert 'faceid_session' not in failed.cookies
        response = client.post('/login', data={'username': 'teacher', 'password': 'password123'}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'] == '/ui/camera'
        assert 'HttpOnly' in response.headers['set-cookie']
        for name in ('camera', 'enroll', 'students', 'rooms', 'accounts', 'events', 'training'):
            response = client.get('/ui/' + name)
            assert response.status_code == 200
            assert f'src="/_pages/{name}/"' in response.text
            assert client.get(f'/_pages/{name}/').status_code == 200
        for role in ('admin', 'teacher'):
            client.app.state.db.execute('UPDATE users SET role=? WHERE username=?', [role, 'teacher'])
            assert '/ui/schedule' not in client.get('/ui/camera').text
            assert client.get('/ui/schedule').status_code == 403
            assert client.get('/_pages/schedule/').status_code == 403
        assert client.post('/logout', headers={'Origin': 'https://untrusted.example'}, follow_redirects=False).status_code == 403
        # Role changes take effect without signing in again.
        client.app.state.db.execute("UPDATE users SET role='student' WHERE username='teacher'")
        assert client.get('/ui/students').status_code == 403
        assert client.get('/_pages/students/').status_code == 403
        assert client.get('/ui/schedule').status_code == 200
        assert '/ui/students' not in client.get('/ui/schedule').text
        assert client.get('/ui/', follow_redirects=False).headers['location'] == '/ui/schedule'
        client.post('/logout', follow_redirects=False)
        assert client.get('/ui/schedule', follow_redirects=False).headers['location'] == '/login'
        assert client.get('/_pages/schedule/').status_code == 401
