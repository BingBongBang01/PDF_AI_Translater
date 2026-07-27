import time
from core.logger import logger
from services.providers.base.request import RetryPolicy
from typing import Callable, Any

class RateLimitException(Exception):
    pass

class RetryManager:
    def __init__(self, policy: RetryPolicy):
        self.policy = policy
        
    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        retries = 0
        delay = self.policy.base_delay
        
        while retries <= self.policy.max_retries:
            try:
                return func(*args, **kwargs)
            except RateLimitException as e:
                logger.warning(f"Rate limited. Retrying in {delay}s...")
                time.sleep(delay)
                retries += 1
                if self.policy.exponential_backoff:
                    delay = min(delay * 2, self.policy.max_delay)
            except Exception as e:
                logger.error(f"Error executing translation: {e}")
                raise e
        raise Exception("Max retries exceeded")
