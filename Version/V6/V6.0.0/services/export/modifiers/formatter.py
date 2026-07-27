from core.logger import logger

class Formatter:
    @staticmethod
    def apply_formatting(filepath: str, format_opts: dict) -> bool:
        logger.info(f"Applying formatting to {filepath}")
        return True
