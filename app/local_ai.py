"""Lazy in-process AI adapter; a single engine owns the gallery/model locks."""
from threading import Lock


class LocalAI:
    def __init__(self):
        self._engine = None
        self._lock = Lock()

    def __call__(self, path, body):
        with self._lock:
            if self._engine is None:
                from ai.web_server import WebEngine
                self._engine = WebEngine()
        return self._engine.handle(path, body)
