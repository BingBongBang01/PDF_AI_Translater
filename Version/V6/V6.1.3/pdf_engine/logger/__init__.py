from .base import Logger
from .console import ConsoleLogger
from .gui import GUILogger

_global_logger = ConsoleLogger()

def get_logger() -> Logger:
    return _global_logger

def set_logger(logger: Logger):
    global _global_logger
    _global_logger = logger
