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
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5.4-mini",
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
@dataclass
class KeyEntry:
    provider: str
    model: str
    client: object
    label: str          # 로그 표기용 (예: "gemini#1", "openai#1", "anthropic#1")
    alive: bool = True   # False = 일일/영구 할당량 소진으로 이번 실행에서 제외


_KEY_PREFIXES = {
    "anthropic": ("sk-ant-",),
    "gemini": ("AIza", "AQ."),
    "openai": ("sk-proj-", "sk-"),  # sk- 는 openai가 마지막 순위(anthropic의 sk-ant-와 겹치므로 순서 중요)
}
_PROVIDER_ALIASES = {"gpt": "openai", "claude": "anthropic", "google": "gemini"}


def detect_provider(key: str) -> str | None:
    """
    'provider:키' 형식이면 명시적으로 그 provider를 쓴다.
    아니면 키 형태(prefix)로 자동 판별한다. sk-ant-(Anthropic) > AIza/AQ.(Gemini) > sk-(OpenAI) 순으로 검사
    (OpenAI 키가 'sk-'로 시작해 Anthropic의 'sk-ant-'와 겹치므로 Anthropic을 먼저 검사).
    """
    if ":" in key:
        prefix, rest = key.split(":", 1)
        p = _PROVIDER_ALIASES.get(prefix.strip().lower(), prefix.strip().lower())
        if p in DEFAULT_MODELS:
            return p
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith(("AIza", "AQ.")):
        return "gemini"
    if key.startswith("sk-"):
        return "openai"
    return None


def strip_provider_prefix(key: str) -> str:
    if ":" in key:
        prefix, rest = key.split(":", 1)
        if _PROVIDER_ALIASES.get(prefix.strip().lower(), prefix.strip().lower()) in DEFAULT_MODELS:
            return rest.strip()
    return key


