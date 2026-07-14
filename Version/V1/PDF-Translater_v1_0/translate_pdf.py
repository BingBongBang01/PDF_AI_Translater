#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate_pdf.py — AI(Anthropic Claude) API 기반 PDF 번역기

파이프라인 (데이터 흐름):
  input.pdf
   -> [1] 추출   : PyMuPDF get_text("dict")로 텍스트 블록별
                   (내용, bbox 좌표, 폰트 크기, 색, 굵기) 추출
   -> [2] 배치   : 블록마다 segment_id(page_001_block_003) 부여 후
                   문자 수 기준으로 배치 묶음 생성
   -> [3] 번역   : prompts/system_prompt.txt + prompts/user_template.txt의
                   {{placeholder}}를 채워 Anthropic Messages API 호출.
                   응답 JSON {"translations":[{segment_id, translated_text}]} 파싱.
                   누락 세그먼트는 자동 재시도.
   -> [4] 재구성 : 원문 블록을 redaction으로 제거(이미지/배경/선은 보존)한 뒤
                   같은 bbox에 번역문 삽입. insert_htmlbox가 폰트 폴백(한글 포함)과
                   자동 축소(scale_low)를 처리. 실패 시 내장 CJK 폰트("korea")로 폴백.
   -> output.pdf

사용 예:
  export ANTHROPIC_API_KEY=sk-ant-...
  python translate_pdf.py input.pdf -o output_ko.pdf                 # 기본: English -> Korean
  python translate_pdf.py input.pdf --source-lang Japanese --target-lang Korean
  python translate_pdf.py input.pdf --mock                           # API 없이 파이프라인 검증
  python translate_pdf.py input.pdf --dry-run                        # 추출 결과만 출력
  python translate_pdf.py input.pdf --pages 1-3 --export-json t.json # 일부 페이지 + 번역 결과 저장
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import pymupdf
except ImportError:
    print("[오류] pymupdf가 없습니다. 설치: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = SCRIPT_DIR / "prompts" / "system_prompt.txt"
USER_TEMPLATE_PATH = SCRIPT_DIR / "prompts" / "user_template.txt"

# 어떤 문자 체계든 '글자'가 하나라도 있는지 검사 (숫자/기호만 있는 블록은 번역 생략)
LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-3.1-pro-preview",
}
DEFAULT_MODEL = DEFAULT_MODELS["anthropic"]  # 하위 호환용
DEFAULT_TERMINOLOGY_POLICY = (
    "Use established target-language technical terminology. "
    "Keep well-known technical abbreviations, protocol names, commands, and product names "
    "(e.g., VXLAN, BGP, OSPF, CLI, API) in their original form. "
    "For an important technical term, the first occurrence may include the original term in parentheses."
)


# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------
@dataclass
class Segment:
    seg_id: str
    page: int                      # 0-based
    bbox: tuple                    # (x0, y0, x1, y1)
    text: str                      # 원문
    font_size: float               # 블록 내 최빈 폰트 크기(pt)
    color: str                     # "#rrggbb"
    bold: bool
    needs_translation: bool        # False면 원문 그대로 유지(숫자 전용 블록 등)
    translated: str | None = None


# ---------------------------------------------------------------------------
# [1] 추출
# ---------------------------------------------------------------------------
def extract_segments(doc: "pymupdf.Document", page_filter: set[int] | None,
                     translate_all: bool) -> list[Segment]:
    segments: list[Segment] = []
    for pno in range(doc.page_count):
        if page_filter is not None and pno not in page_filter:
            continue
        page = doc[pno]
        data = page.get_text("dict", sort=True)  # 위->아래, 왼->오른쪽 정렬
        bno = 0
        for block in data.get("blocks", []):
            if block.get("type") != 0:           # 0 = 텍스트 블록
                continue
            lines, sizes, colors, bold_votes = [], [], [], []
            for line in block.get("lines", []):
                line_text = "".join(sp.get("text", "") for sp in line.get("spans", []))
                if line_text.strip():
                    lines.append(line_text)
                for sp in line.get("spans", []):
                    sizes.append(round(float(sp.get("size", 11.0)), 1))
                    colors.append(int(sp.get("color", 0)))
                    is_bold = bool(sp.get("flags", 0) & 16) or "bold" in sp.get("font", "").lower()
                    bold_votes.append(is_bold)
            text = "\n".join(lines).strip()
            if not text:
                continue
            seg = Segment(
                seg_id=f"page_{pno + 1:03d}_block_{bno:03d}",
                page=pno,
                bbox=tuple(block["bbox"]),
                text=text,
                font_size=(Counter(sizes).most_common(1)[0][0] if sizes else 11.0),
                color=f"#{(Counter(colors).most_common(1)[0][0] if colors else 0):06x}",
                bold=(sum(bold_votes) > len(bold_votes) / 2) if bold_votes else False,
                needs_translation=(True if translate_all else bool(LETTER_RE.search(text))),
            )
            segments.append(seg)
            bno += 1
    return segments


