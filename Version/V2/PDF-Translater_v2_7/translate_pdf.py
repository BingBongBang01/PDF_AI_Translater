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
import shutil
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
SYSTEM_PROMPT_LOCAL_PATH = SCRIPT_DIR / "prompts" / "system_prompt_local.txt"
USER_TEMPLATE_PATH = SCRIPT_DIR / "prompts" / "user_template.txt"

# 어떤 문자 체계든 '글자'가 하나라도 있는지 검사 (숫자/기호만 있는 블록은 번역 생략)
LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5.4-mini",
    "local": "gemma4-it-e2b-FLM",  # Lemonade/FastFlowLM NPU 모델 이름
}
DEFAULT_MODEL = DEFAULT_MODELS["anthropic"]  # 하위 호환용

# 로컬 NPU(Lemonade 서버) 관련 기본값
LEMONADE_DEFAULT_PORT = 13305  # 신버전(C++) Lemonade Server 기본 포트 (구버전 Python 서버는 8000이었음)
LEMONADE_SERVE_CMD = "LemonadeServer"  # 신버전(C++) 실제 서버 실행파일. 'lemonade'는 그 서버에 말 거는 클라이언트일 뿐 서버 본체가 아님
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
    translation_failed: bool = False   # True면 API 실패/할당량소진 등으로 원문을 그대로 유지한 것


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


_SENTENCE_END_RE = re.compile(r'[.!?:;"\u201d\u2026]\s*$')


