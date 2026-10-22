"""User-facing table rows and summaries for API responses."""
from datetime import datetime, timedelta, timezone
import gradio as gr
from . import gradio_app as actions


def table(headers, label):
    return gr.Dataframe(headers=headers, value=[], type='array', interactive=False,
                        label=label, wrap=True, show_search='search', max_height=450)


def local_time(value):
    if not value:
        return '—'
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M')
    except (ValueError, TypeError):
        return '—'


def entity_rows(token, kind):
    fields = ('studentCode', 'fullName') if kind == 'students' else ('roomCode', 'name')
    return [[row['id'], row[fields[0]], row[fields[1]]] for row in actions.entity_list(token, kind)]


def select_entity(event: gr.SelectData):
    return tuple(event.row_value[:3])


def save_entity(token, kind, record_id, code, name):
    actions.save_entity(token, kind, record_id, code, name)
    return 'Đã cập nhật thành công.' if record_id is not None else 'Đã thêm mới thành công.'


def event_rows(token):
    data = actions.history(token)
    students = {s['id']: f"{s['studentCode']} · {s['fullName']}" for s in actions.entity_list(token, 'students')}
    rooms = {r['id']: r['roomCode'] for r in actions.entity_list(token, 'rooms')}
    rows = [[students.get(r['studentId'], f"Sinh viên #{r['studentId']}"), rooms.get(r['roomId'], f"Phòng #{r['roomId']}"),
             'Vào' if r['direction'] == 'in' else 'Ra', local_time(r['occurredAt']),
             'Camera' if r['source'] == 'camera' else 'Thủ công'] for r in data['items']]
    return rows, f"Hiển thị {len(rows)} / {data['total']} lượt ra/vào." if rows else 'Chưa có lượt ra/vào.'


def schedule_rows(token, month):
    data = actions.schedule(token, month)
    rows = [[r['id'], r['subjectCode'], r['subjectName'], r['teacherName'], r['roomCode'],
             local_time(r['startsAt']), local_time(r['endsAt']),
             {'present': 'Đã điểm danh', 'absent': 'Vắng mặt', 'pending': 'Chưa điểm danh'}.get(r['status'], 'Chưa điểm danh'),
             local_time(r.get('attendedAt')), {'open': 'Đang mở', 'closed': 'Đã đóng', 'not_opened': 'Chưa mở'}.get(r.get('attendanceState'), 'Chưa mở')] for r in data['items']]
    choices = [(f"{r['subjectName']} · {local_time(r['startsAt'])} · {r['roomCode']}", r['id']) for r in data['items'] if r.get('canAttend')]
    note = f'{len(rows)} buổi học trong tháng.' if rows else 'Chưa có lịch học trong tháng này.'
    if not data.get('student'):
        note = 'Tài khoản chưa được liên kết với hồ sơ sinh viên.'
    return rows, gr.Dropdown(choices=choices, value=None), note


def attend(token, session_id, image):
    result = actions.attend(token, session_id, image)
    return 'Buổi học này đã được điểm danh.' if result.get('duplicate') else 'Điểm danh thành công.'


def training_view(token, action='status', version=None):
    data = actions.training(token, action, version)
    dataset = [[r['studentCode'], r['images'], r['sessions']] for r in data['dataset']]
    versions = [[r['id'], local_time(r['createdAt']), r['algorithm'],
                 *[f"{r[key] * 100:.1f}%" for key in ('accuracy', 'precision', 'recall', 'f1')],
                 'Cần huấn luyện lại' if r.get('stale') else 'Đang áp dụng' if data.get('activeId') == r['id'] else 'Sẵn sàng'] for r in data['versions']]
    choices = [('So khớp đặc trưng', '')] + [(f"{local_time(r['createdAt'])} · {r['id'][:8]}", r['id']) for r in data['versions'] if not r.get('stale')]
    job = data.get('job')
    state = {'running': 'Đang huấn luyện', 'completed': 'Hoàn tất', 'failed': 'Thất bại'}
    note = f"{state.get(job['state'], job['state'])} · {job['progress']}% · {job['message']}" if job else 'Chưa có tác vụ huấn luyện.'
    return dataset, versions, note, gr.Dropdown(choices=choices, value=data.get('activeId') or '')
