"""Start the complete project: python run.py."""
import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')


if __name__ == '__main__':
    port = int(os.getenv('PORT', '7860'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    # The Gradio callbacks call this same API over loopback.
    os.environ['BACKEND_URL'] = f'http://127.0.0.1:{port}'
    os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
    print(f'FaceID: http://127.0.0.1:{port}/ui/')
    uvicorn.run('server:create_application', factory=True,
                host=os.getenv('HOST', '127.0.0.1'), port=port)
