from unittest.mock import Mock
import gradio as gr
from frontend import tables
from frontend.pages import PAGES, build_page


def test_selection_uses_displayed_row_after_search():
    event = gr.SelectData(None, {'index': [0, 1], 'value': 'LAB02', 'row_value': [27, 'LAB02', 'Phòng thực hành']})
    assert tables.select_entity(event) == (27, 'LAB02', 'Phòng thực hành')


def test_schedule_only_offers_eligible_lessons(monkeypatch):
    lesson = {'id': 2, 'subjectCode': 'PY', 'subjectName': 'Python', 'teacherName': 'Giảng viên', 'roomCode': 'A1',
              'startsAt': '2026-10-22T01:00:00Z', 'endsAt': '2026-10-22T03:00:00Z', 'status': 'pending', 'canAttend': True}
    closed = {**lesson, 'id': 3, 'canAttend': False, 'status': 'present', 'attendedAt': '2026-10-22T01:00:00Z'}
    monkeypatch.setattr(tables.actions, 'schedule', Mock(return_value={'student': {'studentId': 1}, 'items': [lesson, closed]}))
    rows, dropdown, _ = tables.schedule_rows('token', '2026-10')
    assert rows[0][5] == '22/10/2026 08:00'
    assert rows[1][7] == 'Đã điểm danh'
    assert [value for _, value in dropdown.choices] == [2]


def test_all_pages_use_user_facing_components():
    for name in PAGES:
        page = build_page(name)
        assert all(component['type'] != 'json' for component in page.config['components'])
