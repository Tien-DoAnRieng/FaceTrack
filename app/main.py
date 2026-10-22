import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException

from .database import Database, ROOT, duplicate
from .security import ROLES, ai_key, hash_password, sign_ticket, verify_password, verify_ticket
from .validation import choice, fail, integer, iso, obj, text, utc
from .attendance import attendance_state, eligible_time, install_attendance

load_dotenv(ROOT / '.env')
bearer = HTTPBearer(auto_error=False)


def create_app(ai_handler=None):
    @asynccontextmanager
    async def lifespan(app):
        secret = os.getenv('JWT_SECRET', '')
        if len(secret.encode()) < 32:
            raise ValueError('JWT_SECRET must contain at least 32 bytes; configure it in .env')
        app.state.secret = secret
        app.state.db = Database()
        app.state.dummy_hash = hash_password('unused-dummy-password')
        try:
            yield
        finally:
            app.state.db.close()

    app = FastAPI(title='FaceID Attendance API', version='1.0.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(','), allow_methods=['GET', 'POST', 'PATCH', 'PUT', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'])

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse({'message': error.detail, 'error': HTTPStatus(error.status_code).phrase, 'statusCode': error.status_code}, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({'message': 'Invalid or missing request data', 'error': 'Bad Request', 'statusCode': 400}, status_code=400)

    def db(request: Request):
        return request.app.state.db

    def one(database, sql, values=(), message='Resource does not exist'):
        rows = database.all(sql, values)
        if not rows:
            fail(message, 404)
        return rows[0]

    def account(database, user_id):
        rows = database.all('SELECT id,username,fullName,role FROM users WHERE id=?', [user_id])
        if not rows or rows[0]['role'] not in ROLES:
            fail('Account no longer exists or role is invalid', 401)
        user = rows[0]
        links = database.all('SELECT studentId FROM student_accounts WHERE userId=?', [user_id])
        if links:
            user['studentId'] = links[0]['studentId']
        return user

    def current(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer), database=Depends(db)):
        if not credentials:
            fail('Bearer token is required', 401)
        try:
            payload = jwt.decode(credentials.credentials, request.app.state.secret, algorithms=['HS256'], issuer='faceid-api', audience='faceid-clients')
            user_id = integer(int(payload['sub']), 'sub')
        except (jwt.InvalidTokenError, ValueError, KeyError, TypeError, HTTPException):
            fail('Invalid or expired token', 401)
        return account(database, user_id)

    def roles(*allowed):
        def check(user=Depends(current)):
            if user['role'] not in allowed:
                fail('Your role cannot access this operation', 403)
            return user
        return check

    teacher = roles('admin', 'teacher')
    writer = roles('admin', 'teacher', 'ai_service')

    def credentials(body, register=False):
        obj(body, ['username', 'password', 'fullName'] if register else ['username', 'password'])
        username = text(body.get('username'), 'username', 50).lower()
        if not re.fullmatch(r'[a-z0-9_]{3,50}', username):
            fail('username must contain 3-50 letters, digits or underscores')
        password = body.get('password')
        if not isinstance(password, str) or not 8 <= len(password) <= 128 or not password.strip():
            fail('password must contain 8-128 characters')
        return {'username': username, 'password': password, **({'fullName': text(body.get('fullName'), 'fullName')} if register else {})}

    def register(database, data, issuer=None, student_id=None):
        hashed = hash_password(data['password'])
        try:
            with database.transaction():
                database.all('SELECT id FROM account_creation_lock WHERE id=1' + (' FOR UPDATE' if database.dialect == 'mysql' else ''))
                if issuer:
                    fresh = account(database, issuer['id'])
                    if fresh['role'] not in ('admin', 'teacher'):
                        fail('Teacher permission is required', 403)
                if student_id is not None:
                    one(database, 'SELECT id FROM students WHERE id=?', [student_id], 'Student does not exist')
                    if database.all('SELECT userId FROM student_accounts WHERE studentId=?', [student_id]):
                        fail('Student already has an account', 409)
                user_id = database.execute('INSERT INTO users(username,fullName,passwordHash,role) VALUES(?,?,?,?)', [data['username'], data['fullName'], hashed, 'student' if issuer else 'teacher'])
                if student_id is not None:
                    database.execute('INSERT INTO student_accounts(userId,studentId) VALUES(?,?)', [user_id, student_id])
            return account(database, user_id)
        except Exception as error:
            if duplicate(error):
                fail('Username or student account already exists', 409)
            raise

    @app.get('/', response_class=PlainTextResponse)
    def health():
        return 'Hello World!'

    @app.post('/auth/register', status_code=201, tags=['auth'])
    def signup(body: dict = Body(...), database=Depends(db)):
        return register(database, credentials(body, True))

    @app.post('/auth/login', tags=['auth'])
    def login(request: Request, body: dict = Body(...), database=Depends(db)):
        data = credentials(body)
        rows = database.all('SELECT id,passwordHash FROM users WHERE username=?', [data['username']])
        valid = verify_password(data['password'], rows[0]['passwordHash'] if rows else request.app.state.dummy_hash)
        if not rows or not valid:
            fail('Invalid username or password', 401)
        now = int(time.time())
        token = jwt.encode({'sub': str(rows[0]['id']), 'iat': now, 'exp': now + 3600, 'iss': 'faceid-api', 'aud': 'faceid-clients'}, request.app.state.secret, algorithm='HS256')
        return {'accessToken': token, 'tokenType': 'Bearer', 'expiresIn': 3600, 'user': account(database, rows[0]['id'])}

    @app.get('/auth/me', tags=['auth'])
    def me(user=Depends(current)):
        return user

    @app.get('/auth/student-accounts/available-students', tags=['auth'])
    def available(user=Depends(teacher), database=Depends(db)):
        return database.all('SELECT s.id,s.studentCode,s.fullName FROM students s LEFT JOIN student_accounts a ON a.studentId=s.id WHERE a.userId IS NULL ORDER BY s.id')

    @app.post('/auth/student-accounts', status_code=201, tags=['auth'])
    def student_account(body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        obj(body, ['username', 'password', 'fullName', 'studentId'])
        data = credentials({key: body.get(key) for key in ('username', 'password', 'fullName')}, True)
        return register(database, data, user, integer(body.get('studentId'), 'studentId'))

    def student(database, student_id):
        return one(database, 'SELECT id,studentCode,fullName FROM students WHERE id=?', [student_id], 'Student does not exist')

    def room(database, room_id):
        return one(database, 'SELECT * FROM rooms WHERE id=?', [room_id], 'Room does not exist')

    def save_entity(database, table, body, entity_id=None):
        fields = ('studentCode', 'fullName') if table == 'students' else ('roomCode', 'name')
        obj(body, fields)
        data = {field: text(body.get(field), field, 50 if field.endswith('Code') else 200, table == 'students') for field in fields}
        try:
            with database.transaction():
                if entity_id is None:
                    entity_id = database.execute(f'INSERT INTO {table}({fields[0]},{fields[1]}) VALUES(?,?)', list(data.values()))
                else:
                    (student if table == 'students' else room)(database, entity_id)
                    database.execute(f'UPDATE {table} SET {fields[0]}=?,{fields[1]}=? WHERE id=?', [*data.values(), entity_id])
                return {'id': entity_id, **data}
        except Exception as error:
            if duplicate(error):
                fail(f'{fields[0]} already exists', 409)
            raise

    @app.get('/students', tags=['students'])
    def students(user=Depends(current), database=Depends(db)):
        if user['role'] == 'student':
            return [student(database, user['studentId'])] if user.get('studentId') else []
        return database.all('SELECT id,studentCode,fullName FROM students ORDER BY id')

    @app.get('/students/by-code', tags=['students'])
    def by_code(studentCode: str, user=Depends(writer), database=Depends(db)):
        return one(database, 'SELECT id,studentCode,fullName FROM students WHERE studentCode=?', [text(studentCode, 'studentCode', 50, True)], 'Student does not exist')

    @app.post('/students', status_code=201, tags=['students'])
    def add_student(body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        return save_entity(database, 'students', body)

    @app.patch('/students/{id}', tags=['students'])
    def update_student(id: str, body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        return save_entity(database, 'students', body, integer(id, 'id', True))

    @app.get('/rooms', tags=['rooms'])
    def rooms(user=Depends(current), database=Depends(db)):
        return database.all('SELECT id,roomCode,name FROM rooms ORDER BY id')

    @app.post('/rooms', status_code=201, tags=['rooms'])
    def add_room(body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        return save_entity(database, 'rooms', body)

    @app.patch('/rooms/{id}', tags=['rooms'])
    def update_room(id: str, body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        return save_entity(database, 'rooms', body, integer(id, 'id', True))

    def parse_event(body):
        obj(body, ['studentId', 'roomId', 'direction', 'occurredAt', 'source', 'eventKey'])
        data = {key: integer(body.get(key), key) for key in ('studentId', 'roomId')}
        data.update(direction=choice(body.get('direction'), 'direction', ('in', 'out')), source=choice(body.get('source'), 'source', ('camera', 'manual')), eventKey=text(body.get('eventKey'), 'eventKey'))
        if 'occurredAt' in body:
            data['occurredAt'] = utc(body['occurredAt'], 'occurredAt')
        return data

    def create_event(database, data, response):
        student(database, data['studentId'])
        room(database, data['roomId'])
        saved = {**data, 'occurredAt': data.get('occurredAt', iso(datetime.now(timezone.utc)))}
        try:
            event_id = database.execute('INSERT INTO room_events(studentId,roomId,direction,occurredAt,source,eventKey) VALUES(?,?,?,?,?,?)', [saved[k] for k in ('studentId', 'roomId', 'direction', 'occurredAt', 'source', 'eventKey')])
        except Exception as error:
            if not duplicate(error):
                raise
            existing = one(database, 'SELECT * FROM room_events WHERE eventKey=?', [data['eventKey']])
            if any(existing[k] != v for k, v in data.items()):
                fail('eventKey already belongs to a different event', 409)
            response.status_code = 200
            return {'event': existing, 'duplicate': True}
        response.status_code = 201
        return {'event': one(database, 'SELECT * FROM room_events WHERE id=?', [event_id]), 'duplicate': False}

    @app.post('/room-events', tags=['room-events'])
    def add_event(response: Response, body: dict = Body(...), user=Depends(writer), database=Depends(db)):
        data = parse_event(body)
        if user['role'] == 'ai_service' and data['source'] != 'camera':
            fail('AI accounts can only create camera events', 403)
        return create_event(database, data, response)

    @app.get('/room-events', tags=['room-events'])
    def events(request: Request, user=Depends(current), database=Depends(db)):
        data = obj(dict(request.query_params), ['studentId', 'roomId', 'direction', 'from', 'to', 'page', 'limit'])
        page, limit = integer(data.get('page', 1), 'page', True), integer(data.get('limit', 20), 'limit', True)
        if limit > 100 or (page - 1) * limit > 9007199254740991:
            fail('Invalid pagination')
        filters = {}
        for key in ('studentId', 'roomId'):
            if key in data:
                filters[key] = integer(data[key], key, True)
        if 'direction' in data:
            filters['direction'] = choice(data['direction'], 'direction', ('in', 'out'))
        dates = {key: utc(data[key], key) for key in ('from', 'to') if key in data}
        if dates.get('from', '') > dates.get('to', '9999'):
            fail('from must not be after to')
        if user['role'] == 'ai_service':
            fail('AI accounts cannot read history', 403)
        if user['role'] == 'student':
            if not user.get('studentId'):
                return {'items': [], 'total': 0, 'page': page, 'limit': limit, 'totalPages': 0}
            if filters.get('studentId', user['studentId']) != user['studentId']:
                fail('Students can only read their own history', 403)
            filters['studentId'] = user['studentId']
        conditions = [f'{key}=?' for key in filters]
        values = list(filters.values())
        for key, value in dates.items():
            conditions.append('occurredAt ' + ('>=' if key == 'from' else '<=') + ' ?')
            values.append(value)
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        with database.transaction():
            total = database.all('SELECT COUNT(*) AS total FROM room_events' + where, values)[0]['total']
            items = database.all('SELECT * FROM room_events' + where + ' ORDER BY occurredAt DESC,id DESC LIMIT ? OFFSET ?', [*values, limit, (page - 1) * limit])
        return {'items': items, 'total': total, 'page': page, 'limit': limit, 'totalPages': (total + limit - 1) // limit}

    def ai(path, body):
        if ai_handler is not None:
            try:
                return ai_handler(path, body)
            except ValueError as error:
                fail(str(error), 400)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Local AI operation failed')
                fail('AI processing failed. Check model files and server logs.', 503)
        key = ai_key()
        try:
            response = httpx.post(os.getenv('AI_SERVICE_URL', 'http://127.0.0.1:8001').rstrip('/') + path, json=body, headers={'X-AI-Key': key}, timeout=30)
        except httpx.HTTPError:
            fail('AI service is unavailable. Start python -m ai.web_server', 503)
        try:
            result = response.json()
        except ValueError:
            result = None
        if response.status_code == 400:
            fail(result.get('message', 'Invalid AI request') if isinstance(result, dict) else 'Invalid AI request')
        if not response.is_success or not isinstance(result, dict):
            fail('AI service failed or returned invalid response', 503)
        return result

    def image(value):
        if not isinstance(value, str) or not value.startswith('data:image/jpeg;base64,') or len(value) > 2_000_000:
            fail('JPEG image required, maximum 2 MB')
        return value

    @app.post('/camera/enroll', status_code=201, tags=['camera'])
    def enroll(body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        obj(body, ['studentId', 'images'])
        record = student(database, integer(body.get('studentId'), 'studentId'))
        photos = body.get('images')
        if not isinstance(photos, list) or len(photos) != 5:
            fail('Five photos required')
        return ai('/enroll', {'studentCode': record['studentCode'], 'images': [image(p) for p in photos]})

    @app.post('/camera/recognize', status_code=201, tags=['camera'])
    def recognize(body: dict = Body(...), user=Depends(current), database=Depends(db)):
        obj(body, ['image'])
        result = ai('/recognize', {'image': image(body.get('image'))})
        if result.get('studentCode') == 'unknown':
            return {'student': None, 'similarity': result.get('similarity'), 'ticket': None}
        if not isinstance(result.get('studentCode'), str) or type(result.get('similarity')) not in (float, int):
            fail('Invalid recognition response', 503)
        record = one(database, 'SELECT id,studentCode,fullName FROM students WHERE studentCode=?', [result['studentCode']], 'Student does not exist')
        return {'student': record, 'similarity': result['similarity'], 'ticket': sign_ticket(record['id'], user['id'])}

    @app.post('/camera/events', tags=['camera'])
    def camera_event(response: Response, body: dict = Body(...), user=Depends(writer), database=Depends(db)):
        obj(body, ['ticket', 'roomId', 'direction', 'eventKey', 'occurredAt'])
        ticket = verify_ticket(body.get('ticket'), user['id'])
        data = {key: value for key, value in body.items() if key != 'ticket'}
        data.update(studentId=ticket['studentId'], source='camera')
        return create_event(database, parse_event(data), response)

    @app.get('/ai-training', tags=['ai-training'])
    def training(user=Depends(teacher)):
        return ai('/training/status', {})

    @app.post('/ai-training/jobs', status_code=201, tags=['ai-training'])
    def train(body: dict = Body(...), user=Depends(teacher)):
        obj(body, [])
        return ai('/training/start', {})

    @app.post('/ai-training/activate', status_code=201, tags=['ai-training'])
    def activate(body: dict = Body(...), user=Depends(teacher)):
        obj(body, ['version'])
        if 'version' not in body or (body['version'] is not None and (not isinstance(body['version'], str) or not re.fullmatch('[a-f0-9]{32}', body['version']))):
            fail('version must be a model ID or null')
        return ai('/training/activate', body)

    def linked(database, user_id):
        rows = database.all('SELECT a.studentId,s.studentCode,s.fullName FROM student_accounts a JOIN students s ON s.id=a.studentId WHERE a.userId=?', [user_id])
        return rows[0] if rows else None

    @app.get('/schedule', tags=['schedule'])
    def schedule(month: str, user=Depends(current), database=Depends(db)):
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month) or int(month[:4]) < 2000 or month == '9999-12':
            fail('month must be YYYY-MM')
        record = linked(database, user['id'])
        if not record:
            return {'student': None, 'items': []}
        year, m = map(int, month.split('-'))
        vn = timezone(timedelta(hours=7))
        start = iso(datetime(year, m, 1, tzinfo=vn))
        end = iso(datetime(year + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=vn))
        items = database.all('SELECT l.*,r.roomCode,r.name AS roomName,a.occurredAt AS attendedAt FROM learning_sessions l JOIN session_students e ON e.sessionId=l.id JOIN rooms r ON r.id=l.roomId LEFT JOIN lesson_attendance a ON a.sessionId=l.id AND a.studentId=e.studentId WHERE e.studentId=? AND l.startsAt>=? AND l.startsAt<? ORDER BY l.startsAt,l.id', [record['studentId'], start, end])
        now = iso(datetime.now(timezone.utc))
        for item in items:
            item['status'] = 'present' if item['attendedAt'] else 'absent' if item['endsAt'] < now else 'pending'
            moment = datetime.now(timezone.utc)
            item['attendanceState'] = attendance_state(database, item, moment)
            item['canAttend'] = not item['attendedAt'] and item['attendanceState'] == 'open' and eligible_time(item, moment)
        return {'student': record, 'items': items}

    @app.post('/schedule/{id}/attendance', tags=['schedule'])
    def attend(id: str, response: Response, body: dict = Body(...), user=Depends(current), database=Depends(db)):
        obj(body, ['ticket'])
        session_id = integer(id, 'id', True)
        with database.transaction():
            database.all('SELECT id FROM learning_sessions WHERE id=?' + (' FOR UPDATE' if database.dialect == 'mysql' else ''), [session_id])
            record = linked(database, user['id'])
            if not record:
                fail('Account is not linked to a student', 403)
            session = one(database, 'SELECT l.* FROM learning_sessions l JOIN session_students e ON e.sessionId=l.id WHERE l.id=? AND e.studentId=?', [session_id, record['studentId']], 'Session is not in your schedule')
            values = [session_id, record['studentId']]
            lookup = 'SELECT * FROM lesson_attendance WHERE sessionId=? AND studentId=?'
            existing = database.all(lookup, values)
            if existing:
                return {'attendance': existing[0], 'duplicate': True}
            ticket = verify_ticket(body.get('ticket'), user['id'])
            if ticket['studentId'] != record['studentId']:
                fail('Recognized face does not match your student account', 403)
            now = datetime.now(timezone.utc)
            if attendance_state(database, session, now) != 'open':
                fail('Giảng viên chưa mở hoặc đã đóng điểm danh buổi học này', 403)
            if not eligible_time(session, now):
                fail('Attendance is outside the session time window')
            try:
                database.execute('INSERT INTO lesson_attendance(sessionId,studentId,occurredAt,source) VALUES(?,?,?,?)', [*values, iso(now), 'camera'])
            except Exception as error:
                if not duplicate(error):
                    raise
                return {'attendance': one(database, lookup, values), 'duplicate': True}
            response.status_code = 201
            return {'attendance': one(database, lookup, values), 'duplicate': False}

    from .classes import install_classes
    install_classes(app, teacher, db)
    install_attendance(app, teacher, db)
    return app


app = create_app()