def _decode_key_file_text(raw: bytes, path: Path) -> str:
    """
    메모장 등에서 저장한 api.txt는 UTF-8이 아닐 수 있다
    (UTF-16 LE/BE + BOM이 흔함, 드물게 UTF-8 BOM이나 CP949).
    BOM으로 우선 판별하고, 없으면 순서대로 시도한다. (전체 텍스트를 반환)
    """
    if raw.startswith(b"\xff\xfe"):
        text = raw.decode("utf-16-le")
    elif raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16-be")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        text = None
        for enc in ("utf-8", "utf-16", "cp949"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            sys.exit(f"[오류] {path}의 인코딩을 판별할 수 없습니다. "
                     f"메모장에서 '다른 이름으로 저장 > 인코딩: UTF-8'로 다시 저장하세요.")
    return text.lstrip("\ufeff")


def load_key_pool(args) -> list[tuple[str, str]]:
    """
    api.txt(또는 --api-key-file)에서 여러 provider의 키를 한 번에 읽어
    [(provider, key), ...] 형태로 반환한다.
    한 줄에 키 하나. 형태로 provider 자동 판별(sk-ant-=anthropic, AIza/AQ.=gemini, sk-=openai).
    'gemini:AIza...'처럼 'provider:키'로 명시할 수도 있다. '#'으로 시작하는 줄은 주석.
    --provider를 명시하면 해당 provider의 키만 사용(기존 단일 provider 동작과 동일).
    파일이 없으면 환경변수(ANTHROPIC_API_KEY/GEMINI_API_KEY/OPENAI_API_KEY, 콤마로 여러 개)로 폴백.
    """
    candidates: list[Path] = []
    if args.api_key_file:
        candidates.append(Path(args.api_key_file))
    else:
        candidates += [Path.cwd() / "api.txt", Path(__file__).resolve().parent / "api.txt"]

    entries: list[tuple[str, str]] = []
    unknown = 0
    for p in candidates:
        if p.is_file():
            text = _decode_key_file_text(p.read_bytes(), p)
            for ln in text.splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                provider = detect_provider(ln)
                if provider is None:
                    unknown += 1
                    print(f"  [경고] 키 형식을 알 수 없어 건너뜀: {ln[:12]}...")
                    continue
                entries.append((provider, strip_provider_prefix(ln)))
            break  # 첫 번째로 발견된 파일만 사용

    if not entries:
        for provider, env_var in (("anthropic", "ANTHROPIC_API_KEY"),
                                  ("gemini", "GEMINI_API_KEY"),
                                  ("openai", "OPENAI_API_KEY")):
            env_val = os.environ.get(env_var) or \
                (os.environ.get("GOOGLE_API_KEY") if provider == "gemini" else None)
            if env_val:
                entries += [(provider, k.strip()) for k in env_val.split(",") if k.strip()]

    if args.provider:
        entries = [e for e in entries if e[0] == args.provider]

    if not entries:
        sys.exit(
            f"[오류] API 키를 찾지 못했습니다"
            f"{f' (provider={args.provider} 필터 적용됨)' if args.provider else ''}. "
            f"다음 중 하나로 제공하세요:\n"
            f"       1) api.txt에 한 줄씩 키 추가 (형태로 provider 자동판별, 또는 'gemini:키'처럼 명시)\n"
            f"       2) export ANTHROPIC_API_KEY=... / GEMINI_API_KEY=... / OPENAI_API_KEY=... (콤마로 여러 개)"
        )
    return entries


def resolve_model(args, provider: str) -> str:
    override = {"anthropic": args.model_anthropic, "gemini": args.model_gemini,
               "openai": args.model_openai}.get(provider)
    if override:
        return override
    if args.model and args.provider == provider:
        return args.model  # 단일 provider로 명시했을 때만 --model 허용 (혼합 풀에서는 모호하므로 무시)
    return DEFAULT_MODELS[provider]


def build_client(provider: str, key: str):
    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            sys.exit("[오류] anthropic SDK가 없습니다. 설치: pip install anthropic")
        return anthropic.Anthropic(api_key=key)
    if provider == "gemini":
        try:
            from google import genai
        except ImportError:
            sys.exit("[오류] google-genai SDK가 없습니다. 설치: pip install google-genai")
        return genai.Client(api_key=key)
    if provider == "openai":
        try:
            from openai import OpenAI as OpenAIClient
        except ImportError:
            sys.exit("[오류] openai SDK가 없습니다. 설치: pip install openai")
        return OpenAIClient(api_key=key)
    sys.exit(f"[오류] 알 수 없는 provider: {provider}")


def get_key_pool(args) -> list[KeyEntry]:
    """api.txt(여러 provider 혼합 가능)를 읽어 KeyEntry 풀을 구성한다."""
    raw_entries = load_key_pool(args)
    counts: dict[str, int] = {}
    pool: list[KeyEntry] = []
    for provider, key in raw_entries:
        counts[provider] = counts.get(provider, 0) + 1
        pool.append(KeyEntry(
            provider=provider,
            model=resolve_model(args, provider),
            client=build_client(provider, key),
            label=f"{provider}#{counts[provider]}",
        ))
    summary = ", ".join(f"{p} {n}개({resolve_model(args, p)})" for p, n in counts.items())
    print(f"[정보] API 키 {len(pool)}개 로드됨 -> {summary} "
          f"({'할당량 초과 시 순환/전환' if len(pool) > 1 else '단일 키'})")
    return pool


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


def call_openai(client, model: str, system_prompt: str, user_prompt: str,
                max_tokens: int, temperature: float | None) -> str:
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        # 응답을 JSON으로 강제 -> parse_model_json의 관대 파싱과 이중 안전장치
        response_format={"type": "json_object"},
    )
    if temperature is not None:
        kwargs["temperature"] = temperature

    def _fix_and_retry(e: Exception, kw: dict) -> "object":
        s = str(e).lower()
        changed = False
        if "temperature" in s and "temperature" in kw:
            kw.pop("temperature", None)
            changed = True
        if "max_tokens" in s and "max_completion_tokens" in s and "max_tokens" in kw:
            # GPT-5.x 등 신형 모델은 max_tokens 대신 max_completion_tokens 사용
            kw["max_completion_tokens"] = kw.pop("max_tokens")
            changed = True
        if not changed:
            raise e
        return client.chat.completions.create(**kw)

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as e:
        try:
            resp = _fix_and_retry(e, kwargs)
        except Exception as e2:
            # 두 파라미터가 동시에 문제였을 수 있으니 한 번 더 시도
            resp = _fix_and_retry(e2, kwargs)
    return resp.choices[0].message.content or ""


def call_llm(provider: str, client, model: str, system_prompt: str, user_prompt: str,
            max_tokens: int, temperature: float | None) -> str:
    if provider == "anthropic":
        return call_claude(client, model, system_prompt, user_prompt, max_tokens, temperature)
    if provider == "gemini":
        return call_gemini(client, model, system_prompt, user_prompt, max_tokens, temperature)
    if provider == "openai":
        return call_openai(client, model, system_prompt, user_prompt, max_tokens, temperature)
    raise ValueError(f"알 수 없는 provider: {provider}")


