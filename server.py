"""One FastAPI application hosting the API, local AI and Gradio UI."""
import os
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
os.environ.setdefault('GRADIO_ANALYTICS_ENABLED', 'False')

from app.main import create_app
from app.local_ai import LocalAI
from frontend.pages import PAGES, build_page
from frontend.navigation import install_navigation


def create_application():
    api = create_app(ai_handler=LocalAI())
    install_navigation(api)
    for name in PAGES:
        api = gr.mount_gradio_app(
            api, build_page(name).queue(), path=f'/_pages/{name}',
            blocked_paths=[str(ROOT / '.env'), str(ROOT / 'data'), str(ROOT / 'models')],
            show_error=False, max_file_size='10mb', run_history=False,
        )
    return api
