"""Recover UI events without replacing working components with error panels."""
from functools import wraps
import logging
import gradio as gr

logger = logging.getLogger(__name__)


def recover_event(fn, outputs):
    @wraps(fn)
    def recovered(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except gr.Error as error:
            message = str(getattr(error, 'message', error))
        except Exception:
            logger.exception('UI action failed: %s', fn.__name__)
            message = 'Không hoàn tất được thao tác. Hãy làm mới danh sách để kiểm tra dữ liệu trước khi thử lại.'
        gr.Warning(message, duration=8)
        # Skip preserves the last successful table, input values and session state.
        # Returning normally also releases the loading state and permits retrying.
        values = [message if getattr(output, 'label', None) in ('Thông báo', 'Kết quả lưu', 'Kết quả điểm danh', 'Trạng thái điểm danh') else gr.skip() for output in outputs]
        if not values:
            return None
        return values[0] if len(values) == 1 else tuple(values)
    return recovered


def install_recovery(demo):
    for event in demo.fns.values():
        if event.fn is not None:
            event.fn = recover_event(event.fn, event.outputs)
