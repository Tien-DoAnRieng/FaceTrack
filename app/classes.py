"""Class rosters and teaching sessions managed by teachers and admins."""
from datetime import datetime, timezone
from fastapi import Body, Depends
from .database import duplicate
from .validation import obj, text, integer, utc, iso, fail


def install_classes(app, teacher, db):
    def find(database, table, id):
        rows = database.all(f'SELECT * FROM {table} WHERE id=?', [id])
        if not rows:
            fail('Không tìm thấy dữ liệu yêu cầu', 404)
        return rows[0]

    @app.get('/classes')
    def classes(user=Depends(teacher), database=Depends(db)):
        return database.all('SELECT c.*, (SELECT COUNT(*) FROM class_students s WHERE s.classId=c.id) AS studentCount FROM classes c ORDER BY c.classCode')

    @app.post('/classes', status_code=201)
    def create(body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        obj(body, ['classCode', 'name'])
        code, name = text(body.get('classCode'), 'classCode', 50), text(body.get('name'), 'name')
        try:
            id = database.execute('INSERT INTO classes(classCode,name) VALUES(?,?)', [code, name])
        except Exception as error:
            if duplicate(error):
                fail('Mã lớp đã tồn tại', 409)
            raise
        return find(database, 'classes', id)

    @app.get('/classes/{id}/students')
    def roster(id: str, user=Depends(teacher), database=Depends(db)):
        class_id = integer(id, 'id', True)
        find(database, 'classes', class_id)
        return database.all('SELECT s.* FROM students s JOIN class_students c ON c.studentId=s.id WHERE c.classId=? ORDER BY s.studentCode', [class_id])

    @app.put('/classes/{id}/students')
    def update_roster(id: str, body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        class_id = integer(id, 'id', True)
        obj(body, ['studentIds'])
        values = body.get('studentIds')
        if not isinstance(values, list) or len(values) > 1000:
            fail('Danh sách sinh viên không hợp lệ')
        ids = set(integer(value, 'studentId') for value in values)
        with database.transaction():
            find(database, 'classes', class_id)
            for student_id in ids:
                find(database, 'students', student_id)
            database.execute('DELETE FROM class_students WHERE classId=?', [class_id])
            for student_id in ids:
                database.execute('INSERT INTO class_students(classId,studentId) VALUES(?,?)', [class_id, student_id])
            # Change future rosters only; keep historical attendance intact.
            sessions = database.all('SELECT l.id FROM learning_sessions l JOIN class_sessions c ON c.sessionId=l.id WHERE c.classId=? AND l.startsAt>?', [class_id, iso(datetime.now(timezone.utc))])
            for session in sessions:
                session_id = session['id']
                existing = database.all('SELECT studentId FROM session_students WHERE sessionId=?', [session_id])
                old = {row['studentId'] for row in existing}
                for student_id in ids - old:
                    database.execute('INSERT INTO session_students(sessionId,studentId) VALUES(?,?)', [session_id, student_id])
                for student_id in old - ids:
                    if not database.all('SELECT id FROM lesson_attendance WHERE sessionId=? AND studentId=?', [session_id, student_id]):
                        database.execute('DELETE FROM session_students WHERE sessionId=? AND studentId=?', [session_id, student_id])
        return {'message': 'Đã lưu danh sách lớp và cập nhật các buổi học sắp tới.'}

    @app.get('/teaching-sessions')
    def sessions(user=Depends(teacher), database=Depends(db)):
        from .attendance import attendance_state, eligible_time
        rows = database.all('SELECT l.*,c.classCode,c.name AS className,r.roomCode FROM learning_sessions l LEFT JOIN class_sessions x ON x.sessionId=l.id LEFT JOIN classes c ON c.id=x.classId JOIN rooms r ON r.id=l.roomId ORDER BY l.startsAt DESC,l.id DESC LIMIT 200')
        now = datetime.now(timezone.utc)
        for row in rows:
            row['attendanceState'] = attendance_state(database, row, now)
            row['canOpenAttendance'] = eligible_time(row, now)
        return rows

    @app.post('/teaching-sessions', status_code=201)
    def create_session(body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        obj(body, ['classId', 'roomId', 'subjectCode', 'subjectName', 'teacherName', 'startsAt', 'endsAt'])
        class_id, room_id = integer(body.get('classId'), 'classId'), integer(body.get('roomId'), 'roomId')
        starts, ends = utc(body.get('startsAt'), 'startsAt'), utc(body.get('endsAt'), 'endsAt')
        if ends <= starts:
            fail('Giờ kết thúc phải sau giờ bắt đầu')
        code = text(body.get('subjectCode'), 'subjectCode', 50)
        name, teacher_name = text(body.get('subjectName'), 'subjectName'), text(body.get('teacherName'), 'teacherName')
        with database.transaction():
            find(database, 'classes', class_id)
            find(database, 'rooms', room_id)
            students = database.all('SELECT studentId FROM class_students WHERE classId=?', [class_id])
            if not students:
                fail('Hãy thêm sinh viên vào lớp trước khi xếp lịch')
            if database.all('SELECT id FROM learning_sessions WHERE roomId=? AND startsAt<? AND endsAt>?', [room_id, ends, starts]):
                fail('Phòng đã có lịch trong khoảng thời gian này', 409)
            if database.all('SELECT l.id FROM learning_sessions l JOIN class_sessions c ON c.sessionId=l.id WHERE c.classId=? AND l.startsAt<? AND l.endsAt>?', [class_id, ends, starts]):
                fail('Lớp đã có lịch trong khoảng thời gian này', 409)
            session_id = database.execute('INSERT INTO learning_sessions(subjectCode,subjectName,teacherName,roomId,startsAt,endsAt) VALUES(?,?,?,?,?,?)', [code, name, teacher_name, room_id, starts, ends])
            database.execute('INSERT INTO class_sessions(sessionId,classId) VALUES(?,?)', [session_id, class_id])
            for student in students:
                database.execute('INSERT INTO session_students(sessionId,studentId) VALUES(?,?)', [session_id, student['studentId']])
        return {'id': session_id, 'message': 'Đã tạo lịch học cho sinh viên trong lớp.'}
