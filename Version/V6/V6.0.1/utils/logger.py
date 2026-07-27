"""Application-wide logger: keeps every log line since startup in memory
for export, while the UI only ever needs to show the most recent slice."""
import time
from PySide6.QtCore import QObject, Signal

MAX_DISPLAY_LINES = 500


class AppLogger(QObject):
    """Singleton log sink shared by every page/controller in the app."""
    entry_added = Signal(str)

    _instance = None

    def __init__(self):
        super().__init__()
        self._entries = []

    @classmethod
    def instance(cls) -> "AppLogger":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def log(self, message: str, level: str = "INFO"):
        line = f"[{time.strftime('%H:%M:%S')}] [{level}] {message}"
        self._entries.append(line)
        self.entry_added.emit(line)

    def raw(self, line: str):
        """Store an already-formatted line (e.g. from a page's own log widget) verbatim, just timestamped."""
        stamped = f"[{time.strftime('%H:%M:%S')}] {line}"
        self._entries.append(stamped)
        self.entry_added.emit(stamped)

    def info(self, message: str):
        self.log(message, "INFO")

    def error(self, message: str):
        self.log(message, "ERROR")

    def warning(self, message: str):
        self.log(message, "WARN")

    def recent(self, limit: int = MAX_DISPLAY_LINES) -> list:
        return self._entries[-limit:]

    def all_entries(self) -> list:
        return list(self._entries)

    def clear(self):
        self._entries.clear()

    def export_to_file(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self._entries))


app_logger = AppLogger.instance()


import logging as _logging


class QtLogBridgeHandler(_logging.Handler):
    """logging.Handler that forwards every record emitted anywhere in the app
    (controllers, services, engine, workers) into the in-app AppLogger, so the
    About-page log mirrors exactly what shows up in the terminal / logs/app.log."""
    def __init__(self):
        super().__init__()
        self.setFormatter(_logging.Formatter("%(name)s - %(levelname)s - %(message)s"))

    def emit(self, record):
        try:
            app_logger.raw(self.format(record))
        except Exception:
            pass


class StdStreamTee:
    """Mirrors writes to a real stream (stdout/stderr) into the in-app AppLogger,
    for output from bare print() calls that bypass the logging module entirely."""
    def __init__(self, real_stream, level="INFO"):
        self._real_stream = real_stream
        self._level = level
        self._buffer = ""

    def write(self, text):
        self._real_stream.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                app_logger.log(line, self._level)

    def flush(self):
        self._real_stream.flush()

    def isatty(self):
        return getattr(self._real_stream, "isatty", lambda: False)()


def install_terminal_log_bridge():
    """Call once at app startup: mirrors the stdlib 'PDFTranslater' logger and
    raw stdout/stderr prints into the in-app log so the About page shows
    everything that appears in the terminal."""
    import logging
    import sys

    handler = QtLogBridgeHandler()
    logging.getLogger("PDFTranslater").addHandler(handler)

    if not isinstance(sys.stdout, StdStreamTee):
        sys.stdout = StdStreamTee(sys.stdout, "INFO")
    if not isinstance(sys.stderr, StdStreamTee):
        sys.stderr = StdStreamTee(sys.stderr, "ERROR")
