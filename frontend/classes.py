"""Teacher-facing class roster and timetable screens."""
from datetime import datetime, timezone, timedelta
import gradio as gr
from .gradio_app import api, require_login
from .tables import table, local_time


def class_choices(token):
    require_login(token)
    classes = api('GET', '/classes', token)
    return gr.Dropdown(choices=[(f"{r['classCode']} · {r['name']}", r['id']) for r in classes], value=None)


def class_rows(token):
    return [[r['id'], r['classCode'], r['name'], r['studentCount']] for r in api('GET', '/classes', token)]


def create_class(token, code, name):
    api('POST', '/classes', token, {'classCode': code, 'name': name})
    return 'Đã tạo lớp học.', class_rows(token), class_choices(token)


def roster(token, class_id):
    if class_id is None:
        return gr.Dropdown(choices=[], value=[])
    members = api('GET', f'/classes/{int(class_id)}/students', token)
    students = api('GET', '/students', token)
    return gr.Dropdown(choices=[(f"{r['studentCode']} · {r['fullName']}", r['id']) for r in students], value=[r['id'] for r in members])


def save_roster(token, class_id, students):
    if class_id is None:
        raise gr.Error('Hãy chọn lớp học.')
    result = api('PUT', f'/classes/{int(class_id)}/students', token, {'studentIds': students or []})
    return result['message'], class_rows(token)


def session_rows(token):
    return [[r['classCode'] or '—', r['subjectCode'], r['subjectName'], r['teacherName'], r['roomCode'], local_time(r['startsAt']), local_time(r['endsAt']),
             {'open': 'Đang mở', 'closed': 'Đã đóng', 'not_opened': 'Chưa mở'}[r['attendanceState']]] for r in api('GET', '/teaching-sessions', token)]


def attendance_choices(token):
    rows = api('GET', '/teaching-sessions', token)
    choices = [(f"{r['classCode'] or 'Buổi học'} · {r['subjectName']} · {local_time(r['startsAt'])}", r['id']) for r in rows if r['canOpenAttendance']]
    return gr.Dropdown(choices=choices, value=None)


def change_attendance(token, session_id, state):
    if session_id is None:
        raise gr.Error('Hãy chọn buổi học trong thời gian cho phép.')
    result = api('PUT', f'/teaching-sessions/{int(session_id)}/attendance-window', token, {'state': state})
    return result['message'], session_rows(token)


def save_session(token, class_id, room_id, code, name, teacher, starts, ends):
    if class_id is None or room_id is None:
        raise gr.Error('Hãy chọn lớp và phòng học.')
    def timestamp(value):
        try:
            if value is None or isinstance(value, bool):
                raise ValueError()
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            raise gr.Error('Hãy chọn đầy đủ ngày và giờ bắt đầu, kết thúc.') from None
    result = api('POST', '/teaching-sessions', token, {
        'classId': class_id, 'roomId': room_id, 'subjectCode': code, 'subjectName': name,
        'teacherName': teacher, 'startsAt': timestamp(starts), 'endsAt': timestamp(ends),
    })
    return result['message'], session_rows(token)


def render_classes(token, ready):
    listing = table(['ID', 'Mã lớp', 'Tên lớp', 'Số sinh viên'], 'Danh sách lớp học')
    refresh = gr.Button('Làm mới danh sách')
    with gr.Row():
        code = gr.Textbox(label='Mã lớp')
        name = gr.Textbox(label='Tên lớp')
    create = gr.Button('Tạo lớp', variant='primary')
    gr.Markdown('### Danh sách sinh viên trong lớp\nChọn lớp, chọn các sinh viên rồi bấm lưu. Bỏ chọn để đưa sinh viên ra khỏi lớp. Lịch đã diễn ra và kết quả điểm danh được giữ nguyên.')
    selected = gr.Dropdown(label='Lớp học', choices=[])
    students = gr.Dropdown(label='Sinh viên trong lớp', choices=[], multiselect=True)
    save = gr.Button('Lưu danh sách sinh viên', variant='primary')
    note = gr.Textbox(label='Thông báo', interactive=False)
    ready.then(class_rows, token, listing).then(class_choices, token, selected)
    refresh.click(class_rows, token, listing).then(class_choices, token, selected)
    create.click(create_class, [token, code, name], [note, listing, selected])
    selected.change(roster, [token, selected], students)
    save.click(save_roster, [token, selected, students], [note, listing])


def render_timetable(token, ready):
    from .gradio_app import catalogs
    listing = table(['Lớp', 'Mã môn', 'Môn học', 'Giảng viên', 'Phòng', 'Bắt đầu', 'Kết thúc', 'Điểm danh'], 'Lịch học đã xếp (200 buổi gần nhất)')
    refresh = gr.Button('Làm mới lịch học')
    gr.Markdown('### Mở / đóng điểm danh\nChọn buổi học hôm nay. Có thể mở từ 15 phút trước giờ bắt đầu; hết giờ học hệ thống tự ngừng nhận điểm danh.')
    attendance_session = gr.Dropdown(label='Buổi học có thể mở điểm danh', choices=[])
    with gr.Row():
        open_attendance = gr.Button('Mở điểm danh', variant='primary')
        close_attendance = gr.Button('Đóng điểm danh')
    attendance_note = gr.Textbox(label='Trạng thái điểm danh', interactive=False)
    ready.then(attendance_choices, token, attendance_session)
    refresh.click(attendance_choices, token, attendance_session)
    open_attendance.click(lambda t, s: change_attendance(t, s, 'open'), [token, attendance_session], [attendance_note, listing])
    close_attendance.click(lambda t, s: change_attendance(t, s, 'closed'), [token, attendance_session], [attendance_note, listing])
    gr.Markdown('### Xếp buổi học\nSinh viên trong lớp sẽ thấy buổi học này trong lịch cá nhân. Ngày giờ tính theo giờ Việt Nam.')
    with gr.Row():
        selected = gr.Dropdown(label='Lớp học', choices=[])
        room = gr.Dropdown(label='Phòng học', choices=[])
    with gr.Row():
        code = gr.Textbox(label='Mã môn học')
        name = gr.Textbox(label='Tên môn học')
    teacher = gr.Textbox(label='Giảng viên')
    with gr.Row():
        starts = gr.DateTime(label='Bắt đầu', include_time=True, type='timestamp', timezone='Asia/Ho_Chi_Minh', info='Chọn ngày và giờ Việt Nam', interactive=True)
        ends = gr.DateTime(label='Kết thúc', include_time=True, type='timestamp', timezone='Asia/Ho_Chi_Minh', info='Chọn ngày và giờ Việt Nam', interactive=True)
    save = gr.Button('Tạo lịch cho lớp', variant='primary')
    note = gr.Textbox(label='Thông báo', interactive=False)
    ready.then(session_rows, token, listing).then(class_choices, token, selected).then(lambda t: catalogs(t)[1], token, room)
    refresh.click(session_rows, token, listing).then(class_choices, token, selected).then(lambda t: catalogs(t)[1], token, room)
    save.click(save_session, [token, selected, room, code, name, teacher, starts, ends], [note, listing])
    # Leave room for the calendar/time popover below the final form fields.
    gr.HTML('<div style="height:360px" aria-hidden="true"></div>')
