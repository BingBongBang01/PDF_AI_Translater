class AppError(Exception):
    """Base exception for all application errors."""
    pass

class ConfigurationError(AppError):
    pass

class ServiceError(AppError):
    pass

class PluginError(AppError):
    pass

class TaskError(AppError):
    pass

class OCRException(AppError):
    pass

class TranslationException(AppError):
    pass

class ExportException(AppError):
    pass

class CacheException(AppError):
    pass

class ValidationException(AppError):
    pass