# ---------------------------------------------------------------------------
# [2] 배치
# ---------------------------------------------------------------------------
def make_batches(segments: list[Segment], max_chars: int, max_segs: int):
    batch, size = [], 0
    for s in segments:
        if not s.needs_translation:
            continue
        if batch and (size + len(s.text) > max_chars or len(batch) >= max_segs):
            yield batch
            batch, size = [], 0
        batch.append(s)
        size += len(s.text)
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


def build_user_prompt(template: str, args, glossary_text: str,
                      prev_context: str, batch: list[Segment]) -> str:
    repl = {
        "{{source_language}}": args.source_lang,
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


# ---------------------------------------------------------------------------
# [3] 번역 (Anthropic Messages API / Gemini API)
# ---------------------------------------------------------------------------
def load_api_key(provider: str, explicit_path: str | None) -> str:
    """
    API 키 로딩 우선순위:
      1) --api-key-file로 지정한 파일
      2) 스크립트/현재 작업 디렉터리의 api.txt (첫 줄, 공백 제거)
      3) 환경변수 (ANTHROPIC_API_KEY 또는 GEMINI_API_KEY/GOOGLE_API_KEY)
    api.txt는 평문 저장이므로 .gitignore 등록 및 리포지토리 커밋 금지 권장.
    """
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    else:
        candidates += [Path.cwd() / "api.txt", Path(__file__).resolve().parent / "api.txt"]

    for p in candidates:
        if p.is_file():
            key = p.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            if key:
                return key
            sys.exit(f"[오류] {p} 파일이 비어 있습니다.")

    env_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "GEMINI_API_KEY"
    env_val = os.environ.get(env_var) or (os.environ.get("GOOGLE_API_KEY") if provider == "gemini" else None)
    if env_val:
        return env_val

    sys.exit(
        f"[오류] API 키를 찾지 못했습니다. 다음 중 하나로 제공하세요:\n"
        f"       1) --api-key-file api.txt\n"
        f"       2) 현재 디렉터리에 api.txt 파일 생성 (키 한 줄)\n"
        f"       3) export {env_var}=..."
    )


def get_client(args):
    """args.provider에 맞는 (provider, client) 튜플 반환."""
    provider = args.provider
    api_key = load_api_key(provider, args.api_key_file)

    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            sys.exit("[오류] anthropic SDK가 없습니다. 설치: pip install anthropic")
        return provider, anthropic.Anthropic(api_key=api_key)

    if provider == "gemini":
        try:
            from google import genai
        except ImportError:
            sys.exit("[오류] google-genai SDK가 없습니다. 설치: pip install google-genai")
        return provider, genai.Client(api_key=api_key)

    sys.exit(f"[오류] 알 수 없는 provider: {provider}")


def call_claude(client, model: str, system_prompt: str, user_prompt: str,
                max_tokens: int, temperature: float | None) -> str:
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        msg = client.messages.create(**kwargs)
    except Exception as e:
        # 일부 신형 모델은 sampling 파라미터(temperature)를 받지 않음 -> 제거 후 1회 재시도
        if temperature is not None and "temperature" in str(e).lower():
            kwargs.pop("temperature", None)
            msg = client.messages.create(**kwargs)
        else:
            raise
    # thinking 블록 등은 .text 속성이 없으므로 자동 배제
    return "".join(getattr(block, "text", "") for block in msg.content)


def call_gemini(client, model: str, system_prompt: str, user_prompt: str,
                max_tokens: int, temperature: float | None) -> str:
    from google.genai import types
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=max_tokens,
        # 응답을 JSON으로 강제 -> parse_model_json의 관대 파싱과 이중 안전장치
        response_mime_type="application/json",
    )
    if temperature is not None:
        config.temperature = temperature
    try:
        resp = client.models.generate_content(
            model=model, contents=user_prompt, config=config,
        )
    except Exception as e:
        if temperature is not None and "temperature" in str(e).lower():
            config.temperature = None
            resp = client.models.generate_content(
                model=model, contents=user_prompt, config=config,
            )
        else:
            raise
    text = getattr(resp, "text", None)
    if text:
        return text
    # candidates가 비었거나(safety 차단 등) .text가 없는 경우
    raise RuntimeError(f"Gemini 응답에 텍스트가 없습니다 (finish_reason 확인 필요): {resp}")


