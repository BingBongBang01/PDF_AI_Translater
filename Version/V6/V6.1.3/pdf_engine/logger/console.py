from .base import Logger
class ConsoleLogger(Logger):
    def log(self, message: str, level: str = 'INFO') -> None:
        print(f'[{level}] {message}')
