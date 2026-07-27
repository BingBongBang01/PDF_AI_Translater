from dataclasses import dataclass

@dataclass
class TranslationStats:
    total_characters: int = 0
    total_words: int = 0
    total_tokens: int = 0
    total_pages: int = 0
    total_chunks: int = 0
    successful_chunks: int = 0
    failed_chunks: int = 0
    retries: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    estimated_cost: float = 0.0
    
class StatisticsTracker:
    """Tracks metrics across the translation pipeline."""
    def __init__(self):
        self.stats = TranslationStats()
        
    def add_tokens(self, input_tokens: int, output_tokens: int, cost: float = 0.0):
        self.stats.total_tokens += (input_tokens + output_tokens)
        self.stats.estimated_cost += cost
        
    def mark_success(self):
        self.stats.successful_chunks += 1
        
    def mark_failure(self):
        self.stats.failed_chunks += 1
        
    def add_retry(self):
        self.stats.retries += 1
