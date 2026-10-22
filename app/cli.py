"""Database administration: python -m app.cli --help."""
import argparse
from .main import load_dotenv, ROOT
from .database import Database
from .security import ROLES
from .validation import text, utc


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    role = commands.add_parser('set-role')
    role.add_argument('username')
    role.add_argument('role', choices=ROLES)
    schedule = commands.add_parser('setup-schedule')
    for name in ('username', 'studentCode', 'roomCode', 'subjectCode', 'subjectName', 'teacherName', 'startsAt', 'endsAt'):
        schedule.add_argument(name)
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    database = Database()
    try:
        with database.transaction():
            users = database.all('SELECT id FROM users WHERE username=?', [text(args.username, 'username', 50)])
            if not users:
                raise ValueError('Account does not exist')
            user_id = users[0]['id']
            if args.command == 'set-role':
                database.execute('UPDATE users SET role=? WHERE id=?', [args.role, user_id])
                print(f'Role updated: {args.username} -> {args.role}')
                return
            starts, ends = utc(args.startsAt, 'startsAt'), utc(args.endsAt, 'endsAt')
            if ends <= starts:
                raise ValueError('endsAt must be after startsAt')
            students = database.all('SELECT id FROM students WHERE studentCode=?', [args.studentCode])
            rooms = database.all('SELECT id FROM rooms WHERE roomCode=?', [args.roomCode])
            if not students or not rooms:
                raise ValueError('Create student and room first')
            student_id, room_id = students[0]['id'], rooms[0]['id']
            links = database.all('SELECT * FROM student_accounts WHERE userId=? OR studentId=?', [user_id, student_id])
            if any(link['userId'] != user_id or link['studentId'] != student_id for link in links):
                raise ValueError('Account/student already linked differently')
            if not links:
                database.execute('INSERT INTO student_accounts(userId,studentId) VALUES(?,?)', [user_id, student_id])
            code = text(args.subjectCode, 'subjectCode', 50)
            name, teacher = text(args.subjectName, 'subjectName'), text(args.teacherName, 'teacherName')
            sessions = database.all('SELECT * FROM learning_sessions WHERE roomId=? AND subjectCode=? AND startsAt=?', [room_id, code, starts])
            if len(sessions) > 1 or (sessions and any(sessions[0][key] != value for key, value in [('subjectName', name), ('teacherName', teacher), ('endsAt', ends)])):
                raise ValueError('Existing session has conflicting content')
            session_id = sessions[0]['id'] if sessions else database.execute('INSERT INTO learning_sessions(subjectCode,subjectName,teacherName,roomId,startsAt,endsAt) VALUES(?,?,?,?,?,?)', [code, name, teacher, room_id, starts, ends])
            if not database.all('SELECT * FROM session_students WHERE sessionId=? AND studentId=?', [session_id, student_id]):
                database.execute('INSERT INTO session_students(sessionId,studentId) VALUES(?,?)', [session_id, student_id])
            print(f'Schedule ready: session {session_id}')
    finally:
        database.close()


if __name__ == '__main__':
    main()
