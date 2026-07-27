import abc
class Logger(abc.ABC):
    @abc.abstractmethod
    def log(self, message: str, level: str = 'INFO') -> None:
        pass
