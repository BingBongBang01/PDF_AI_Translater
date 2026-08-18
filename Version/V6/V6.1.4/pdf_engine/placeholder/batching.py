"""세그먼트를 배치로 묶고, LLM에 보낼 사용자 프롬프트를 구성한다."""
from __future__ import annotations

import re

from pdf_engine.placeholder.segment import Segment


def is_label_like(text: str) -> bool:
    """
    "JAMES:", "EMMA:", "PROFESSOR AUSTIN:" 같은 화자 라벨/짧은 표제어인지 판정.

    실제로 확인된 문제: 이런 짧은 라벨 세그먼트를 문단(수십~수백자 대화문) 세그먼트와
    같은 배치에 함께 보내면, 특히 소형 로컬 모델이 둘을 혼동해 라벨에는 옆 문단의
    번역문을, 문단에는 라벨 텍스트를 배정하는 경우가 반복적으로 관찰됐다(같은 문서를
    다시 번역해도 매번 같은 지점에서 재현됨 - 캐시 문제가 아니라 모델이 짧은/긴
    세그먼트가 섞인 배치에서 실제로 헷갈리는 것). 라벨류를 별도 배치로 분리해 이
    혼동의 소지 자체를 없앤다.
    """
    t = text.strip()
    if not t or "\n" in t or len(t) > 30:
        return False
    return t.endswith(":") or t.endswith("：")


def make_batches(segments: list[Segment], max_chars: int, max_segs: int):
    batch, size, batch_kind = [], 0, None
    for s in segments:
        if not s.needs_translation:
            continue
        kind = "label" if is_label_like(s.text) else "para"
        if batch and (size + len(s.text) > max_chars or len(batch) >= max_segs
                      or kind != batch_kind):
            yield batch
            batch, size = [], 0
        batch.append(s)
        size += len(s.text)
        batch_kind = kind
    if batch:
        yield batch


def render_segments_block(batch: list[Segment]) -> str:
    parts = [f"SEGMENT_ID: {s.seg_id}\nTEXT:\n{s.text}" for s in batch]
    return "\n\n-----\n\n".join(parts)


def render_prev_context(pairs: list[tuple[str, str]], limit_chars: int = 1500) -> str:
    """직전 번역 (원문, 번역) 쌍을 용어 일관성 유지용으로 렌더링."""
    if not pairs:
        return "(none)"
    chunks, total = [], 0
    for src, dst in reversed(pairs):
        chunk = f"SOURCE: {src}\nTRANSLATION: {dst}"
        if total + len(chunk) > limit_chars and chunks:
            break
        chunks.append(chunk)
        total += len(chunk)
    return "\n---\n".join(reversed(chunks))


_AUTO_DETECT_TOKENS = {"auto", "auto-detect", "autodetect", "자동", "자동 인식", "자동인식"}


def resolve_source_lang(raw: str) -> str:
    """
    GUI의 '자동 인식' 선택(또는 --source-lang auto)을 모델이 이해할 자연어 지시문으로 치환.
    일반 언어명(예: English, 한국어)은 그대로 통과시킨다.
    """
    if raw.strip().lower() in _AUTO_DETECT_TOKENS:
        return "the original language of the text (detect it automatically per segment)"
    return raw


def build_user_prompt(template: str, args, glossary_text: str,
                      prev_context: str, batch: list[Segment]) -> str:
    repl = {
        "{{source_language}}": resolve_source_lang(args.source_lang),
        "{{target_language}}": args.target_lang,
        "{{document_type}}": args.doc_type,
        "{{translation_style}}": args.style,
        "{{terminology_policy}}": args.terminology_policy,
        "{{glossary_data}}": glossary_text or "(no glossary provided)",
        "{{document_title}}": args.title,
        "{{document_domain}}": args.domain,
        "{{document_instructions}}": args.instructions or "(none)",
        "{{prev_context}}": prev_context,
        "{{text_segments}}": render_segments_block(batch),
    }
    out = template
    for key, val in repl.items():
        out = out.replace(key, val)
    return out