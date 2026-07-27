import json
from pdf_engine.logger import get_logger
from pdf_engine.translator.providers_cloud import build_client, call_llm
from pdf_engine.placeholder.segment import Segment
from typing import List

class ContextDetector:
    CATEGORIES = ["document title", "search query", "tweet", "UI", "academic paper", "report", "chat", "marketing"]
    
    @classmethod
    def detect(cls, pool: list, segments: List[Segment]) -> str:
        """
        Samples the text from the segments and uses the LLM pool to classify the context.
        Returns one of the CATEGORIES, or 'default' if detection fails.
        """
        logger = get_logger()
        
        # Gather sample text (first 1000 characters)
        sample_text = ""
        for s in segments:
            if s.needs_translation:
                sample_text += s.text + "\n"
                if len(sample_text) > 1000:
                    break
                    
        sample_text = sample_text[:1000].strip()
        if not sample_text:
            return "default"
            
        system_prompt = (
            f"You are a context classifier. Analyze the following text snippet and classify it into EXACTLY ONE of the following categories:\n"
            f"{', '.join(cls.CATEGORIES)}.\n"
            "Return ONLY a valid JSON object with the key 'context' and the category as the value. Do not output anything else."
        )
        
        user_prompt = f"Text Snippet:\n{sample_text}"
        
        # Try to get a classification using the pool
        for entry in pool:
            try:
                client = build_client(entry)
                response = call_llm(
                    provider=entry.provider,
                    client=client,
                    model=entry.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=50,
                    temperature=0.0
                )
                
                # Try to parse JSON from the response
                # LLMs sometimes wrap in ```json ... ```
                cleaned = response.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:-3].strip()
                elif cleaned.startswith("```"):
                    cleaned = cleaned[3:-3].strip()
                    
                data = json.loads(cleaned)
                context = data.get("context", "").lower()
                
                # Match against known categories
                for cat in cls.CATEGORIES:
                    if cat.lower() == context:
                        logger.log(f"[INFO] Context detected: {cat} (using {entry.provider})")
                        return cat
                        
                logger.log(f"[WARNING] LLM returned unknown context category: {context}")
                return "default"
                
            except Exception as e:
                logger.log(f"[DEBUG] Context detection failed with {entry.label}: {e}")
                continue
                
        logger.log("[WARNING] All providers failed for context detection. Falling back to 'default'.")
        return "default"
