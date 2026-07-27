from core.logger import logger

class Watermarker:
    @staticmethod
    def apply(filepath: str, watermark_options: dict) -> bool:
        logger.info(f"Applying watermark to {filepath}")
        return True
