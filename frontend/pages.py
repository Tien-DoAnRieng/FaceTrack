"""Independent Gradio screens, hosted inside the authenticated navigation shell."""
from datetime import datetime, timedelta, timezone
import gradio as gr
from . import gradio_app as actions
from . import tables

PAGES = {
    'camera': ('Nhận diện ra/vào', ('admin', 'teacher', 'ai_service')),
    'enroll': ('Đăng ký khuôn mặt', ('admin', 'teacher')),
    'events': ('Lịch sử ra/vào', ('admin', 'teacher', 'student')),
    'students': ('Sinh viên', ('admin', 'teacher')),
    'rooms': ('Phòng', ('admin', 'teacher')),
    'accounts': ('Tài khoản sinh viên', ('admin', 'teacher')),
    'classes': ('Quản lý lớp học', ('admin', 'teacher')),
    'timetable': ('Quản lý lịch học', ('admin', 'teacher')),
    'schedule': ('Lịch học & điểm danh', ('student',)),
    'training': ('Huấn luyện AI', ('admin', 'teacher')),
}


def session_token(request: gr.Request):
    return request.cookies.get('faceid_session')


def build_page(name):
    with gr.Blocks(title=PAGES[name][0]) as demo:
        token = gr.State(None)
        ready = demo.load(session_token, outputs=token)
        gr.Markdown('## ' + PAGES[name][0])
        if name in ('classes', 'timetable'):
            from .classes import render_classes, render_timetable
            (render_classes if name == 'classes' else render_timetable)(token, ready)
        elif name == 'camera':
            state = gr.State({})
            with gr.Row():
                image = gr.Image(label='Chụp hoặc tải ảnh', sources=['webcam', 'upload'], type='pil')
                with gr.Column():
                    room = gr.Dropdown(label='Phòng', choices=[])
                    direction = gr.Radio([('Vào phòng', 'in'), ('Ra khỏi phòng', 'out')], value='in', label='Hướng')
                    scan = gr.Button('Nhận diện', variant='primary')
                    result = gr.Textbox(label='Kết quả', interactive=False)
                    save = gr.Button('Xác nhận / Thử lưu lại')
                    saved = gr.Textbox(label='Trạng thái lưu', interactive=False)
            ready.then(lambda t: actions.catalogs(t)[1], token, room)
            scan.click(actions.recognize, [token, image, state], [state, result], concurrency_id='camera', concurrency_limit=1)
            save.click(actions.confirm, [token, room, direction, state], [state, saved], concurrency_id='camera', concurrency_limit=1)
            gr.Markdown('Chỉ một người trong khung hình. Nếu lưu lỗi, thử lưu lại trước khi rời trang để tránh mất sự kiện đang chờ.')
        elif name == 'enroll':
            student = gr.Dropdown(label='Sinh viên', choices=[])
            ready.then(lambda t: actions.catalogs(t)[0], token, student)
            gr.Markdown('Chụp đủ 5 ảnh, mỗi ảnh có đúng một khuôn mặt.')
            with gr.Row():
                images = [gr.Image(label=label, sources=['webcam', 'upload'], type='pil') for label in ['Chính diện', 'Hơi quay trái', 'Hơi quay phải', 'Hơi ngẩng', 'Hơi cúi']]
            save = gr.Button('Lưu 5 ảnh khuôn mặt', variant='primary')
            result = gr.Textbox(label='Kết quả', interactive=False)
            save.click(actions.enroll, [token, student, *images], result)
        elif name == 'events':
            refresh = gr.Button('Tải 20 sự kiện gần nhất')
            note = gr.Textbox(label='Tổng quan', interactive=False)
            result = tables.table(['Sinh viên', 'Phòng', 'Hướng', 'Thời gian (giờ Việt Nam)', 'Nguồn'], 'Lịch sử ra/vào')
            ready.then(tables.event_rows, token, [result, note])
            refresh.click(tables.event_rows, token, [result, note])
        elif name in ('students', 'rooms'):
            listing = tables.table(['ID', 'Mã sinh viên' if name == 'students' else 'Mã phòng', 'Họ tên' if name == 'students' else 'Tên phòng'], 'Danh sách')
            refresh = gr.Button('Làm mới danh sách')
            ready.then(lambda t: tables.entity_rows(t, name), token, listing)
            refresh.click(lambda t: tables.entity_rows(t, name), token, listing)
            gr.Markdown('Chọn một dòng để sửa, hoặc bấm **Thêm mới** để tạo bản ghi. Tìm kiếm bằng ô tìm trong bảng.')
            record_id = gr.Number(label='ID đang chọn', value=None, precision=0, interactive=False)
            code = gr.Textbox(label='Mã sinh viên' if name == 'students' else 'Mã phòng')
            full_name = gr.Textbox(label='Họ tên' if name == 'students' else 'Tên phòng')
            save = gr.Button('Lưu', variant='primary')
            new = gr.Button('Thêm mới')
            result = gr.Textbox(label='Kết quả lưu', interactive=False)
            listing.select(tables.select_entity, outputs=[record_id, code, full_name])
            new.click(lambda: (None, '', '', ''), outputs=[record_id, code, full_name, result])
            save.click(lambda t, i, c, n: tables.save_entity(t, name, i, c, n), [token, record_id, code, full_name], result).success(lambda t: tables.entity_rows(t, name), token, listing).success(lambda: (None, '', ''), outputs=[record_id, code, full_name])
        elif name == 'accounts':
            student = gr.Dropdown(label='Sinh viên', choices=[])
            ready.then(lambda t: actions.catalogs(t)[0], token, student)
            username = gr.Textbox(label='Tên đăng nhập sinh viên')
            password = gr.Textbox(label='Mật khẩu', type='password')
            full_name = gr.Textbox(label='Họ tên')
            save = gr.Button('Cấp tài khoản', variant='primary')
            result = gr.Textbox(label='Kết quả', interactive=False)
            save.click(actions.provision, [token, student, username, password, full_name], [result, password])
        elif name == 'schedule':
            month = gr.Textbox(label='Tháng (YYYY-MM)', value=datetime.now(timezone(timedelta(hours=7))).strftime('%Y-%m'))
            refresh = gr.Button('Tải lịch học cá nhân')
            lessons = tables.table(['ID', 'Mã môn', 'Môn học', 'Giảng viên', 'Phòng', 'Bắt đầu', 'Kết thúc', 'Trạng thái', 'Điểm danh lúc', 'Phiên điểm danh'], 'Lịch học')
            gr.Markdown('Chỉ điểm danh khi giảng viên mở phiên. Bấm **Tải lịch học cá nhân** để cập nhật trạng thái mới nhất.')
            note = gr.Textbox(label='Tổng quan', interactive=False)
            session = gr.Dropdown(label='Buổi học đang mở điểm danh', choices=[])
            ready.then(tables.schedule_rows, [token, month], [lessons, session, note])
            refresh.click(tables.schedule_rows, [token, month], [lessons, session, note])
            image = gr.Image(label='Ảnh điểm danh', sources=['webcam', 'upload'], type='pil')
            save = gr.Button('Nhận diện & điểm danh', variant='primary')
            result = gr.Textbox(label='Kết quả điểm danh', interactive=False)
            save.click(tables.attend, [token, session, image], result).success(tables.schedule_rows, [token, month], [lessons, session, note])
        elif name == 'training':
            gr.Markdown('Cần ít nhất 2 sinh viên, mỗi người 10 ảnh từ 2 lần chụp.')
            with gr.Row():
                refresh = gr.Button('Làm mới trạng thái')
                start = gr.Button('Bắt đầu huấn luyện', variant='primary')
            dataset = tables.table(['Mã sinh viên', 'Số ảnh', 'Số lần chụp'], 'Dữ liệu huấn luyện')
            versions = tables.table(['Phiên bản', 'Ngày tạo', 'Thuật toán', 'Độ chính xác', 'Precision', 'Recall', 'F1', 'Trạng thái'], 'Kết quả đánh giá')
            result = gr.Textbox(label='Tiến độ huấn luyện', interactive=False)
            version = gr.Dropdown(label='Phiên bản muốn áp dụng', choices=[('So khớp đặc trưng', '')], value='')
            activate = gr.Button('Áp dụng phiên bản')
            outputs = [dataset, versions, result, version]
            ready.then(tables.training_view, token, outputs)
            refresh.click(tables.training_view, token, outputs)
            start.click(lambda t: tables.training_view(t, 'start'), token, outputs)
            activate.click(lambda t, v: tables.training_view(t, 'activate', v), [token, version], outputs)
    from .errors import install_recovery
    install_recovery(demo)
    return demo
