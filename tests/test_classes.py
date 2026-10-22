from fastapi.testclient import TestClient
from app.main import create_app


def test_class_roster_populates_student_schedule(monkeypatch):
    monkeypatch.setenv('DB_TYPE', 'sqlite')
    monkeypatch.setenv('DATABASE_PATH', ':memory:')
    monkeypatch.setenv('JWT_SECRET', 'class-test-secret-at-least-thirty-two-bytes')
    with TestClient(create_app()) as client:
        password = 'password123'
        client.post('/auth/register', json={'username': 'teacher', 'password': password, 'fullName': 'Teacher'})
        def login(username):
            return {'Authorization': 'Bearer ' + client.post('/auth/login', json={'username': username, 'password': password}).json()['accessToken']}
        headers = login('teacher')
        def post(path, body):
            return client.post(path, headers=headers, json=body)
        student = post('/students', {'studentCode': 'S01', 'fullName': 'Student'}).json()
        client.post('/auth/student-accounts', headers=headers, json={'studentId': student['id'], 'username': 'student', 'password': password, 'fullName': 'Student'})
        student_headers = login('student')
        room = post('/rooms', {'roomCode': 'A01', 'name': 'Room'}).json()
        group = post('/classes', {'classCode': 'IT01', 'name': 'Class'}).json()
        assert client.get('/classes', headers=student_headers).status_code == 403
        assert post('/classes', {'classCode': 'IT01', 'name': 'Duplicate'}).status_code == 409
        body = {'classId': group['id'], 'roomId': room['id'], 'subjectCode': 'PY', 'subjectName': 'Python', 'teacherName': 'Teacher', 'startsAt': '2099-10-22T08:00:00+07:00', 'endsAt': '2099-10-22T10:00:00+07:00'}
        assert post('/teaching-sessions', body).status_code == 400
        url = f"/classes/{group['id']}/students"
        assert client.put(url, headers=headers, json={'studentIds': [student['id']]}).status_code == 200
        assert post('/teaching-sessions', body).status_code == 201
        assert post('/teaching-sessions', body).status_code == 409
        schedule = client.get('/schedule?month=2099-10', headers=student_headers).json()
        assert len(schedule['items']) == 1
        assert schedule['items'][0]['subjectName'] == 'Python'
        # Invalid edits roll back and keep the existing roster intact.
        assert client.put(url, headers=headers, json={'studentIds': [99999]}).status_code == 404
        assert len(client.get(url, headers=headers).json()) == 1
        assert client.put(url, headers=headers, json={'studentIds': []}).status_code == 200
        assert client.get('/schedule?month=2099-10', headers=student_headers).json()['items'] == []
        assert client.put(url, headers=headers, json={'studentIds': [student['id']]}).status_code == 200
        assert len(client.get('/schedule?month=2099-10', headers=student_headers).json()['items']) == 1
        assert client.post('/teaching-sessions', headers=student_headers, json=body).status_code == 403
