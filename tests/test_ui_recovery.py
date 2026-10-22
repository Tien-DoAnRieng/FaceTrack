from unittest.mock import Mock, patch
import gradio as gr
from frontend.errors import recover_event


def test_error_preserves_existing_table_and_allows_retry():
    fn = Mock(side_effect=[gr.Error('Mã lớp đã tồn tại'), [[1, 'CNTT01', 'Lớp 1', 2]]])
    fn.__name__ = 'class_rows'
    recovered = recover_event(fn, [gr.Dataframe()])
    with patch('frontend.errors.gr.Warning') as warning:
        assert recovered() == gr.skip()
        warning.assert_called_once()
    assert recovered() == [[1, 'CNTT01', 'Lớp 1', 2]]


def test_error_clears_stale_success_message_without_resetting_form():
    def fail():
        raise gr.Error('Hãy chọn lớp học.')
    recovered = recover_event(fail, [gr.Textbox(label='Thông báo'), gr.Dataframe(), gr.Dropdown()])
    with patch('frontend.errors.gr.Warning'):
        result = recovered()
    assert result[0] == 'Hãy chọn lớp học.'
    assert result[1:] == (gr.skip(), gr.skip())
