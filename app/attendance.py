"""Explicit instructor-controlled attendance windows."""
from datetime import datetime, timedelta, timezone
from fastapi import Body, Depends
from .validation import obj, integer, fail, iso

VN = timezone(timedelta(hours=7))


def eligible_time(session, now):
    starts = datetime.fromisoformat(session['startsAt'].replace('Z', '+00:00'))
    ends = datetime.fromisoformat(session['endsAt'].replace('Z', '+00:00'))
    return (now.astimezone(VN).date() == starts.astimezone(VN).date()
            and starts - timedelta(minutes=15) <= now <= ends)


def attendance_state(database, session, now):
    rows = database.all('SELECT state FROM attendance_windows WHERE sessionId=?', [session['id']])
    ends = datetime.fromisoformat(session['endsAt'].replace('Z', '+00:00'))
    if now > ends:
        return 'closed'
    return rows[0]['state'] if rows else 'not_opened'


def install_attendance(app, teacher, db):
    @app.put('/teaching-sessions/{id}/attendance-window')
    def change(id: str, body: dict = Body(...), user=Depends(teacher), database=Depends(db)):
        session_id = integer(id, 'id', True)
        obj(body, ['state'])
        state = body.get('state')
        if state not in ('open', 'closed'):
            fail('Trạng thái điểm danh không hợp lệ')
        with database.transaction():
            suffix = ' FOR UPDATE' if database.dialect == 'mysql' else ''
            rows = database.all('SELECT * FROM learning_sessions WHERE id=?' + suffix, [session_id])
            if not rows:
                fail('Không tìm thấy buổi học', 404)
            now = datetime.now(timezone.utc)
            if state == 'open' and not eligible_time(rows[0], now):
                fail('Chỉ mở điểm danh trong ngày học, từ 15 phút trước giờ bắt đầu đến giờ kết thúc')
            old = database.all('SELECT state FROM attendance_windows WHERE sessionId=?', [session_id])
            if old:
                database.execute('UPDATE attendance_windows SET state=?,updatedBy=?,updatedAt=? WHERE sessionId=?', [state, user['id'], iso(now), session_id])
            else:
                database.execute('INSERT INTO attendance_windows(sessionId,state,updatedBy,updatedAt) VALUES(?,?,?,?)', [session_id, state, user['id'], iso(now)])
        return {'message': 'Đã mở điểm danh.' if state == 'open' else 'Đã đóng điểm danh.'}