def merge_adjacent_segments(segments: list[Segment]) -> list[Segment]:
    """
    PDF 원본이 한 문장을 여러 텍스트 블록으로 쪼개놓은 경우(앞 블록이 마침표 없이 끝남),
    번역 품질 저하와 조각 번역 실패("mark." 잔여 현상)를 막기 위해 보수적으로 병합한다.

    병합 조건 (전부 만족해야 함 - 오탐으로 레이아웃을 깨느니 놓치는 쪽을 택함):
      * 같은 페이지의 '연속된' 세그먼트이고 둘 다 번역 대상
      * 앞 블록이 문장 종결 부호(.!?:;"…)로 끝나지 않음 (문장이 중간에서 끊겼다는 신호)
      * 폰트 크기(±0.6pt)/굵기/색이 동일
      * 세로 간격이 폰트 크기의 1.8배 미만 (같은 문단 흐름)
      * 가로 범위가 충분히 겹침 (다단 레이아웃 오병합 방지)
      * 병합 후 영역(union bbox)이 다른 어떤 세그먼트와도 겹치지 않음
      * 병합 결과가 2,000자 이하 (지나치게 큰 덩어리 방지)
    """
    if not segments:
        return segments

    def x_overlap_ratio(a, b) -> float:
        left, right = max(a[0], b[0]), min(a[2], b[2])
        if right <= left:
            return 0.0
        return (right - left) / max(min(a[2] - a[0], b[2] - b[0]), 1e-6)

    merged: list[Segment] = []
    absorbed: set[int] = set()  # 병합되어 사라진 세그먼트의 id() (conflict 체크에서 제외)
    n_merged = 0
    for seg in segments:
        prev = merged[-1] if merged else None
        can_merge = (
            prev is not None
            and prev.page == seg.page
            and prev.needs_translation and seg.needs_translation
            and not _SENTENCE_END_RE.search(prev.text)
            and abs(prev.font_size - seg.font_size) <= 0.6
            and prev.bold == seg.bold
            and prev.color == seg.color
            and (seg.bbox[1] - prev.bbox[3]) < prev.font_size * 1.8
            and (seg.bbox[1] - prev.bbox[3]) > -prev.font_size  # 겹치는 역순 배치 방지
            and x_overlap_ratio(prev.bbox, seg.bbox) > 0.5
            and len(prev.text) + len(seg.text) <= 2000
        )
        if can_merge:
            union = (min(prev.bbox[0], seg.bbox[0]), min(prev.bbox[1], seg.bbox[1]),
                     max(prev.bbox[2], seg.bbox[2]), max(prev.bbox[3], seg.bbox[3]))
            # union이 (병합 대상/이미 흡수된 것 제외) 다른 세그먼트와 겹치면 병합 포기.
            # 단, PDF에서 인접 줄의 bbox가 1~2pt 겹치는 건 정상이므로 2pt 허용 오차를 둔다.
            def intersects(b1, b2, tol=2.0):
                return not (b1[2] - tol <= b2[0] or b2[2] - tol <= b1[0]
                            or b1[3] - tol <= b2[1] or b2[3] - tol <= b1[1])
            conflict = any(
                intersects(union, o.bbox) for o in segments
                if o is not prev and o is not seg and id(o) not in absorbed
                and o.page == seg.page
            )
            if not conflict:
                prev.text = prev.text.rstrip() + " " + seg.text.lstrip()
                prev.bbox = union
                absorbed.add(id(seg))
                n_merged += 1
                continue
        merged.append(seg)

    if n_merged:
        print(f"[정보] 문장 단절 블록 {n_merged}쌍 병합됨 (마침표 없이 끊긴 인접 블록)")
    return merged


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
    label: str          # 로그 표기용 (예: "gemini#1", "openai#1", "anthropic#1", "local-NPU")
    alive: bool = True   # False = 일일/영구 할당량 소진으로 이번 실행에서 제외
    is_local: bool = False  # True = 로컬 NPU(Lemonade). 클라우드 키가 전부 죽은 뒤에만 사용


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
        if getattr(args, "local_npu", False) and not getattr(args, "no_local_npu", False):
            print("[정보] 클라우드 API 키를 찾지 못함 -> --local-npu 지정됨, 로컬 NPU만으로 진행")
            return []
        sys.exit(
            f"[오류] API 키를 찾지 못했습니다"
            f"{f' (provider={args.provider} 필터 적용됨)' if args.provider else ''}. "
            f"다음 중 하나로 제공하세요:\n"
            f"       1) api.txt에 한 줄씩 키 추가 (형태로 provider 자동판별, 또는 'gemini:키'처럼 명시)\n"
            f"       2) export ANTHROPIC_API_KEY=... / GEMINI_API_KEY=... / OPENAI_API_KEY=... (콤마로 여러 개)\n"
            f"       3) 클라우드 키 없이 로컬 NPU만 쓰려면 --local-npu 를 추가하세요"
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
    if pool:
        summary = ", ".join(f"{p} {n}개({resolve_model(args, p)})" for p, n in counts.items())
        print(f"[정보] API 키 {len(pool)}개 로드됨 -> {summary} "
              f"({'할당량 초과 시 순환/전환' if len(pool) > 1 else '단일 키'})")
    return pool


# ---------------------------------------------------------------------------
# 로컬 NPU (Lemonade / FastFlowLM) 자동 기동
# ---------------------------------------------------------------------------
_LEMONADE_PROC = None  # 스크립트가 직접 띄운 서버 프로세스 (없으면 None = 이미 켜져 있던 것)


def lemonade_base_url(port: int) -> str:
    return f"http://localhost:{port}/api/v1"


def is_lemonade_up(port: int) -> bool:
    """서버가 이미 떠서 응답하는지 확인."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/api/v1/models", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _tail_file(path: Path, n_lines: int = 25) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n_lines:]) if lines else "(로그가 비어 있음)"
    except Exception as e:
        return f"(로그 읽기 실패: {e})"


def _try_start_one(exe: str, extra_args: list[str], port: int, args) -> bool:
    """한 개의 실행 명령으로 서버 기동을 시도. 성공하면 True."""
    global _LEMONADE_PROC
    import subprocess

    serve_args = [exe] + list(extra_args)
    if port != LEMONADE_DEFAULT_PORT and "--port" not in extra_args:
        serve_args += ["--port", str(port)]
    log_path = Path(args.input).with_suffix(".lemonade.log")
    print(f"[로컬] 기동 시도: {' '.join(serve_args)} (포트 {port})")

    # 한국어 Windows에서 자식 프로세스의 stdout이 파일로 리다이렉트되면 기본 인코딩이 cp949가 되어
    # (구버전) lemonade-server-dev 내부 print()의 유니코드 문자(예: '•')에서 UnicodeEncodeError로 즉시 죽는다.
    # UTF-8을 강제해 이 크래시를 막는다.
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"

    try:
        logf = open(log_path, "w", encoding="utf-8")
        creationflags = 0
        if os.name == "nt":
            # 콘솔 창을 새로 열지 않고 백그라운드로 (CREATE_NO_WINDOW), 프로세스 그룹 분리
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW
        _LEMONADE_PROC = subprocess.Popen(
            serve_args, stdout=logf, stderr=subprocess.STDOUT,
            creationflags=creationflags, env=child_env,
        )
    except Exception as e:
        print(f"[로컬][오류] '{exe}' 실행 자체 실패: {e}")
        return False

    print("[로컬] 서버 준비 대기 중 (최대 180초, 첫 실행은 모델 초기화로 오래 걸릴 수 있음)...")
    for _ in range(180):
        if is_lemonade_up(port):
            print("[로컬] 서버 준비 완료")
            return True
        if _LEMONADE_PROC.poll() is not None:
            print(f"[로컬][오류] '{exe}' 프로세스가 조기 종료됨 (exit code {_LEMONADE_PROC.returncode}).")
            print(f"[로컬] --- 서버 로그 (마지막 25줄) ---")
            print(_tail_file(log_path))
            print(f"[로컬] --- 로그 끝 (전체: {log_path}) ---")
            _LEMONADE_PROC = None
            return False
        time.sleep(1)
    print(f"[로컬][오류] 서버가 제한 시간 내에 준비되지 않음. 로그 확인: {log_path}")
    return False


def load_local_model(args) -> bool:
    """
    /api/v1/load로 모델을 명시적 컨텍스트 크기와 함께 로드한다.
    번역 엔진 프롬프트가 길기 때문에 기본 컨텍스트(보통 4096 이하)로는
    시스템 프롬프트 뒤쪽(JSON 출력 지시)이 잘려나가 모델이 JSON이 아닌 일반 텍스트로
    응답하는 문제가 생길 수 있다. 컨텍스트를 넉넉히 키워서 이를 방지한다.

    주의: FLM(FastFlowLM) 레시피는 llamacpp 전용 필드인 'ctx_size'를 받지 않고
    'flm_args'로 '--ctx-len N'을 전달해야 한다(다르면 422 Unprocessable Entity).
    모델 이름이 'FLM'을 포함하면 flm_args로, 아니면 llamacpp의 ctx_size로 시도한다.
    """
    import urllib.request
    model = args.model_local or DEFAULT_MODELS["local"]
    is_flm = "flm" in model.lower()
    if is_flm:
        payload_dict = {"model": model, "flm_args": f"--ctx-len {args.local_ctx_size}"}
    else:
        payload_dict = {"model": model, "ctx_size": args.local_ctx_size}
    payload = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{args.local_port}/api/v1/load",
        data=payload, method="POST", headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            ok = r.status == 200
            if ok:
                print(f"[로컬] 모델 로드 완료: {model} (컨텍스트 {args.local_ctx_size}, "
                      f"{'flm_args' if is_flm else 'ctx_size'} 방식)")
            else:
                print(f"[로컬][경고] 모델 로드 응답 코드 {r.status} (기존 로드 설정으로 계속 진행)")
            return ok
    except Exception as e:
        # 방식이 틀렸을 수 있으니 반대 방식으로 1회 재시도
        alt_dict = {"model": model, "ctx_size": args.local_ctx_size} if is_flm \
            else {"model": model, "flm_args": f"--ctx-len {args.local_ctx_size}"}
        try:
            alt_req = urllib.request.Request(
                f"http://localhost:{args.local_port}/api/v1/load",
                data=json.dumps(alt_dict).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(alt_req, timeout=120) as r:
                if r.status == 200:
                    print(f"[로컬] 모델 로드 완료 (대체 방식: {list(alt_dict.keys())[-1]})")
                    return True
        except Exception:
            pass
        print(f"[로컬][경고] 명시적 컨텍스트 로드 실패, 기존 로드 상태로 계속 진행: {e}")
        return False


def ensure_lemonade_server(args) -> bool:
    """
    로컬 Lemonade 서버가 떠 있으면 재사용, 없으면 백그라운드로 자동 기동한다.
    여러 실행 명령 후보를 순서대로 시도하고, 하나라도 성공하면 True.
    실행파일마다 필요한 인자가 달라서 (exe, extra_args) 쌍으로 관리한다:
      - LemonadeServer(신버전 C++ 서버 본체): 인자 없이 실행하면 바로 서버가 뜬다.
      - lemonade-server-dev(구버전 Python, deprecated, wmic 의존성 문제 있음): 'serve' 서브커맨드 필요.
    'lemonade.exe'(신버전 CLI)는 서버가 아니라 이미 떠 있는 서버에 말 거는 클라이언트라 후보에서 제외한다.
    """
    port = args.local_port
    if is_lemonade_up(port):
        print(f"[로컬] 이미 실행 중인 Lemonade 서버 감지 (포트 {port}) -> 재사용")
        prepare_local_model(args)
        return True

    if args.local_serve_cmd:
        candidates = [(args.local_serve_cmd, [])]
    else:
        candidates = [
            (LEMONADE_SERVE_CMD, []),           # 신버전 C++ 서버 본체 (인자 없이 실행)
            ("lemonade-server-dev", ["serve"]),  # 구버전 Python 서버 (wmic 의존성 문제로 최후순위)
        ]
    found = [(exe, extra) for exe, extra in candidates if shutil.which(exe)]
    if not found:
        names = ", ".join(c[0] for c in candidates)
        print(f"[로컬][오류] Lemonade 서버 실행파일을 찾지 못했습니다 (시도: {names}).")
        print(f"[로컬] 해결책: 별도 터미널에서 'LemonadeServer'(또는 트레이 앱)를 먼저 켜두면 "
              f"이 스크립트가 그 서버를 자동 감지해 재사용합니다.")
        return False

    for exe, extra in found:
        if _try_start_one(exe, extra, port, args):
            prepare_local_model(args)
            return True
        # 이 후보가 실패했지만 그 사이 다른 프로세스가 포트를 잡았을 수도 있으니 재확인
        if is_lemonade_up(port):
            print(f"[로컬] 서버가 포트 {port}에 떠 있음 -> 재사용")
            prepare_local_model(args)
            return True

    print(f"[로컬][오류] 모든 기동 명령({', '.join(c[0] for c in found)})이 실패했습니다.")
    print(f"[로컬] 위 서버 로그를 확인하세요. 흔한 원인:")
    print(f"        - 포트 {port} 이미 사용 중(트레이에 서버가 이미 실행 중) -> 그 서버를 재사용해야 하는데 감지 실패")
    print(f"        - 메모리 부족(다른 앱, 특히 브라우저를 닫고 재시도)")
    print(f"        - 해결이 안 되면 수동으로 서버(LemonadeServer 또는 트레이 앱)를 먼저 켜두고 이 스크립트를 다시 실행")
    return False


def shutdown_lemonade_server():
    """스크립트가 직접 띄운 서버만 종료 (원래 켜져 있던 건 건드리지 않음)."""
    global _LEMONADE_PROC
    if _LEMONADE_PROC is not None:
        print("[로컬] 자동 기동한 Lemonade 서버 종료")
        try:
            _LEMONADE_PROC.terminate()
            _LEMONADE_PROC.wait(timeout=10)
        except Exception:
            try:
                _LEMONADE_PROC.kill()
            except Exception:
                pass
        _LEMONADE_PROC = None


def make_local_entry(args) -> KeyEntry:
    """로컬 NPU용 KeyEntry 생성 (OpenAI 호환 클라이언트를 로컬 엔드포인트로 지정)."""
    from openai import OpenAI as OpenAIClient
    model = args.model_local or DEFAULT_MODELS["local"]
    client = OpenAIClient(base_url=lemonade_base_url(args.local_port), api_key="lemonade",
                          timeout=args.local_timeout, max_retries=0)
    return KeyEntry(provider="openai", model=model, client=client,
                    label="local-NPU", is_local=True)


# ---------------------------------------------------------------------------
# 로컬 모델 선택 메뉴 + 양자화 프리셋
# ---------------------------------------------------------------------------
# 양자화 비트별 로컬 처리 파라미터 (낮은 비트 = 낮은 품질/불안정 -> 작게 나눠서 실패 파장 축소)
_QUANT_PRESETS = {
    2: {"batch_chars": 700,  "batch_segs": 4,  "max_tokens": 2048},
    4: {"batch_chars": 1500, "batch_segs": 10, "max_tokens": 4096},
    8: {"batch_chars": 2500, "batch_segs": 16, "max_tokens": 6144},
}
_QUANT_RE = re.compile(r'(?:^|[-_.])(?:q|int)(\d)(?:[-_.\d]|bit|$)', re.IGNORECASE)


def detect_quant_bits(model_name: str) -> int | None:
    """
    모델명에서 양자화 비트 감지 (q4_1, Q8_0, int4, 4bit 등).
    주의: 'e2b'/'e4b'(Gemma의 effective 파라미터 수)나 '-4B'(파라미터 수)와
    혼동하지 않도록 q/int 접두어가 있는 경우만 매칭한다.
    """
    m = _QUANT_RE.search(model_name)
    if m:
        bits = int(m.group(1))
        if 1 <= bits <= 8:
            return bits
    return None


def local_presets_for(model_name: str) -> dict:
    """
    양자화 비트에 따른 배치/토큰 프리셋 반환. 2/4/8비트는 고정값,
    그 사이 비트(3,5,6,7)는 인접 두 프리셋의 선형 보간.
    감지 실패 시 4비트 프리셋 사용 (FLM 기본 양자화가 Q4_1이므로 합리적 기본값).
    """
    bits = detect_quant_bits(model_name)
    if bits is None:
        bits = 4
        print(f"[로컬] 모델명에서 양자화 비트를 감지하지 못함 -> 4비트 프리셋 사용 (FLM 기본 Q4 가정)")
    if bits in _QUANT_PRESETS:
        preset = dict(_QUANT_PRESETS[bits])
    else:
        # 선형 보간 (예: 3비트 = 2비트와 4비트의 중간)
        lo = max(b for b in _QUANT_PRESETS if b < bits)
        hi = min(b for b in _QUANT_PRESETS if b > bits)
        t = (bits - lo) / (hi - lo)
        preset = {k: int(_QUANT_PRESETS[lo][k] + t * (_QUANT_PRESETS[hi][k] - _QUANT_PRESETS[lo][k]))
                  for k in _QUANT_PRESETS[lo]}
    print(f"[로컬] 양자화 {bits}비트 프리셋 적용: 청크 {preset['batch_chars']}자/"
          f"{preset['batch_segs']}세그먼트, max_tokens {preset['max_tokens']}")
    return preset


def timed_input(prompt: str, timeout: float) -> str | None:
    """
    timeout초 안에 입력이 없으면 None 반환. Windows(msvcrt)와 POSIX(select) 모두 지원.
    """
    print(prompt, end="", flush=True)
    if os.name == "nt":
        import msvcrt
        buf = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                ch = msvcrt.getwche()
                if ch in ("\r", "\n"):
                    print()
                    return buf.strip()
                elif ch == "\b":
                    buf = buf[:-1]
                else:
                    buf += ch
            time.sleep(0.05)
        print()
        return None
    else:
        import select
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            return sys.stdin.readline().strip()
        print()
        return None


def fetch_local_models(port: int) -> list[str]:
    """서버의 /api/v1/models에서 사용 가능한 모델 ID 목록을 가져온다."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/api/v1/models", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        items = data.get("data", data if isinstance(data, list) else [])
        ids = []
        for it in items:
            mid = it.get("id") if isinstance(it, dict) else str(it)
            if mid:
                ids.append(mid)
        return ids
    except Exception as e:
        print(f"[로컬][경고] 모델 목록 조회 실패: {e}")
        return []


def fetch_loaded_local_model(port: int) -> str | None:
    """Lemonade 모델 목록 응답에서 현재 로드/실행 중인 모델을 최대한 보수적으로 감지한다."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/api/v1/models", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        items = data.get("data", data if isinstance(data, list) else [])
        for it in items:
            if not isinstance(it, dict):
                continue
            mid = it.get("id") or it.get("model")
            status = str(it.get("status", "")).lower()
            loaded = it.get("loaded") is True or it.get("is_loaded") is True
            active = it.get("active") is True or it.get("is_active") is True
            if mid and (loaded or active or status in {"loaded", "running", "active", "ready"}):
                return str(mid)
        # 일부 Lemonade 버전은 최상위 필드로 현재 모델을 반환할 수 있음
        for key in ("loaded_model", "active_model", "model"):
            if isinstance(data, dict) and data.get(key):
                return str(data[key])
    except Exception as e:
        print(f"[로컬][경고] 로드된 모델 감지 실패: {e}")
    return None


def prepare_local_model(args) -> None:
    """로드된 모델을 최우선 기본값으로 선택하고, 필요할 때만 모델을 로드한다."""
    loaded_model = fetch_loaded_local_model(args.local_port)
    if loaded_model:
        print(f"[로컬] 현재 로드된 모델 감지: {loaded_model} -> 최우선 기본값")
        args.model_local = loaded_model
    selected = choose_local_model(args)
    args.model_local = selected
    if loaded_model == selected:
        print(f"[로컬] 이미 로드된 모델 재사용: {selected}")
        return
    load_local_model(args)


def choose_local_model(args) -> str:
    """
    서버의 모델 목록을 번호로 보여주고, 제한시간 안에 번호 입력이 없으면 기본 모델로 진행.
    """
    default_model = args.model_local or DEFAULT_MODELS["local"]
    models = fetch_local_models(args.local_port)
    if not models:
        print(f"[로컬] 모델 목록을 못 가져와 기본 모델로 진행: {default_model}")
        return default_model

    # 기본 모델을 목록 맨 위로
    if default_model in models:
        models.remove(default_model)
        models.insert(0, default_model)

    print(f"[로컬] 사용 가능한 모델 (기본값: 1번 {default_model}):")
    for i, m in enumerate(models, 1):
        marker = " (기본값)" if m == default_model else ""
        print(f"  {i}. {m}{marker}")
    ans = timed_input(f"[로컬] 번호 입력 ({args.model_select_timeout:.0f}초 내 미입력 시 기본값): ",
                      args.model_select_timeout)
    if ans:
        try:
            idx = int(ans)
            if 1 <= idx <= len(models):
                print(f"[로컬] 선택됨: {models[idx - 1]}")
                return models[idx - 1]
        except ValueError:
            # 번호가 아니라 모델명을 직접 친 경우도 허용
            if ans in models:
                print(f"[로컬] 선택됨: {ans}")
                return ans
        print(f"[로컬] 잘못된 입력 '{ans}' -> 기본값으로 진행")
    else:
        print(f"[로컬] 입력 없음 -> 기본값으로 진행: {default_model}")
    return default_model


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
    # Qwen3 등 일부 로컬 모델은 <think>...</think> 사고과정 블록을 앞에 붙인다 -> 제거
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        preview = raw.strip()[:300].replace("\n", "\\n")
        raise ValueError(f"응답에서 JSON 객체를 찾지 못했습니다. 실제 응답(앞 300자): {preview!r}")
    payload = s[i:j + 1]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        if "control character" in str(e).lower():
            # 모델이 문자열 값 안에 이스케이프 안 된 리터럴 개행/탭 등을 그대로 넣은 경우
            # (예: 번역문에 실제 줄바꿈이 포함됨). strict=False로 재시도.
            data = json.loads(payload, strict=False)
        else:
            preview = payload[:300].replace("\n", "\\n")
            raise ValueError(f"JSON 파싱 실패({e}). 추출된 부분(앞 300자): {preview!r}") from e
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
    '이 키로는 계속 시도해도 절대 안 되는' 종류인지 판별
    (일일 할당량 소진, 크레딧/결제 한도, 또는 키 자체가 잘못됨/차단됨).
    이 경우 해당 키는 이번 실행에서 완전히 제외한다 (반대는 분당 제한 등 일시적 상황).
    휴리스틱이라 완벽하지 않을 수 있음 - 오탐 시 --api-key-file에서 해당 키를 직접 제거할 것.
    """
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code in (401, 403):
        return True
    s = str(e).lower()
    return any(kw in s for kw in (
        "perday",                       # Gemini: GenerateRequestsPerDayPerProjectPerModel-FreeTier 등
        "insufficient_quota",           # OpenAI: 크레딧/결제 한도 소진
        "credit balance",               # Anthropic: 크레딧 부족
        "billing",                      # 공통: 결제 관련 하드 한도
        "401",                          # 인증 실패 (잘못된/만료된 키)
        "unauthenticated",              # Gemini: 인증 자격 증명 오류
        "unauthorized",
        "invalid_api_key", "invalid api key", "api key not valid",
        "access_token_type_unsupported",
        "permission_denied", "denied access",  # 403: 프로젝트/키 자체가 차단됨
        "invalid authentication credentials",
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


def _is_context_or_400_error(e: Exception) -> bool:
    """
    청크가 너무 커서 나는 종류의 오류인지 판별 (컨텍스트 초과, 400 Bad Request,
    413 Payload Too Large 등). 이 경우 청크를 반으로 쪼개 재시도하면 해결될 수 있다.
    """
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code in (400, 413, 422):
        return True
    s = str(e).lower()
    return any(kw in s for kw in (
        "400", "413", "422", "context", "too long", "too large", "maximum length",
        "token limit", "exceeds", "payload",
    ))


def translate_local_chunked(entry: "KeyEntry", args, system_prompt_local: str,
                            template: str, glossary_text: str, prev_context: str,
                            todo: list[Segment], presets: dict) -> tuple[dict[str, str], set[str]]:
    """
    로컬 NPU용 청크 처리: todo를 양자화 프리셋(batch_chars/batch_segs)에 맞춰
    작은 청크로 나눠 순차 호출하고, 400/컨텍스트 오류가 나면 해당 청크를
    반으로 쪼개 재귀적으로 재시도한다 (1개까지 쪼개도 실패하면 그 세그먼트만 포기).
    반환: (합쳐진 seg_id->번역문 매핑, 포기한 seg_id 집합).
    포기 집합을 돌려주지 않으면 호출측 while 루프가 같은 세그먼트를 무한 재요청하게 된다.
    """
    chunks: list[list[Segment]] = []
    cur, cur_chars = [], 0
    for s in todo:
        if cur and (cur_chars + len(s.text) > presets["batch_chars"]
                    or len(cur) >= presets["batch_segs"]):
            chunks.append(cur)
            cur, cur_chars = [], 0
        cur.append(s)
        cur_chars += len(s.text)
    if cur:
        chunks.append(cur)

    result: dict[str, str] = {}
    given_up: set[str] = set()

    def run_chunk(chunk: list[Segment], depth: int = 0):
        prompt = build_user_prompt(template, args, glossary_text, prev_context, chunk)
        try:
            raw = call_llm(entry.provider, entry.client, entry.model,
                          system_prompt_local, prompt,
                          presets["max_tokens"], args.temperature)
            result.update(parse_model_json(raw))
        except Exception as e:
            if _is_context_or_400_error(e) and len(chunk) > 1 and depth < 4:
                mid = len(chunk) // 2
                print(f"    [로컬] 청크 오류({str(e)[:80]}) -> {len(chunk)}세그먼트를 "
                      f"반으로 쪼개 재시도")
                run_chunk(chunk[:mid], depth + 1)
                run_chunk(chunk[mid:], depth + 1)
            elif len(chunk) == 1:
                print(f"    [로컬] 세그먼트 {chunk[0].seg_id} 번역 실패(원문 유지 예정): "
                      f"{str(e)[:120]}")
                given_up.add(chunk[0].seg_id)
            else:
                raise  # 컨텍스트류가 아닌 오류는 상위 재시도 로직에 위임

    total = len(chunks)
    for ci, chunk in enumerate(chunks, 1):
        if total > 1:
            print(f"    [로컬] 청크 {ci}/{total} ({len(chunk)}세그먼트) 처리 중...")
        run_chunk(chunk)
    return result, given_up


def translate_all_batches(pool: list["KeyEntry"], args, system_prompt: str, template: str,
                          segments: list[Segment], glossary_text: str,
                          system_prompt_local: str | None = None) -> bool:
    """
    반환값: aborted (pool의 모든 키가 영구 소진되어 나머지 배치를 건너뛰고 중단했는지 여부).
    어떤 이유로든(할당량 소진, 일반 오류, JSON 파싱 실패 등) 결국 원문으로 남은 세그먼트는
    s.translation_failed=True로 표시되며, 이는 main()에서 페이지 단위로 집계해
    출력 파일명의 미번역 구간을 만드는 데 쓰인다.
    로컬 NPU 엔트리는 컨텍스트가 짧고 소형 모델이라 system_prompt_local(축약판, 없으면
    system_prompt와 동일)을 사용한다.
    """
    system_prompt_local = system_prompt_local or system_prompt
    targets = [s for s in segments if s.needs_translation]
    batches = list(make_batches(targets, args.batch_chars, args.batch_segs))
    prev_pairs: list[tuple[str, str]] = []
    total_chars_sent = 0
    last_call_time = 0.0
    n_keys = len(pool)
    key_idx = 0  # 배치 간에도 유지
    local_started = {"done": False, "presets": None}  # 로컬 서버를 아직 안 깨웠으면 done=False

    def next_alive_index(start: int) -> int | None:
        """
        살아있는 키 중 다음 것을 고른다. 단 클라우드 키를 항상 로컬보다 우선한다
        (로컬 NPU는 클라우드가 전부 죽은 최후의 폴백).
        """
        cloud = [i for i in range(n_keys) if pool[i].alive and not pool[i].is_local]
        local = [i for i in range(n_keys) if pool[i].alive and pool[i].is_local]
        if cloud:
            # start 이상에서 첫 클라우드 키, 없으면 처음부터 (라운드로빈)
            for i in range(start, start + n_keys):
                j = i % n_keys
                if j in cloud:
                    return j
            return cloud[0]
        # 클라우드가 전부 죽음 -> 로컬 사용 (필요 시 서버 기동)
        if local:
            if not local_started["done"]:
                had_cloud = any(not e.is_local for e in pool)
                reason = "클라우드 API 전부 소진" if had_cloud else "클라우드 API 키 없음"
                print(f"  [폴백] {reason} -> 로컬 NPU로 전환 시도")
                if not ensure_lemonade_server(args):
                    # 서버 기동 실패 -> 로컬도 못 쓰므로 죽은 것으로 처리
                    for i in local:
                        pool[i].alive = False
                    return None
                # 메뉴에서 선택된(또는 기본) 모델을 로컬 엔트리에 반영 + 양자화 프리셋 계산
                chosen = args.model_local or DEFAULT_MODELS["local"]
                for i in local:
                    pool[i].model = chosen
                local_started["presets"] = local_presets_for(chosen)
                local_started["done"] = True
            return local[0]
        return None

    aborted = False
    abort_page: int | None = None

    for bi, batch in enumerate(batches, 1):
        remaining = {s.seg_id: s for s in batch}
        attempt = 0
        rl_retry = 0
        keys_tried_since_success = 0
        no_progress = 0  # 성공 응답인데 remaining이 줄지 않은 연속 횟수 (모델의 세그먼트 누락 반복 감지)
        while remaining:
            idx = next_alive_index(key_idx)
            if idx is None:
                aborted = True
                abort_page = min(s.page for s in remaining.values()) + 1
                print(f"  [batch {bi}/{len(batches)}] 사용 가능한 번역 수단이 없음 "
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
                if entry.is_local:
                    # 로컬 NPU: 양자화 프리셋에 맞춰 작은 청크로 나눠 처리
                    # (소형 모델 컨텍스트/품질 한계 -> 실패 파장 축소)
                    presets = local_started["presets"] or local_presets_for(entry.model)
                    mapping, given_up = translate_local_chunked(
                        entry, args, system_prompt_local, template, glossary_text,
                        render_prev_context(prev_pairs), todo, presets)
                    # 반분 재시도 끝에도 실패한 세그먼트는 원문 유지로 확정하고
                    # remaining에서 제거 (안 그러면 무한 재요청 루프)
                    for sid in given_up:
                        if sid in remaining:
                            remaining[sid].translated = remaining[sid].text
                            remaining[sid].translation_failed = True
                            del remaining[sid]
                else:
                    raw = call_llm(entry.provider, entry.client, entry.model,
                                  system_prompt, prompt,
                                  args.max_tokens, args.temperature)
                    mapping = parse_model_json(raw)
                last_call_time = time.monotonic()
                keys_tried_since_success = 0
            except Exception as e:
                last_call_time = time.monotonic()
                if is_permanent_exhaustion(e):
                    # 401/403/할당량-크레딧-결제 소진 등: 재시도해도 절대 안 되므로 즉시 제외
                    # (rate-limit 형태의 오류든 아니든 무관하게 최우선으로 처리)
                    entry.alive = False
                    print(f"  [batch {bi}/{len(batches)}] 키 {entry.label} 영구 오류(인증/권한/할당량) "
                          f"-> 이번 실행에서 제외: {e}")
                    nxt = next_alive_index(key_idx + 1)
                    if nxt is None:
                        aborted = True
                        abort_page = min(s.page for s in remaining.values()) + 1
                        print(f"  [batch {bi}/{len(batches)}] 모든 키 소진 "
                              f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                        break
                    key_idx = nxt
                    continue
                if is_rate_limit_error(e):
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

            before_count = len(remaining)
            for sid, txt in mapping.items():
                if sid in remaining:
                    remaining[sid].translated = txt
            remaining = {k: v for k, v in remaining.items() if v.translated is None}
            if remaining:
                if len(remaining) >= before_count:
                    no_progress += 1
                    if no_progress >= 3:
                        print(f"  [batch {bi}/{len(batches)}] 3회 연속 진전 없음(모델이 세그먼트를 "
                              f"계속 누락) -> 남은 {len(remaining)}개는 원문 유지하고 다음 배치로")
                        break
                else:
                    no_progress = 0
                print(f"  [batch {bi}/{len(batches)}] 누락 {len(remaining)}개 세그먼트 재요청")

        # 이 배치에서 끝까지 실패/중단된 분은 원문 유지 (문서 손실 방지)
        for s in remaining.values():
            if s.translated is None:
                s.translated = s.text
                s.translation_failed = True
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
            s.translation_failed = True

    print(f"[3/4] 번역 {'중단됨' if aborted else '완료'}: {len(targets)}개 세그먼트, "
          f"원문 {total_chars_sent:,}자 전송")
    return aborted


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
    r"^(?P<base>.+?)_(?:translated|T)_(?P<trange>\d{3}-\d{3})"
    r"_(?:untranslated|unT)_(?P<uranges>\d{3}-\d{3}(?:_\d{3}-\d{3})*)$"
)


def collapse_to_ranges(pages: list[int]) -> list[tuple[int, int]]:
    """[3,4,5,10,11,20] -> [(3,5),(10,11),(20,20)] 처럼 연속 페이지를 구간으로 묶는다."""
    if not pages:
        return []
    pages = sorted(set(pages))
    ranges: list[tuple[int, int]] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
        else:
            ranges.append((start, prev))
            start = prev = p
    ranges.append((start, prev))
    return ranges


def parse_resume_filename(stem: str) -> dict | None:
    """
    '<base>_translated_###-@@@_untranslated_$$$-%%%[_...더 있으면 계속]' (또는 축약형 _T_/_unT_)
    패턴을 입력 파일명에서 감지한다. 미번역 구간이 없으면 '000-000'으로 표시되어 있다(완역 sentinel).
    이어서 번역할 때 재사용.
    """
    m = RESUME_FILENAME_RE.match(stem)
    if not m:
        return None
    a, b = m.group("trange").split("-")
    t_start, t_end = int(a), int(b)
    u_ranges: list[tuple[int, int]] = []
    for part in m.group("uranges").split("_"):
        c, d = part.split("-")
        u_ranges.append((int(c), int(d)))
    if u_ranges == [(0, 0)]:  # 완역 sentinel
        u_ranges = []
    return {"base": m.group("base"), "t_start": t_start, "t_end": t_end, "u_ranges": u_ranges}


def build_output_stem(base_stem: str, t_start: int, t_end: int,
                      u_ranges: list[tuple[int, int]]) -> str:
    """
    페이지 범위를 반영한 출력 파일명(확장자 제외) 생성.
    미번역 구간이 없으면 '000-000' sentinel을 붙여 다음 실행에서 건너뛸 수 있게 한다.
    너무 길면 _translated->_T, _untranslated->_unT로 축약.
    """
    fmt = lambda n: f"{n:03d}"
    t_part = f"_translated_{fmt(t_start)}-{fmt(t_end)}"
    display_ranges = u_ranges if u_ranges else [(0, 0)]
    u_part = "_untranslated_" + "_".join(f"{fmt(a)}-{fmt(b)}" for a, b in display_ranges)
    stem = base_stem + t_part + u_part
    if len(stem) > 150:
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
    # --- 로컬 NPU (Lemonade / FastFlowLM) 폴백 ---
    ap.add_argument("--local-npu", action="store_true",
                    help="클라우드 API가 전부 소진되면 로컬 NPU(Lemonade)로 이어서 번역. "
                         "서버가 안 떠 있으면 자동으로 백그라운드 기동함")
    ap.add_argument("--no-local-npu", action="store_true",
                    help="로컬 NPU 폴백을 비활성화 (api.txt에 local 항목이 있어도 무시)")
    ap.add_argument("--model-local", default=None,
                    help=f"로컬 NPU 모델 이름 (기본: {DEFAULT_MODELS['local']})")
    ap.add_argument("--local-port", type=int, default=LEMONADE_DEFAULT_PORT,
                    help=f"Lemonade 서버 포트 (기본: {LEMONADE_DEFAULT_PORT})")
    ap.add_argument("--local-serve-cmd", default=None,
                    help="Lemonade 서버 실행 명령/경로 (기본: LemonadeServer → lemonade-server-dev 순으로 자동 탐색)")
    ap.add_argument("--local-timeout", type=float, default=300.0,
                    help="로컬 NPU 요청 타임아웃(초). NPU는 느리므로 넉넉하게 (기본: 300)")
    ap.add_argument("--local-ctx-size", type=int, default=8192,
                    help="로컬 모델 로드시 컨텍스트 크기(토큰). 번역 프롬프트가 길어 기본값(보통 4096 "
                         "이하)으로는 JSON 출력 지시가 잘릴 수 있어 넉넉히 잡음 (기본: 8192)")
    ap.add_argument("--model-select-timeout", type=float, default=10.0,
                    help="로컬 모델 선택 메뉴의 입력 대기 시간(초). 시간 내 입력이 없으면 "
                         "기본 모델로 자동 진행 (기본: 10)")
    ap.add_argument("--no-merge", action="store_true",
                    help="문장 단절 블록 자동 병합 비활성화 (PDF가 문장을 여러 블록으로 쪼갠 경우 "
                         "기본적으로 병합해서 번역 품질을 높임)")
    ap.add_argument("--doc-type", default="technical documentation")
    ap.add_argument("--style", default="formal, professional")
    ap.add_argument("--terminology-policy", default=DEFAULT_TERMINOLOGY_POLICY)
    ap.add_argument("--title", default=None, help="문서 제목 (기본: PDF 메타데이터/파일명)")
    ap.add_argument("--domain", default="general")
    ap.add_argument("--instructions", default="", help="추가 문서별 지시사항")
    ap.add_argument("--glossary", default=None, help="용어집 파일 (.json 또는 .csv/.txt)")
    ap.add_argument("--pages", default=None, help='번역할 페이지 지정 (예: "1-3,7")')
    ap.add_argument("--batch-chars", type=int, default=1500, help="배치당 최대 원문 문자 수")
    ap.add_argument("--batch-segs", type=int, default=10, help="배치당 최대 세그먼트 수")
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
        u_ranges = resume_info["u_ranges"]
        if u_ranges:
            ranges_str = ", ".join(f"{a}-{b}" for a, b in u_ranges)
            print(f"[정보] 이어서-번역 파일명 감지: 전체 스코프 "
                  f"{resume_info['t_start']}-{resume_info['t_end']}페이지, "
                  f"미번역 {ranges_str}페이지")
        else:
            print(f"[정보] 이어서-번역 파일명 감지: "
                  f"{resume_info['t_start']}-{resume_info['t_end']}페이지 전체 완역 상태")
        if not u_ranges:
            if args.pages is None:
                print("[안내] 미번역 구간이 없어(완역 상태) 다시 번역할 것이 없습니다. 종료합니다.")
                return
        elif args.pages is None:
            args.pages = ",".join(f"{a}-{b}" for a, b in u_ranges)
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
    if not args.no_merge:
        segments = merge_adjacent_segments(segments)
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
    aborted = False
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
        # 로컬 NPU 폴백: --local-npu 지정 시 풀 맨 뒤(최후 순위)에 추가
        if args.local_npu and not args.no_local_npu:
            local_entry = make_local_entry(args)
            pool.append(local_entry)
            print(f"[정보] 로컬 NPU 폴백 활성화: {local_entry.model} "
                  f"(포트 {args.local_port}, 클라우드 전부 소진 시에만 사용)")
        print(f"[2/4] 배치: {len(batches)}개 (배치당 최대 {args.batch_chars}자 / "
              f"{args.batch_segs}세그먼트)")
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        system_prompt_local = SYSTEM_PROMPT_LOCAL_PATH.read_text(encoding="utf-8") \
            if SYSTEM_PROMPT_LOCAL_PATH.exists() else None
        template = USER_TEMPLATE_PATH.read_text(encoding="utf-8")
        glossary_text = load_glossary(args.glossary)
        try:
            aborted = translate_all_batches(pool, args, system_prompt, template,
                                            segments, glossary_text,
                                            system_prompt_local=system_prompt_local)
        finally:
            shutdown_lemonade_server()

    if args.export_json:
        export_translations(args.export_json, segments)

    # 이번 실행에서 (사유 불문하고) 결국 원문으로 남은 페이지를 전부 집계
    # -> 산발적으로 흩어진 실패도 각각의 구간으로 표현된다.
    target_segments = [s for s in segments if s.needs_translation]
    run_failed_pages = sorted({s.page + 1 for s in target_segments if s.translation_failed})
    run_untranslated_ranges = collapse_to_ranges(run_failed_pages)

    # '_translated_###-@@@'는 이 문서가 다루는 전체 페이지 범위(스코프)를 뜻하며,
    # 이어서-번역 시에는 최초 실행의 스코프를 그대로 유지한다(재번역 대상 페이지만 좁혀서 처리해도 안 바뀜).
    if resume_info:
        final_t_start, final_t_end = resume_info["t_start"], resume_info["t_end"]
    else:
        final_t_start, final_t_end = run_first_page, run_last_page
    final_untranslated_ranges = run_untranslated_ranges

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
                                     final_untranslated_ranges)
        out_path = in_path.with_name(out_stem + in_path.suffix)

    doc.save(out_path, garbage=3, deflate=True)
    status = "번역 일부 미완료(원문 유지)" if aborted else "완료"
    print(f"[4/4] 재구성 {status} -> {out_path}"
          + (f" (축소 한계 초과 {truncated}개 블록)" if truncated else ""))
    if final_untranslated_ranges:
        ranges_str = ", ".join(f"{a}-{b}" for a, b in final_untranslated_ranges)
        print(f"[안내] {ranges_str}페이지는 원문 그대로 저장됨 "
              f"({sum(1 for s in target_segments if s.translation_failed)}개 세그먼트). "
              f"이 출력 파일을 다시 입력으로 넣으면 파일명에서 미번역 구간을 읽어 자동으로 이어서 번역함:")
        print(f"       python {Path(__file__).name} \"{out_path}\""
              + (f" --provider {args.provider}" if args.provider else ""))
    else:
        print("[안내] 미번역 구간 없음 (완역). 이 파일을 다시 입력으로 넣으면 할 일이 없어 그대로 종료됨.")


if __name__ == "__main__":
    main()