import os
import sys
import uvicorn
from .main import app  # Loads .env before reading server settings.

if __name__ == '__main__':
    port = int(os.getenv('PORT', '3000'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    uvicorn.run('app.main:app', host=os.getenv('HOST', '0.0.0.0'), port=port, reload='--reload' in sys.argv)
