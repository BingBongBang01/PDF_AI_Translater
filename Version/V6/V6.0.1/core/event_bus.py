from PySide6.QtCore import QObject, Signal

class EventBusSignals(QObject):
    TaskStarted = Signal(str)
    TaskUpdated = Signal(str, str)
    TaskPaused = Signal(str)
    TaskCancelled = Signal(str)
    TaskFinished = Signal(str)
    TaskFailed = Signal(str, str)
    ProgressChanged = Signal(str, int)
    PageChanged = Signal(int)
    ProjectOpened = Signal(str)
    ProjectClosed = Signal()
    OCRStarted = Signal(str)
    OCRFinished = Signal(str, dict)
    TranslationStarted = Signal(str)
    TranslationFinished = Signal(str, dict)
    ExportStarted = Signal(str)
    ExportFinished = Signal(str, str)
    SettingsChanged = Signal(str)
    ThemeChanged = Signal(str)
    HistoryUpdated = Signal()
    CacheUpdated = Signal()
    PluginsReloaded = Signal()

class EventBus:
    """Thread-safe publish/subscribe event bus using QObject signals."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.signals = EventBusSignals()
        return cls._instance
    
    @classmethod
    def publish(cls, event_name: str, *args, **kwargs):
        signal = getattr(cls().signals, event_name, None)
        if signal:
            signal.emit(*args, **kwargs)
            
    @classmethod
    def subscribe(cls, event_name: str, callback):
        signal = getattr(cls().signals, event_name, None)
        if signal:
            signal.connect(callback)
            
    @classmethod
    def unsubscribe(cls, event_name: str, callback):
        signal = getattr(cls().signals, event_name, None)
        if signal:
            try:
                signal.disconnect(callback)
            except RuntimeError:
                pass
