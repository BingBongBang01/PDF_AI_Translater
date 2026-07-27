import logging
from logging.handlers import TimedRotatingFileHandler
import os

class AppLogger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()
        return cls._instance
        
    def _setup(self):
        self.logger = logging.getLogger("PDFTranslater")
        self.logger.setLevel(logging.DEBUG)
        
        os.makedirs("logs", exist_ok=True)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Daily rotation
        file_handler = TimedRotatingFileHandler(
            "logs/app.log", when="midnight", interval=1, backupCount=7
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger

# Convenience accessor
logger = AppLogger().get_logger()
