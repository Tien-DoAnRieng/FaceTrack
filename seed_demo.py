"""Add repeatable demo classes and October 2026 schedules without replacing data."""
from datetime import datetime, timedelta, timezone
from app.main import ROOT  # Loads local database configuration.
from app.database import Database
from app.validation import iso


def main():
    db = Database()
    counts = {'classes': 0, 'sessions': 0, 'memberships': 0}
    try:
        with db.transaction():
            def entity(table, code_field, code, name):
                rows = db.all(f'SELECT id FROM {table} WHERE {code_field}=?', [code])
                return rows[0]['id'] if rows else db.execute(f'INSERT INTO {table}({code_field},name) VALUES(?,?)', [code, name])

            linked = db.all('SELECT a.studentId FROM student_accounts a JOIN users u ON u.id=a.userId WHERE u.username=?', ['sinhvien01'])
            if not linked:
                raise ValueError('Create and link sinhvien01 before seeding schedules.')
            rooms = [entity('rooms', 'roomCode', code, name) for code, name in [
                ('LAB02', 'Phòng thực hành Demo'), ('A101', 'Phòng học Demo A101')]]
            classes = []
            for code, name in [('CNTT01', 'Công nghệ thông tin 01'), ('CNTT02', 'Công nghệ thông tin 02')]:
                existed = db.all('SELECT id FROM classes WHERE classCode=?', [code])
                class_id = entity('classes', 'classCode', code, name)
                counts['classes'] += not bool(existed)
                classes.append(class_id)
            for group, codes in enumerate([range(1, 6), range(6, 11)]):
                students = [row['id'] for number in codes for row in db.all('SELECT id FROM students WHERE studentCode=?', [f'SV{number+1:03d}'])]
                if group == 0:
                    students.append(linked[0]['studentId'])
                for student_id in students:
                    if not db.all('SELECT studentId FROM class_students WHERE classId=? AND studentId=?', [classes[group], student_id]):
                        db.execute('INSERT INTO class_students(classId,studentId) VALUES(?,?)', [classes[group], student_id])
                        counts['memberships'] += 1
            subjects = [('PY101', 'Lập trình Python', 'Nguyễn Minh Tuấn'),
                        ('CSDL101', 'Cơ sở dữ liệu', 'Trần Thu Hương'),
                        ('AI101', 'Trí tuệ nhân tạo', 'Lê Hoàng Nam')]
            vn = timezone(timedelta(hours=7))
            for group, class_id in enumerate(classes):
                for day, subject in zip([23, 26, 28], subjects):
                    for period in range(2):
                        start = datetime(2026, 10, day, 8 + group * 5 + period * 2, tzinfo=vn)
                        starts, ends = iso(start), iso(start + timedelta(minutes=90))
                        existing = db.all('SELECT l.id FROM learning_sessions l JOIN class_sessions c ON c.sessionId=l.id WHERE c.classId=? AND l.subjectCode=? AND l.startsAt=?', [class_id, subject[0], starts])
                        if existing:
                            session_id = existing[0]['id']
                        else:
                            if db.all('SELECT id FROM learning_sessions WHERE roomId=? AND startsAt<? AND endsAt>?', [rooms[group], ends, starts]):
                                raise ValueError('Demo timetable conflicts with an existing room booking.')
                            if db.all('SELECT l.id FROM learning_sessions l JOIN class_sessions c ON c.sessionId=l.id WHERE c.classId=? AND l.startsAt<? AND l.endsAt>?', [class_id, ends, starts]):
                                raise ValueError('Demo timetable conflicts with an existing class booking.')
                            session_id = db.execute('INSERT INTO learning_sessions(subjectCode,subjectName,teacherName,roomId,startsAt,endsAt) VALUES(?,?,?,?,?,?)', [*subject, rooms[group], starts, ends])
                            db.execute('INSERT INTO class_sessions(sessionId,classId) VALUES(?,?)', [session_id, class_id])
                            counts['sessions'] += 1
                        for student in db.all('SELECT studentId FROM class_students WHERE classId=?', [class_id]):
                            if not db.all('SELECT studentId FROM session_students WHERE sessionId=? AND studentId=?', [session_id, student['studentId']]):
                                db.execute('INSERT INTO session_students(sessionId,studentId) VALUES(?,?)', [session_id, student['studentId']])
        print('Demo data added:', counts)
    finally:
        db.close()


if __name__ == '__main__':
    main()
