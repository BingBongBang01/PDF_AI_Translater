from typing import List
from services.providers.base.request import TranslationChunk

class TextChunker:
    def __init__(self, max_tokens: int = 1000):
        self.max_tokens = max_tokens

    def chunk_text(self, text: str, page_number: int) -> List[TranslationChunk]:
        words = text.split()
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_idx = 0
        
        for word in words:
            tokens = len(word) // 4 + 1
            if current_tokens + tokens > self.max_tokens and current_chunk:
                chunks.append(TranslationChunk(f"p{page_number}_c{chunk_idx}", " ".join(current_chunk), page_number))
                chunk_idx += 1
                current_chunk = []
                current_tokens = 0
                
            current_chunk.append(word)
            current_tokens += tokens
            
        if current_chunk:
            chunks.append(TranslationChunk(f"p{page_number}_c{chunk_idx}", " ".join(current_chunk), page_number))
            
        return chunks
