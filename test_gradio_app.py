import unittest
from unittest.mock import patch
from PIL import Image
import gradio as gr
import gradio_app as app

class CameraTests(unittest.TestCase):
    def test_retry_keeps_event_payload(self):
        state = {'ticket': 'signed-ticket'}
        with patch.object(app, 'api', side_effect=gr.Error('network')):
            with self.assertRaises(gr.Error):
                app.confirm('token', 1, 'in', state)
        pending = dict(state['pending'])
        with patch.object(app, 'api', return_value={'duplicate': True}) as request:
            app.confirm('token', 2, 'out', state)
            self.assertEqual(request.call_args.args[3], pending)
        self.assertEqual(state, {})

    def test_failed_scan_invalidates_old_ticket(self):
        state = {'ticket': 'old'}
        with patch.object(app, 'api', side_effect=gr.Error('network')):
            with self.assertRaises(gr.Error):
                app.recognize('token', Image.new('RGB', (10, 10)), state)
        self.assertEqual(state, {})

    def test_pending_event_blocks_new_scan(self):
        state = {'pending': {'eventKey': 'same'}}
        with patch.object(app, 'api') as request:
            with self.assertRaises(gr.Error):
                app.recognize('token', None, state)
            request.assert_not_called()

if __name__ == '__main__':
    unittest.main()
