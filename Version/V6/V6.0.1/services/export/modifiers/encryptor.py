from core.logger import logger

class Encryptor:
    @staticmethod
    def encrypt(filepath: str, encryption_options: dict) -> bool:
        logger.info(f"Encrypting {filepath}")
        return True
