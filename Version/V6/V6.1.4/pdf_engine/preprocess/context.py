import json
from pdf_engine.logger import get_logger
from pdf_engine.translator.providers_cloud import call_llm
from pdf_engine.translator.ratelimit import GLOBAL_LEDGER
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
        
        # 문맥 감지는 1,000자짜리 분류 한 번이면 끝나는 가벼운 작업이다. 그런데 예전에는
        # pool 순서 그대로(=1순위 고급 모델부터) 시도해서, 정작 번역에 써야 할 최상위
        # 모델의 하루 요청 수(RPD)를 시작하자마자 한 번 까먹었다. 게다가 그 모델이
        # 과부하(503)이면 타임아웃까지 기다린 뒤에야 다음으로 넘어가 실제로 156초를
        # 버린 적도 있다(사용자 로그의 [METRIC] Context Detection took 155.97s).
        # -> 체인의 뒤쪽(저렴한 예비 모델)부터, 살아있고 오늘 한도가 남은 것만, 최대 3개.
        candidates = [e for e in pool
                      if getattr(e, "alive", True) and not getattr(e, "is_local", False)]
        rpd_ok = []
        for e in candidates:
            limit = getattr(e, "rpd_limit", None)
            if limit and GLOBAL_LEDGER.used_today(getattr(e, "key_id", ""), e.model) >= limit:
                continue
            rpd_ok.append(e)
        candidates = rpd_ok or candidates or list(pool)
        candidates.sort(key=lambda e: -getattr(e, "priority", 0))

        for entry in candidates[:3]:
            key_id = getattr(entry, "key_id", "") if not getattr(entry, "is_local", False) else ""
            if key_id:
                GLOBAL_LEDGER.note_request(key_id, entry.model)
            try:
                # KeyEntry.client는 get_key_pool()이 만들 때 이미 생성해 둔 것이다.
                # (예전엔 여기서 build_client(entry)를 다시 호출했는데, build_client는
                #  (provider, key) 두 인자를 받는 함수라 KeyEntry 객체 하나만 넘기면
                #  매번 TypeError로 실패했다 - pool의 모든 항목에서 전부 실패하고
                #  '[WARNING] All providers failed'로 폴백되는 게 사실상 100% 고정 동작이었다.)
                response = call_llm(
                    provider=entry.provider,
                    client=entry.client,
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
                if key_id:
                    GLOBAL_LEDGER.note_success(key_id, entry.model)

                # Match against known categories
                for cat in cls.CATEGORIES:
                    if cat.lower() == context:
                        logger.log(f"[INFO] Context detected: {cat} (using {entry.label})")
                        return cat
                        
                logger.log(f"[WARNING] LLM returned unknown context category: {context}")
                return "default"
                
            except Exception as e:
                logger.log(f"[DEBUG] Context detection failed with {entry.label}: {e}")
                continue
                
        logger.log("[WARNING] All providers failed for context detection. Falling back to 'default'.")
        return "default"