def parse_model_json(raw: str) -> dict[str, str]:
    """모델 출력에서 {"translations":[...]} JSON을 관대하게 추출."""
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("응답에서 JSON 객체를 찾지 못했습니다.")
    payload = s[i:j + 1]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        if "control character" in str(e).lower():
            # 모델이 문자열 값 안에 이스케이프 안 된 리터럴 개행/탭 등을 그대로 넣은 경우
            # (예: 번역문에 실제 줄바꿈이 포함됨). strict=False로 재시도.
            data = json.loads(payload, strict=False)
        else:
            raise
    out: dict[str, str] = {}
    for item in data.get("translations", []):
        sid, txt = item.get("segment_id"), item.get("translated_text")
        if isinstance(sid, str) and isinstance(txt, str) and txt.strip():
            out[sid] = txt
    return out


def is_rate_limit_error(e: Exception) -> bool:
    """429/할당량 초과류인지 판별. 이 경우는 일반 재시도 횟수를 소진시키지 않는다."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code == 429:
        return True
    s = str(e).lower()
    return any(kw in s for kw in (
        "429", "resource_exhausted", "rate_limit", "rate limit",
        "quota exceeded", "insufficient_quota", "too many requests",
    ))


def is_permanent_exhaustion(e: Exception) -> bool:
    """
    '기다려도 곧 안 풀리는' 종류의 소진인지 판별 (일일 할당량, 크레딧 소진, 결제 한도 등).
    이 경우 해당 키는 이번 실행에서 완전히 제외한다 (반대는 분당 제한 등 일시적 상황).
    휴리스틱이라 완벽하지 않을 수 있음 - 오탐 시 --api-key-file에서 해당 키를 직접 제거할 것.
    """
    s = str(e).lower()
    return any(kw in s for kw in (
        "perday",                 # Gemini: GenerateRequestsPerDayPerProjectPerModel-FreeTier 등
        "insufficient_quota",     # OpenAI: 크레딧/결제 한도 소진
        "credit balance",         # Anthropic: 크레딧 부족
        "billing",                # 공통: 결제 관련 하드 한도
    ))


def extract_retry_delay(e: Exception, default: float = 30.0) -> float:
    """
    서버가 응답에 명시한 대기시간을 파싱한다.
      - Gemini: "...Please retry in 55.998596965s." 또는 'retryDelay': '55s'
      - Anthropic: response.headers['retry-after'] (초)
    못 찾으면 default초 대기.
    """
    s = str(e)
    m = re.search(r"retry in ([\d.]+)\s*s", s, re.IGNORECASE)
    if m:
        return float(m.group(1)) + 2.0  # 여유분 2초
    m = re.search(r"['\"]retryDelay['\"]\s*:\s*['\"](\d+(?:\.\d+)?)s['\"]", s)
    if m:
        return float(m.group(1)) + 2.0
    resp = getattr(e, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else None
    if headers:
        ra = headers.get("retry-after") or headers.get("Retry-After")
        if ra:
            try:
                return float(ra) + 2.0
            except ValueError:
                pass
    return default


def translate_all_batches(pool: list["KeyEntry"], args, system_prompt: str, template: str,
                          segments: list[Segment], glossary_text: str) -> tuple[bool, int | None]:
    """
    반환값: (aborted, abort_page)
      aborted=True면 pool의 모든 키가 영구 소진되어 번역을 중단한 것.
      abort_page는 1-based 페이지 번호(중단 시점에 처리 중이던 배치의 첫 세그먼트 기준).
    """
    targets = [s for s in segments if s.needs_translation]
    batches = list(make_batches(targets, args.batch_chars, args.batch_segs))
    prev_pairs: list[tuple[str, str]] = []
    total_chars_sent = 0
    last_call_time = 0.0
    n_keys = len(pool)
    key_idx = 0  # 배치 간에도 유지

    def next_alive_index(start: int) -> int | None:
        for step in range(n_keys):
            i = (start + step) % n_keys
            if pool[i].alive:
                return i
        return None

    aborted = False
    abort_page: int | None = None

    for bi, batch in enumerate(batches, 1):
        remaining = {s.seg_id: s for s in batch}
        attempt = 0
        rl_retry = 0
        keys_tried_since_success = 0
        while remaining:
            idx = next_alive_index(key_idx)
            if idx is None:
                aborted = True
                abort_page = min(s.page for s in remaining.values()) + 1
                print(f"  [batch {bi}/{len(batches)}] 사용 가능한 API 키가 남지 않음 "
                      f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                break
            key_idx = idx
            entry = pool[key_idx]

            todo = list(remaining.values())
            prompt = build_user_prompt(template, args, glossary_text,
                                       render_prev_context(prev_pairs), todo)

            if args.min_interval > 0:
                wait = args.min_interval - (time.monotonic() - last_call_time)
                if wait > 0:
                    time.sleep(wait)

            try:
                raw = call_llm(entry.provider, entry.client, entry.model, system_prompt, prompt,
                              args.max_tokens, args.temperature)
                last_call_time = time.monotonic()
                mapping = parse_model_json(raw)
                keys_tried_since_success = 0
            except Exception as e:
                last_call_time = time.monotonic()
                if is_rate_limit_error(e):
                    if is_permanent_exhaustion(e):
                        entry.alive = False
                        print(f"  [batch {bi}/{len(batches)}] 키 {entry.label} 일일/영구 할당량 소진 "
                              f"-> 이번 실행에서 제외")
                        nxt = next_alive_index(key_idx + 1)
                        if nxt is None:
                            aborted = True
                            abort_page = min(s.page for s in remaining.values()) + 1
                            print(f"  [batch {bi}/{len(batches)}] 모든 키 소진 "
                                  f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                            break
                        key_idx = nxt
                        continue
                    # 일시적 429(분당 제한 등): 다음 살아있는 키로 즉시 전환
                    rl_retry += 1
                    if args.max_rate_limit_retries and rl_retry > args.max_rate_limit_retries:
                        print(f"  [batch {bi}/{len(batches)}] 일시적 할당량 재시도 한도 "
                              f"({args.max_rate_limit_retries}회) 초과 -> 이 배치 포기")
                        break
                    prev_label = entry.label
                    nxt = next_alive_index(key_idx + 1)
                    if nxt is None:
                        aborted = True
                        abort_page = min(s.page for s in remaining.values()) + 1
                        break
                    key_idx = nxt
                    keys_tried_since_success += 1
                    n_alive = sum(1 for e2 in pool if e2.alive)
                    if keys_tried_since_success % max(n_alive, 1) == 0:
                        delay = extract_retry_delay(e)
                        print(f"  [batch {bi}/{len(batches)}] 살아있는 키 {n_alive}개 전부 "
                              f"일시적 할당량 초과 - {delay:.0f}초 대기 후 재시도")
                        time.sleep(delay)
                    else:
                        print(f"  [batch {bi}/{len(batches)}] 키 {prev_label} 할당량 초과 "
                              f"-> 키 {pool[key_idx].label}로 전환")
                    continue
                attempt += 1
                print(f"  [batch {bi}/{len(batches)}] 시도 {attempt}/{args.max_attempts} "
                      f"({entry.label}) 실패: {e}")
                if attempt >= args.max_attempts:
                    break
                # 같은 키를 반복 재시도하지 않고 다음 살아있는 키로 전환 (키 고유 버그/차단 대비)
                nxt = next_alive_index(key_idx + 1)
                if nxt is not None:
                    key_idx = nxt
                time.sleep(min(2 ** attempt, 15))
                continue

            for sid, txt in mapping.items():
                if sid in remaining:
                    remaining[sid].translated = txt
            remaining = {k: v for k, v in remaining.items() if v.translated is None}
            if remaining:
                print(f"  [batch {bi}/{len(batches)}] 누락 {len(remaining)}개 세그먼트 재요청")

        # 이 배치에서 끝까지 실패/중단된 분은 원문 유지 (문서 손실 방지)
        for s in remaining.values():
            if s.translated is None:
                s.translated = s.text
        for s in batch:
            prev_pairs.append((s.text[:300], (s.translated or "")[:300]))
        prev_pairs = prev_pairs[-12:]
        total_chars_sent += sum(len(s.text) for s in batch)
        done = sum(1 for s in targets if s.translated is not None and s.translated != s.text)
        print(f"  [batch {bi}/{len(batches)}] 완료 (실제 번역 누적 {done}/{len(targets)} 세그먼트)")

        if aborted:
            break

    # 처리되지 못한 이후 배치들도 원문 유지로 채워둔다 (재구성 단계 안전장치)
    for s in targets:
        if s.translated is None:
            s.translated = s.text

    print(f"[3/4] 번역 {'중단됨' if aborted else '완료'}: {len(targets)}개 세그먼트, "
          f"원문 {total_chars_sent:,}자 전송")
    return aborted, abort_page


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
RESUME_FILENAME_RE = re.compile(
    r"^(?P<base>.+?)_(?:translated|T)_(?P<trange>none|\d{3}-\d{3})"
    r"(?:_(?:untranslated|unT)_(?P<urange>\d{3}-\d{3}))?$"
)


def parse_resume_filename(stem: str) -> dict | None:
    """
    '<base>_translated_###-@@@[_untranslated_$$$-%%%]' (또는 축약형 _T_/_unT_) 패턴을
    입력 파일명에서 감지한다. 이어서 번역할 때 재사용.
    """
    m = RESUME_FILENAME_RE.match(stem)
    if not m:
        return None
    trange = m.group("trange")
    if trange == "none":
        t_start = t_end = None
    else:
        a, b = trange.split("-")
        t_start, t_end = int(a), int(b)
    urange = m.group("urange")
    if urange:
        c, d = urange.split("-")
        u_start, u_end = int(c), int(d)
    else:
        u_start = u_end = None
    return {"base": m.group("base"), "t_start": t_start, "t_end": t_end,
            "u_start": u_start, "u_end": u_end}


def build_output_stem(base_stem: str, t_start: int | None, t_end: int | None,
                      u_start: int | None, u_end: int | None) -> str:
    """페이지 범위를 반영한 출력 파일명(확장자 제외) 생성. 너무 길면 _T/_unT로 축약."""
    fmt = lambda n: f"{n:03d}"
    t_part = "_translated_none" if t_start is None else f"_translated_{fmt(t_start)}-{fmt(t_end)}"
    u_part = "" if u_start is None else f"_untranslated_{fmt(u_start)}-{fmt(u_end)}"
    stem = base_stem + t_part + u_part
    if len(stem) > 120:
        stem = base_stem + t_part.replace("_translated", "_T") + u_part.replace("_untranslated", "_unT")
    return stem


def parse_args():
    ap = argparse.ArgumentParser(
        description="Anthropic Claude API 기반 레이아웃 보존 PDF 번역기",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("input", help="입력 PDF 경로")
    ap.add_argument("-o", "--output", default=None,
                    help="출력 PDF 경로 (기본: <입력파일명>_translated.pdf)")
    ap.add_argument("--source-lang", default="English", help="원문 언어")
    ap.add_argument("--target-lang", default="Korean", help="번역 대상 언어")
    ap.add_argument("--provider", choices=["anthropic", "gemini", "openai"], default=None,
                    help="특정 provider로 제한. 미지정 시 api.txt에 있는 모든 provider의 키를 "
                         "섞어서 순환 사용 (할당량 소진 시 다음 provider/키로 자동 전환)")
    ap.add_argument("--api-key-file", default=None,
                    help="API 키가 담긴 파일 경로 (미지정 시 ./api.txt 자동 탐색). "
                         "한 줄에 키 하나, provider는 키 형태로 자동판별 "
                         "(sk-ant-=anthropic, AIza/AQ.=gemini, sk-=openai). "
                         "'gemini:AIza...'처럼 명시도 가능. 파일 없으면 환경변수 "
                         "ANTHROPIC_API_KEY/GEMINI_API_KEY/OPENAI_API_KEY로 폴백")
    ap.add_argument("--model", default=None,
                    help="--provider를 단일 provider로 지정했을 때만 적용되는 모델 오버라이드. "
                         "여러 provider를 섞어 쓸 때는 --model-anthropic/--model-gemini/"
                         "--model-openai를 사용할 것")
    ap.add_argument("--model-anthropic", default=None,
                    help=f"Anthropic 키에 사용할 모델 (기본: {DEFAULT_MODELS['anthropic']})")
    ap.add_argument("--model-gemini", default=None,
                    help=f"Gemini 키에 사용할 모델 (기본: {DEFAULT_MODELS['gemini']})")
    ap.add_argument("--model-openai", default=None,
                    help=f"OpenAI 키에 사용할 모델 (기본: {DEFAULT_MODELS['openai']}, "
                         f"번역용으로 OpenAI가 권장하는 저비용/고품질 균형 모델)")
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
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="배치당 최대 재시도 횟수 (429/할당량 초과는 별도 무제한 처리, 이 값과 무관)")
    ap.add_argument("--min-interval", type=float, default=0.0,
                    help="API 요청 사이 최소 간격(초). 분당 요청 제한(RPM)에 걸리면 "
                         "예: 무료/저티어는 6~10 정도로 설정해 선제적으로 속도 조절")
    ap.add_argument("--max-rate-limit-retries", type=int, default=0,
                    help="429(할당량 초과) 재시도 최대 횟수. 0=무제한 (서버가 알려준 대기시간만큼 "
                         "자동으로 자고 계속 재시도)")
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

    in_path = Path(args.input)
    if not in_path.exists():
        sys.exit(f"[오류] 입력 파일이 없습니다: {in_path}")

    # 이어서 번역: 파일명에 이전 실행의 페이지 범위 정보가 있으면 감지
    resume_info = parse_resume_filename(in_path.stem)
    if resume_info:
        print(f"[정보] 이어서-번역 파일명 감지: 이전 번역완료 "
              f"{resume_info['t_start']}-{resume_info['t_end']}페이지"
              + (f", 미번역 {resume_info['u_start']}-{resume_info['u_end']}페이지"
                 if resume_info['u_start'] else " (전체 완료 상태)"))
        if args.pages is None and resume_info["u_start"] is not None:
            args.pages = f"{resume_info['u_start']}-{resume_info['u_end']}"
            print(f"[정보] --pages 미지정 -> 미번역 구간({args.pages})만 이어서 번역")
    base_stem = resume_info["base"] if resume_info else in_path.stem

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

    if page_filter is None:
        run_first_page, run_last_page = 1, doc.page_count
    else:
        run_first_page, run_last_page = min(page_filter) + 1, max(page_filter) + 1

    # [2]+[3] 번역
    aborted, abort_page = False, None
    if args.import_json:
        import_translations(args.import_json, segments)
    elif args.mock:
        print("[2/4] 배치: (mock 모드 — API 호출 생략)")
        mock_translate(segments)
        print("[3/4] 모의 번역 완료")
    else:
        batches = list(make_batches([s for s in segments if s.needs_translation],
                                    args.batch_chars, args.batch_segs))
        pool = get_key_pool(args)
        print(f"[2/4] 배치: {len(batches)}개 (배치당 최대 {args.batch_chars}자 / "
              f"{args.batch_segs}세그먼트)")
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        template = USER_TEMPLATE_PATH.read_text(encoding="utf-8")
        glossary_text = load_glossary(args.glossary)
        aborted, abort_page = translate_all_batches(pool, args, system_prompt, template,
                                                     segments, glossary_text)

    if args.export_json:
        export_translations(args.export_json, segments)

    # 이번 실행에서의 번역/미번역 페이지 범위 계산
    if aborted:
        run_t_start, run_t_end = (run_first_page, abort_page - 1) if abort_page > run_first_page \
            else (None, None)
        run_u_start, run_u_end = abort_page, run_last_page
    else:
        run_t_start, run_t_end = run_first_page, run_last_page
        run_u_start, run_u_end = None, None

    # 이어서-번역 상황이면 이전 실행의 번역완료 구간과 이번 결과를 합친다
    if resume_info:
        if run_t_start is not None:
            final_t_start = resume_info["t_start"] if resume_info["t_start"] is not None else run_t_start
            final_t_end = run_t_end
        else:
            final_t_start, final_t_end = resume_info["t_start"], resume_info["t_end"]
        final_u_start, final_u_end = run_u_start, run_u_end
    else:
        final_t_start, final_t_end = run_t_start, run_t_end
        final_u_start, final_u_end = run_u_start, run_u_end

    # [4] 재구성
    truncated = rebuild_pdf(doc, segments, args.font_scale)
    try:
        doc.subset_fonts()
    except Exception:
        pass

    if args.output:
        out_path = Path(args.output)
    else:
        out_stem = build_output_stem(base_stem, final_t_start, final_t_end,
                                     final_u_start, final_u_end)
        out_path = in_path.with_name(out_stem + in_path.suffix)

    doc.save(out_path, garbage=3, deflate=True)
    status = "번역 중단(할당량 소진)" if aborted else "완료"
    print(f"[4/4] 재구성 {status} -> {out_path}"
          + (f" (축소 한계 초과 {truncated}개 블록)" if truncated else ""))
    if aborted:
        print(f"[안내] {final_u_start}-{final_u_end}페이지는 원문 그대로 저장됨. "
              f"할당량 회복 후 이 출력 파일을 다시 입력으로 넣으면 자동으로 이어서 번역함:")
        print(f"       python {Path(__file__).name} \"{out_path}\" --provider {args.provider or '(생략, 전체 키 사용)'}")


if __name__ == "__main__":
    main()