def call_llm(provider: str, client, model: str, system_prompt: str, user_prompt: str,
            max_tokens: int, temperature: float | None) -> str:
    if provider == "anthropic":
        return call_claude(client, model, system_prompt, user_prompt, max_tokens, temperature)
    if provider == "gemini":
        return call_gemini(client, model, system_prompt, user_prompt, max_tokens, temperature)
    raise ValueError(f"알 수 없는 provider: {provider}")


def parse_model_json(raw: str) -> dict[str, str]:
    """모델 출력에서 {"translations":[...]} JSON을 관대하게 추출."""
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("응답에서 JSON 객체를 찾지 못했습니다.")
    data = json.loads(s[i:j + 1])
    out: dict[str, str] = {}
    for item in data.get("translations", []):
        sid, txt = item.get("segment_id"), item.get("translated_text")
        if isinstance(sid, str) and isinstance(txt, str) and txt.strip():
            out[sid] = txt
    return out


def translate_all_batches(provider: str, client, args, system_prompt: str, template: str,
                          segments: list[Segment], glossary_text: str) -> None:
    targets = [s for s in segments if s.needs_translation]
    batches = list(make_batches(targets, args.batch_chars, args.batch_segs))
    prev_pairs: list[tuple[str, str]] = []
    total_chars_sent = 0

    for bi, batch in enumerate(batches, 1):
        remaining = {s.seg_id: s for s in batch}
        for attempt in range(1, args.max_attempts + 1):
            todo = list(remaining.values())
            prompt = build_user_prompt(template, args, glossary_text,
                                       render_prev_context(prev_pairs), todo)
            try:
                raw = call_llm(provider, client, args.model, system_prompt, prompt,
                              args.max_tokens, args.temperature)
                mapping = parse_model_json(raw)
            except Exception as e:
                print(f"  [batch {bi}/{len(batches)}] 시도 {attempt} 실패: {e}")
                time.sleep(min(2 ** attempt, 15))
                continue
            for sid, txt in mapping.items():
                if sid in remaining:
                    remaining[sid].translated = txt
            remaining = {k: v for k, v in remaining.items() if v.translated is None}
            if not remaining:
                break
            print(f"  [batch {bi}/{len(batches)}] 누락 {len(remaining)}개 세그먼트 재요청")
        # 최종 실패분은 원문 유지 (문서 손실 방지)
        for s in remaining.values():
            print(f"  [경고] {s.seg_id} 번역 실패 -> 원문 유지")
            s.translated = s.text
        for s in batch:
            prev_pairs.append((s.text[:300], (s.translated or "")[:300]))
        prev_pairs = prev_pairs[-12:]
        total_chars_sent += sum(len(s.text) for s in batch)
        done = sum(1 for s in targets if s.translated is not None)
        print(f"  [batch {bi}/{len(batches)}] 완료 (누적 {done}/{len(targets)} 세그먼트)")

    print(f"[3/4] 번역 완료: {len(targets)}개 세그먼트, 원문 {total_chars_sent:,}자 전송")


def mock_translate(segments: list[Segment]) -> None:
    """API 없이 파이프라인(추출/재구성/한글 폰트)을 검증하기 위한 모의 번역."""
    for s in segments:
        if s.needs_translation:
            s.translated = f"[모의 번역] {s.text}"


# ---------------------------------------------------------------------------
# [4] 재구성
# ---------------------------------------------------------------------------
def hex_to_rgb01(hx: str) -> tuple:
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def apply_redactions_safe(page) -> None:
    """텍스트만 제거하고 이미지/벡터 그래픽은 보존. 구버전 시그니처 폴백 포함."""
    try:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    except (TypeError, AttributeError):
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)


def insert_translated_text(page, seg: Segment, font_scale: float) -> bool:
    """번역문을 원래 bbox에 삽입. True=정상, False=축소 한계 초과(잘림 가능)."""
    rect = pymupdf.Rect(seg.bbox)
    fs = max(4.0, seg.font_size * font_scale)

    if hasattr(page, "insert_htmlbox"):
        body = html_mod.escape(seg.translated or "").replace("\n", "<br>")
        weight = "bold" if seg.bold else "normal"
        css = ("* {" +
               "margin:0;padding:0;font-family:sans-serif;" +
               f"font-size:{fs:.1f}px;color:{seg.color};font-weight:{weight};" +
               "line-height:1.28;}")
        try:
            spare, _scale = page.insert_htmlbox(rect, f"<div>{body}</div>",
                                                css=css, scale_low=0.15)
            return not (spare is not None and spare < 0)
        except Exception:
            pass  # -> 내장 CJK 폰트 폴백

    # 폴백: MuPDF 내장 CJK 폰트("korea")로 크기 축소 반복 삽입
    color = hex_to_rgb01(seg.color)
    size = fs
    while size >= 4.0:
        rc = page.insert_textbox(rect, seg.translated or "", fontsize=size,
                                 fontname="korea", color=color)
        if rc >= 0:
            return True
        size *= 0.88
    page.insert_textbox(rect, seg.translated or "", fontsize=4.0,
                        fontname="korea", color=color)
    return False


