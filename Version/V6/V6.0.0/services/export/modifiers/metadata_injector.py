from core.logger import logger

class MetadataInjector:
    @staticmethod
    def inject(filepath: str, metadata: dict) -> bool:
        logger.info(f"Injecting metadata into {filepath}")
        return True
