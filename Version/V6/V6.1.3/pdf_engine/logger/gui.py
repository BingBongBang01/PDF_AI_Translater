from .base import Logger
class GUILogger(Logger):
    def __init__(self, app_instance):
        self.app = app_instance
    def log(self, message: str, level: str = 'INFO') -> None:
        self.app._log(f'[{level}] {message}')