def rebuild_pdf(doc, segments: list[Segment], font_scale: float) -> int:
    by_page: dict[int, list[Segment]] = defaultdict(list)
    for s in segments:
        if s.needs_translation and s.translated:
            by_page[s.page].append(s)

    truncated = 0
    for pno in sorted(by_page):
        page = doc[pno]
        for s in by_page[pno]:
            page.add_redact_annot(pymupdf.Rect(s.bbox), fill=False)
        apply_redactions_safe(page)
        for s in by_page[pno]:
            if not insert_translated_text(page, s, font_scale):
                truncated += 1
                print(f"  [경고] {s.seg_id}: 번역문이 원래 영역보다 길어 최대 축소로도 넘칠 수 있음")
    return truncated


# ---------------------------------------------------------------------------
# 보조: 용어집 / 페이지 지정 / 내보내기·가져오기
# ---------------------------------------------------------------------------
def load_glossary(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        sys.exit(f"[오류] 용어집 파일이 없습니다: {path}")
    lines: list[str] = []
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.items() if isinstance(data, dict) else \
            ((d.get("source", ""), d.get("target", "")) for d in data)
        for src, dst in items:
            if src:
                lines.append(f"{src} => {dst}")
    else:  # csv/txt: "source,target" 또는 "source => target"
        for raw in p.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            if "=>" in raw:
                src, dst = raw.split("=>", 1)
            elif "," in raw:
                src, dst = raw.split(",", 1)
            else:
                continue
            lines.append(f"{src.strip()} => {dst.strip()}")
    return "\n".join(lines)


def parse_pages(spec: str | None, page_count: int) -> set[int] | None:
    if not spec:
        return None
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a) - 1, int(b)))
        else:
            out.add(int(part) - 1)
    return {p for p in out if 0 <= p < page_count}


def export_translations(path: str, segments: list[Segment]) -> None:
    payload = {"segments": [
        {"segment_id": s.seg_id, "page": s.page + 1, "source": s.text,
         "translated": s.translated}
        for s in segments if s.needs_translation
    ]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"[i] 번역 결과 JSON 저장: {path}")


def import_translations(path: str, segments: list[Segment]) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    table = {d["segment_id"]: d.get("translated") for d in data.get("segments", [])}
    hit = 0
    for s in segments:
        if s.needs_translation and table.get(s.seg_id):
            s.translated = table[s.seg_id]
            hit += 1
    print(f"[i] JSON에서 {hit}개 세그먼트 번역 로드: {path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(
        description="Anthropic Claude API 기반 레이아웃 보존 PDF 번역기",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("input", help="입력 PDF 경로")
    ap.add_argument("-o", "--output", default=None,
                    help="출력 PDF 경로 (기본: <입력파일명>_translated.pdf)")
    ap.add_argument("--source-lang", default="English", help="원문 언어")
    ap.add_argument("--target-lang", default="Korean", help="번역 대상 언어")
    ap.add_argument("--provider", choices=["anthropic", "gemini"], default="anthropic",
                    help="사용할 API 제공자")
    ap.add_argument("--api-key-file", default=None,
                    help="API 키가 담긴 파일 경로 (미지정 시 ./api.txt 자동 탐색, "
                         "그다음 환경변수 ANTHROPIC_API_KEY/GEMINI_API_KEY)")
    ap.add_argument("--model", default=None,
                    help="모델 ID (미지정 시 provider별 기본값: "
                         f"anthropic={DEFAULT_MODELS['anthropic']}, "
                         f"gemini={DEFAULT_MODELS['gemini']})")
    ap.add_argument("--doc-type", default="technical documentation")
    ap.add_argument("--style", default="formal, professional")
    ap.add_argument("--terminology-policy", default=DEFAULT_TERMINOLOGY_POLICY)
    ap.add_argument("--title", default=None, help="문서 제목 (기본: PDF 메타데이터/파일명)")
    ap.add_argument("--domain", default="general")
    ap.add_argument("--instructions", default="", help="추가 문서별 지시사항")
    ap.add_argument("--glossary", default=None, help="용어집 파일 (.json 또는 .csv/.txt)")
    ap.add_argument("--pages", default=None, help='번역할 페이지 지정 (예: "1-3,7")')
    ap.add_argument("--batch-chars", type=int, default=3500, help="배치당 최대 원문 문자 수")
    ap.add_argument("--batch-segs", type=int, default=25, help="배치당 최대 세그먼트 수")
    ap.add_argument("--max-tokens", type=int, default=8192, help="응답 max_tokens")
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="샘플링 온도. 미지원 모델이면 자동 제거 후 재시도")
    ap.add_argument("--max-attempts", type=int, default=3, help="배치당 최대 재시도 횟수")
    ap.add_argument("--font-scale", type=float, default=1.0,
                    help="삽입 폰트 크기 배율 (번역문이 자주 잘리면 0.9 등으로 축소)")
    ap.add_argument("--translate-all", action="store_true",
                    help="숫자/기호 전용 블록도 API로 전송 (기본은 원문 유지)")
    ap.add_argument("--mock", action="store_true",
                    help="API 호출 없이 '[모의 번역] 원문' 삽입 — 레이아웃/폰트 검증용")
    ap.add_argument("--dry-run", action="store_true", help="추출 결과만 출력하고 종료")
    ap.add_argument("--export-json", default=None, help="번역 결과를 JSON으로 저장")
    ap.add_argument("--import-json", default=None,
                    help="저장된 JSON으로 재구성만 수행 (API 호출 생략)")
    return ap.parse_args()


