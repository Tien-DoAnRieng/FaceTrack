"""Vietnamese Gradio client for the existing FaceID backend."""
import base64
import io
import os
import uuid
from datetime import datetime, timezone

import gradio as gr
import httpx

API_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:3000").rstrip("/")


def api(method, path, token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = httpx.request(method, API_URL + path, json=body, headers=headers, timeout=60)
    except httpx.HTTPError as exc:
        raise gr.Error("Không kết nối được máy chủ. Hãy thử làm mới danh sách sau ít giây.") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise gr.Error("Backend trả về dữ liệu không hợp lệ.") from exc
    if not response.is_success:
        detail = data.get("message", "Yêu cầu thất bại") if isinstance(data, dict) else "Yêu cầu thất bại"
        raise gr.Error(f"{response.status_code}: {detail}")
    return data


def require_login(token):
    if not token:
        raise gr.Error("Vui lòng đăng nhập trước.")


def jpeg(image):
    if image is None:
        raise gr.Error("Hãy chụp hoặc tải ảnh lên trước.")
    image = image.convert("RGB")
    image.thumbnail((960, 960))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def login(username, password):
    result = api("POST", "/auth/login", body={"username": username, "password": password})
    return result["accessToken"], f"Đã đăng nhập: {result['user']['fullName']} ({result['user']['role']})", "", {}


def catalogs(token):
    require_login(token)
    students = api("GET", "/students", token)
    rooms = api("GET", "/rooms", token)
    return (
        gr.Dropdown(choices=[(f"{s['studentCode']} · {s['fullName']}", s['id']) for s in students], value=None),
        gr.Dropdown(choices=[(f"{r['roomCode']} · {r['name']}", r['id']) for r in rooms], value=None),
    )


def recognize(token, image, state):
    require_login(token)
    if state and state.get("pending"):
        raise gr.Error("Hãy thử lưu lại sự kiện đang chờ trước khi nhận diện mới.")
    # Mutate session state before the request so failures cannot leave an old ticket usable.
    state.clear()
    result = api("POST", "/camera/recognize", token, {"image": jpeg(image)})
    if not result.get("student"):
        return state, "Chưa nhận diện được. Thử lại với ánh sáng tốt hơn."
    state.update(result)
    student = result["student"]
    return state, f"{student['fullName']} · {student['studentCode']}\nĐiểm tương đồng: {result['similarity']:.4f} (không phải xác suất)."


def confirm(token, room, direction, state):
    require_login(token)
    if not state.get("pending"):
        if not state.get("ticket") or room is None:
            raise gr.Error("Hãy nhận diện khuôn mặt và chọn phòng trước.")
        state["pending"] = {
            "ticket": state["ticket"], "roomId": int(room), "direction": direction,
            "occurredAt": datetime.now(timezone.utc).isoformat(),
            "eventKey": f"gradio-{uuid.uuid4()}",
        }
    # Keep the same payload and eventKey when a network failure requires retrying.
    result = api("POST", "/camera/events", token, state["pending"])
    state.clear()
    return state, "Sự kiện đã được lưu trước đó." if result.get("duplicate") else "Đã lưu sự kiện ra/vào."


def enroll(token, student, *images):
    require_login(token)
    if student is None:
        raise gr.Error("Hãy chọn sinh viên.")
    api("POST", "/camera/enroll", token, {"studentId": int(student), "images": [jpeg(image) for image in images]})
    return "Đã đăng ký 5 ảnh khuôn mặt. Bạn có thể chuyển sang tab Nhận diện để kiểm tra."


def history(token):
    require_login(token)
    return api("GET", "/room-events?page=1&limit=20", token)


def entity_list(token, kind):
    require_login(token)
    return api('GET', '/' + kind, token)


def save_entity(token, kind, record_id, code, name):
    require_login(token)
    fields = ('studentCode', 'fullName') if kind == 'students' else ('roomCode', 'name')
    if record_id is not None and (record_id < 1 or int(record_id) != record_id):
        raise gr.Error('ID phải là số nguyên dương; để trống khi tạo mới.')
    suffix = f'/{int(record_id)}' if record_id is not None else ''
    return api('PATCH' if suffix else 'POST', '/' + kind + suffix, token, dict(zip(fields, [code, name])))


def signup(username, password, full_name):
    api('POST', '/auth/register', body={'username': username, 'password': password, 'fullName': full_name})
    return 'Đã tạo tài khoản giáo viên. Bạn có thể đăng nhập.'


def provision(token, student_id, username, password, full_name):
    require_login(token)
    if student_id is None or student_id < 1 or int(student_id) != student_id:
        raise gr.Error('Nhập ID sinh viên hợp lệ trong danh sách sinh viên.')
    api('POST', '/auth/student-accounts', token, {'studentId': int(student_id), 'username': username, 'password': password, 'fullName': full_name})
    return 'Đã tạo tài khoản sinh viên.', ''


def training(token, action, version=None):
    require_login(token)
    if action == 'status':
        return api('GET', '/ai-training', token)
    if action == 'start':
        api('POST', '/ai-training/jobs', token, {})
    else:
        api('POST', '/ai-training/activate', token, {'version': version.strip() or None})
    return api('GET', '/ai-training', token)


def schedule(token, month):
    require_login(token)
    from urllib.parse import urlencode
    return api('GET', '/schedule?' + urlencode({'month': month}), token)


def attend(token, session_id, image):
    require_login(token)
    if session_id is None or session_id < 1 or int(session_id) != session_id:
        raise gr.Error('Nhập ID buổi học trong lịch học.')
    result = api('POST', '/camera/recognize', token, {'image': jpeg(image)})
    if not result.get('ticket'):
        raise gr.Error('Chưa nhận diện được khuôn mặt. Hãy thử lại.')
    return api('POST', f'/schedule/{int(session_id)}/attendance', token, {'ticket': result['ticket']})


def build_app():
    from .pages import build_page
    return build_page("camera")