def main():
    args = parse_args()

    if args.model is None:
        args.model = DEFAULT_MODELS[args.provider]

    in_path = Path(args.input)
    if not in_path.exists():
        sys.exit(f"[오류] 입력 파일이 없습니다: {in_path}")
    out_path = Path(args.output) if args.output else \
        in_path.with_name(in_path.stem + "_translated.pdf")

    doc = pymupdf.open(in_path)
    if doc.needs_pass:
        sys.exit("[오류] 암호화된 PDF입니다. 먼저 암호를 해제하세요 (예: qpdf --decrypt).")
    if args.title is None:
        args.title = (doc.metadata or {}).get("title") or in_path.stem

    # [1] 추출
    page_filter = parse_pages(args.pages, doc.page_count)
    segments = extract_segments(doc, page_filter, args.translate_all)
    n_target = sum(1 for s in segments if s.needs_translation)
    n_skip = len(segments) - n_target
    total_chars = sum(len(s.text) for s in segments if s.needs_translation)
    print(f"[1/4] 추출: {doc.page_count}페이지, 텍스트 블록 {len(segments)}개 "
          f"(번역 대상 {n_target}, 원문 유지 {n_skip}), 원문 약 {total_chars:,}자")
    if n_target == 0:
        sys.exit("[오류] 번역할 텍스트가 없습니다. 스캔(이미지) PDF면 OCR이 먼저 필요합니다.")

    if args.dry_run:
        for s in segments:
            flag = "T" if s.needs_translation else "-"
            preview = s.text.replace("\n", "⏎")[:70]
            print(f"  [{flag}] {s.seg_id}  {s.font_size:>5.1f}pt  {preview}")
        return

    # [2]+[3] 번역
    if args.import_json:
        import_translations(args.import_json, segments)
    elif args.mock:
        print("[2/4] 배치: (mock 모드 — API 호출 생략)")
        mock_translate(segments)
        print("[3/4] 모의 번역 완료")
    else:
        batches = list(make_batches([s for s in segments if s.needs_translation],
                                    args.batch_chars, args.batch_segs))
        print(f"[2/4] 배치: {len(batches)}개 (배치당 최대 {args.batch_chars}자 / "
              f"{args.batch_segs}세그먼트), provider={args.provider}, 모델 {args.model}")
        provider, client = get_client(args)
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        template = USER_TEMPLATE_PATH.read_text(encoding="utf-8")
        glossary_text = load_glossary(args.glossary)
        translate_all_batches(provider, client, args, system_prompt, template,
                              segments, glossary_text)

    if args.export_json:
        export_translations(args.export_json, segments)

    # [4] 재구성
    truncated = rebuild_pdf(doc, segments, args.font_scale)
    try:
        doc.subset_fonts()
    except Exception:
        pass
    doc.save(out_path, garbage=3, deflate=True)
    print(f"[4/4] 재구성 완료 -> {out_path}"
          + (f" (축소 한계 초과 {truncated}개 블록)" if truncated else ""))


if __name__ == "__main__":
    main()
