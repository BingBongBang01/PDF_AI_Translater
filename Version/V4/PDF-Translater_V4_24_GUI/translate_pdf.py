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
import hashlib
import html as html_mod
import json
import math
import os
import re
import shutil
import sys
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import pymupdf
except ImportError as _pymupdf_error:
    try:
        import fitz as pymupdf
    except ImportError as _fitz_error:
        print("[오류] PyMuPDF 로드 실패.", file=sys.stderr)
        print(f"  pymupdf import 오류: {_pymupdf_error!r}", file=sys.stderr)
        print(f"  fitz import 오류: {_fitz_error!r}", file=sys.stderr)
        print(f"  Python 실행 파일: {sys.executable}", file=sys.stderr)
        print(f"  frozen(EXE): {getattr(sys, 'frozen', False)}", file=sys.stderr)
        sys.exit(1)

# 버전 표기는 이 상수 하나에서만 관리한다. gui.py는 이 값을 import해서 타이틀에 쓰고,
# build_exe.bat은 이 값을 읽어 실행파일 이름을 결정한다 (버전 문자열이 여러 곳에 흩어져
# 서로 어긋나는 사고 방지 - 예: v3.82로 하드코딩된 채 zip 이름만 v3.84로 배포됐던 문제).
__version__ = "4.3.0"

# ---------------------------------------------------------------------------
# 로컬 AI 런타임 레지스트리 - Lemonade 외 다른 로컬 서버(Ollama, LM Studio 등)를
# 지원하기 위한 확장 지점. 전부 OpenAI 호환 REST API를 노출하므로 실제 호출 경로는
# 공통(call_llm)이고, 여기서는 "이 런타임을 어떻게 찾고/켜고/무슨 장치를 쓰는지"만 정의한다.
#
# 확인된 사실(2026-07 기준, 출처: 각 프로젝트 공식 문서/최근 리뷰 기사):
#   - NPU 가속을 지금 실사용 가능한 수준으로 지원하는 로컬 런타임은 Lemonade(AMD XDNA2, FLM
#     백엔드)뿐이다. Ollama는 개발진이 "NPU를 직접 활용할 수 없다"고 명시했고, LM Studio는
#     AMD RyzenAI용 별도 '기술 프리뷰' 빌드만 있어 정식 기능이 아니다. Intel/Qualcomm NPU를
#     지원하는 런타임은 이 목록에 없다.
#   - GPU(NVIDIA/AMD/Intel)는 Lemonade, LM Studio, Ollama 셋 다 지원(백엔드: CUDA/ROCm/Vulkan).
#   - Jan, AnythingLLM, llamafile은 이번 조사에서 GPU 지원 정도까지만 확인됐고(Jan은 CUDA/
#     Vulkan 빌드 선택 방식), 자동 기동 명령/헬스체크 경로는 실제 설치 후 검증이 필요해
#     레지스트리에 아직 넣지 않았다. 필요해지면 아래 형식 그대로 항목만 추가하면 된다.
# ---------------------------------------------------------------------------
RUNTIME_REGISTRY: dict[str, dict] = {
    "lemonade": {
        "label": "Lemonade Server",
        "default_port": 13305,
        "supports_npu": True,
        "supports_gpu": True,
        "api_prefix": "/api/v1",       # base_url = http://localhost:{port}{api_prefix}
        "health_path": "/api/v1/models",
        "serve_candidates": [("LemonadeServer", []), ("lemonade-server-dev", ["serve"])],
        "needs_ctx_load": True,        # /api/v1/load로 컨텍스트 크기 명시 필요 (긴 프롬프트 대응)
        "needs_model_menu": True,      # 번호 선택 메뉴 지원 (choose_local_model)
    },
    "ollama": {
        "label": "Ollama",
        "default_port": 11434,
        "supports_npu": False,
        "supports_gpu": True,
        "api_prefix": "/v1",
        "health_path": "/v1/models",
        "serve_candidates": [("ollama", ["serve"])],
        "needs_ctx_load": False,
        "needs_model_menu": False,
    },
    "lmstudio": {
        "label": "LM Studio",
        "default_port": 1234,
        "supports_npu": False,
        "supports_gpu": True,
        "api_prefix": "/v1",
        "health_path": "/v1/models",
        # LM Studio는 보통 앱을 켜두거나 'lms server start'로 미리 띄워두는 걸 전제로 한다.
        # CLI 자동 기동은 이 환경에서 검증되지 않았으니 실패해도 "수동으로 켜두라"고 안내한다.
        "serve_candidates": [("lms", ["server", "start"])],
        "needs_ctx_load": False,
        "needs_model_menu": False,
    },
}
DEFAULT_LOCAL_RUNTIME = "lemonade"


def get_runtime_spec(name: str) -> dict:
    spec = RUNTIME_REGISTRY.get(name)
    if spec is None:
        valid = ", ".join(RUNTIME_REGISTRY)
        raise SystemExit(f"[오류] 알 수 없는 --local-runtime '{name}'. 사용 가능: {valid}")
    return spec

SCRIPT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 우아한 중단(Graceful Stop) API — GUI 등 외부에서 호출
#   request_stop(): 현재 진행 중인 배치까지만 번역하고, 이후 배치는 원문 유지한 채
#                   정상 저장 경로(파일명 untranslated 구간 포함)로 마무리한다.
#   reset_stop():   새 실행 시작 전 플래그 초기화 (같은 프로세스에서 재실행하는 GUI용)
# ---------------------------------------------------------------------------
STOP_EVENT = threading.Event()


def request_stop() -> None:
    STOP_EVENT.set()


def reset_stop() -> None:
    STOP_EVENT.clear()


def stop_requested() -> bool:
    return STOP_EVENT.is_set()

SYSTEM_PROMPT_PATH = SCRIPT_DIR / "prompts" / "system_prompt.txt"
SYSTEM_PROMPT_LOCAL_PATH = SCRIPT_DIR / "prompts" / "system_prompt_local.txt"
USER_TEMPLATE_PATH = SCRIPT_DIR / "prompts" / "user_template.txt"

# 어떤 문자 체계든 '글자'가 하나라도 있는지 검사 (숫자/기호만 있는 블록은 번역 생략)
LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5.4-mini",
    "local": "gemma4-it-e2b-FLM",  # 하위 호환용 (device 미지정 시 기본값 = NPU 모델)
}
DEFAULT_MODEL = DEFAULT_MODELS["anthropic"]  # 하위 호환용

# ---------------------------------------------------------------------------
# 중요: Lemonade에서 NPU/GPU는 실행 시점에 고르는 옵션이 아니라 "모델 자체의 recipe"다.
# 파일명이 -FLM으로 끝나는 모델은 FLM 백엔드(NPU) 전용이고, 그 외(-GGUF 등)는 llamacpp
# 백엔드(GPU/CPU)다. 즉 "GPU를 쓰고 싶다"는 요청은 실제로는 "GGUF 계열 모델을 로드하라"는
# 뜻이어야 하는데, 예전 코드는 device와 무관하게 항상 DEFAULT_MODELS["local"](FLM 모델)만
# 로드해서 GPU를 체크해도 NPU가 도는 버그가 있었다. 장치별 기본 모델을 분리해 해결한다.
# ---------------------------------------------------------------------------
DEFAULT_LOCAL_MODEL_BY_DEVICE = {
    "npu": "gemma4-it-e2b-FLM",       # FLM 레시피 -> XDNA NPU 전용
    "gpu": "Gemma-3-4b-it-GGUF",      # llamacpp 레시피 -> Vulkan/ROCm/CUDA로 GPU 사용
}


def model_recipe_device(model_name: str) -> str:
    """모델 이름으로 실제 실행 장치를 추정. 'FLM' 접미사 = NPU 전용, 그 외 = GPU/CPU(llamacpp)."""
    return "npu" if model_name.lower().endswith("-flm") or "-flm-" in model_name.lower() \
        else "gpu"


def resolve_local_model_for_device(args, device: str) -> str:
    """
    device별 전용 인자(--model-local-npu/--model-local-gpu)가 있으면 최우선,
    없으면 공용 --model-local, 그것도 없으면 device 기본값을 쓴다.
    명시된 모델이 요청한 device와 실제로 안 맞으면 경고한다(예: device=gpu인데 -FLM 모델을
    지정한 경우 -> 여전히 NPU로 돌 것이라는 사실을 알려줌).
    """
    per_device = getattr(args, f"model_local_{device}", None)
    explicit = per_device or args.model_local
    if explicit:
        actual = model_recipe_device(explicit)
        if actual != device:
            print(f"[경고] {explicit}은(는) 실제로 {actual.upper()} 전용 모델입니다. "
                  f"{device.upper()}를 요청했지만 이 모델은 항상 {actual.upper()}로 실행됩니다 "
                  f"(Lemonade는 장치를 모델의 recipe로 고정하며, 실행 시점에 전환할 수 없습니다).")
        return explicit
    return DEFAULT_LOCAL_MODEL_BY_DEVICE.get(device, DEFAULT_MODELS["local"])

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
    line_boxes: list[tuple] | None = None  # 원본 각 줄 bbox
    layout_boxes: list[tuple] | None = None  # 병합 전 원본 블록 bbox 보존
    vertical: bool = False          # True면 세로쓰기(일본어 종서 등) - 렌더링 시 writing-mode 적용
    is_ocr: bool = False            # True면 OCR로 얻은 텍스트 - 원본에 텍스트 레이어가 없어 redact 생략


# ---------------------------------------------------------------------------
# [1] 추출
# ---------------------------------------------------------------------------
# --source-lang(자유 형식 문자열)을 Tesseract 언어 데이터 코드로 자동 매핑.
# 사용자가 --ocr-lang을 직접 안 주면 이 매핑을 써서 매번 수동 지정할 필요가 없게 한다.
# 일본어는 가로쓰기(jpn)와 세로쓰기(jpn_vert) 언어 데이터가 따로 있는데, 스캔본이 어느
# 쪽인지 사전에 알 수 없으므로 둘 다 지정해 Tesseract가 알아서 인식하게 한다(Tesseract는
# '+'로 여러 언어를 동시에 지정 가능).
_OCR_LANG_MAP = {
    "english": "eng", "en": "eng", "auto": "eng",
    "korean": "kor", "ko": "kor", "한국어": "kor",
    "japanese": "jpn+jpn_vert", "ja": "jpn+jpn_vert", "일본어": "jpn+jpn_vert",
    "chinese": "chi_sim", "chinese (simplified)": "chi_sim", "zh": "chi_sim",
    "chinese (traditional)": "chi_tra",
    "french": "fra", "german": "deu", "spanish": "spa",
}


def resolve_ocr_lang(source_lang: str, explicit_ocr_lang: str | None) -> str:
    """명시적으로 --ocr-lang을 줬으면 그걸 우선하고, 없으면 --source-lang에서 자동 매핑한다."""
    if explicit_ocr_lang:
        return explicit_ocr_lang
    mapped = _OCR_LANG_MAP.get((source_lang or "").strip().lower())
    return mapped or "eng"


def find_tessdata_dir(explicit: str | None = None) -> str | None:
    """
    Tesseract의 언어 데이터(tessdata) 폴더를 찾는다. pymupdf의 자체 자동탐지는
    유닉스 계열에서 'whereis tesseract-ocr'라는 명령 결과에만 의존하는데, 실행파일
    이름이 배포판/설치방식마다 다르면(예: 'tesseract'만 있고 'tesseract-ocr'는 없음,
    Windows는 애초에 'whereis'가 없음) 이 탐지가 실패해서 Tesseract가 실제로 정상
    설치돼 있어도 "Tesseract is not installed"라는 오류가 난다. 그래서 우리가 직접
    더 폭넓게 탐색한다.
    우선순위: 1) 사용자가 --tessdata-dir로 직접 지정  2) TESSDATA_PREFIX 환경변수
    3) tesseract 실행파일 위치 기준 형제/하위 tessdata 폴더  4) OS별로 흔히 설치되는 경로.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_prefix = os.environ.get("TESSDATA_PREFIX")
    if env_prefix:
        candidates.append(Path(env_prefix))

    exe = shutil.which("tesseract")
    if exe:
        exe_dir = Path(exe).resolve().parent
        candidates += [
            exe_dir / "tessdata",             # Windows 표준: <설치폴더>\tessdata
            exe_dir.parent / "tessdata",
            exe_dir.parent / "share" / "tessdata",
            exe_dir.parent / "share" / "tesseract-ocr" / "tessdata",
        ]

    if os.name == "nt":
        candidates += [
            Path("C:/Program Files/Tesseract-OCR/tessdata"),
            Path("C:/Program Files (x86)/Tesseract-OCR/tessdata"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tessdata",
        ]
    else:
        import glob
        candidates += [Path(p) for p in glob.glob("/usr/share/tesseract-ocr/*/tessdata")]
        candidates += [
            Path("/usr/share/tessdata"),
            Path("/usr/local/share/tessdata"),
            Path("/opt/homebrew/share/tessdata"),
        ]

    for c in candidates:
        try:
            if c and c.is_dir() and any(c.glob("*.traineddata")):
                return str(c)
        except Exception:
            continue
    return None


def extract_segments(doc: "pymupdf.Document", page_filter: set[int] | None,
                     translate_all: bool, tessdata_dir: str | None = None,
                     ocr_lang: str = "eng") -> list[Segment]:
    # 같은 왼쪽 시작 x좌표로 볼 수 있는 오차 허용치. 이보다 크게 벌어진 줄이 섞여 있으면
    # 표/다단 레이아웃으로 보고(pymupdf가 여러 셀/컬럼을 하나의 block으로 묶어버리는 경우가
    # 흔함) 블록 전체를 한 세그먼트로 합치지 않고 줄 단위로 쪼갠다. 안 쪼개면 서로 다른 셀의
    # 텍스트가 하나의 문단으로 합쳐져 번역 후 표 구조가 무너진다(칸이 비거나 내용이 뒤섞임).
    TABLE_LIKE_X0_TOLERANCE = 3.0

    def make_seg(pno: int, bno: int, text: str, bbox: tuple,
                sizes: list[float], colors: list[int], bold_votes: list[bool],
                line_boxes: list[tuple] | None, vertical: bool = False,
                is_ocr: bool = False) -> Segment | None:
        text = text.strip()
        if not text:
            return None
        return Segment(
            seg_id=f"page_{pno + 1:03d}_block_{bno:03d}",
            page=pno, bbox=bbox, text=text,
            font_size=(Counter(sizes).most_common(1)[0][0] if sizes else 11.0),
            color=f"#{(Counter(colors).most_common(1)[0][0] if colors else 0):06x}",
            bold=(sum(bold_votes) > len(bold_votes) / 2) if bold_votes else False,
            needs_translation=(True if translate_all else bool(LETTER_RE.search(text))),
            line_boxes=line_boxes,
            layout_boxes=[bbox],
            vertical=vertical,
            is_ocr=is_ocr,
        )

    def _is_vertical_dir(d: tuple) -> bool:
        """pymupdf line의 'dir'(방향 벡터)로 세로쓰기 여부 판정.
        가로쓰기는 보통 (1,0)에 가깝고, 세로쓰기(일본어 종서 등)나 회전된 텍스트는
        y성분이 지배적인 (0,±1)에 가깝다."""
        try:
            return abs(d[1]) > abs(d[0])
        except Exception:
            return False

    ocr_warned = {"done": False}  # tesseract 미설치 경고를 문서당 1번만 띄우기 위한 플래그
    resolved_tessdata = find_tessdata_dir(tessdata_dir)
    if tessdata_dir and not resolved_tessdata:
        print(f"[경고] 지정한 --tessdata-dir '{tessdata_dir}'에서 언어 데이터 파일"
              f"(*.traineddata)을 찾지 못함 - 자동 탐지도 실패했으므로 OCR이 동작하지 않을 수 있음")

    segments: list[Segment] = []
    for pno in range(doc.page_count):
        if page_filter is not None and pno not in page_filter:
            continue
        page = doc[pno]
        data = page.get_text("dict", sort=True)  # 위->아래, 왼->오른쪽 정렬
        is_ocr_page = False

        # 스캔본(이미지만 있고 텍스트 레이어가 없는 PDF) 자동 감지 + OCR 폴백.
        # 조건: 추출된 글자 수가 극히 적은데(20자 미만) 페이지에 이미지가 있으면 스캔본으로
        # 추정 - 그런 경우 pymupdf 내장 OCR(Tesseract 필요)로 재추출을 시도한다.
        total_chars = sum(len(sp.get("text", "")) for b in data.get("blocks", [])
                          if b.get("type") == 0 for ln in b.get("lines", [])
                          for sp in ln.get("spans", []))
        if total_chars < 20:
            try:
                has_images = bool(page.get_images())
            except Exception:
                has_images = False
            if has_images:
                try:
                    ocr_kwargs = {"flags": 0, "full": True, "dpi": 200, "language": ocr_lang}
                    if resolved_tessdata:
                        ocr_kwargs["tessdata"] = resolved_tessdata
                    ocr_textpage = page.get_textpage_ocr(**ocr_kwargs)
                    ocr_data = page.get_text("dict", textpage=ocr_textpage, sort=True)
                    ocr_chars = sum(len(sp.get("text", "")) for b in ocr_data.get("blocks", [])
                                    if b.get("type") == 0 for ln in b.get("lines", [])
                                    for sp in ln.get("spans", []))
                    if ocr_chars > total_chars:
                        data = ocr_data
                        is_ocr_page = True
                        print(f"[정보] {pno + 1}페이지: 텍스트 레이어가 거의 없음(스캔본으로 추정) "
                              f"-> OCR로 텍스트 {ocr_chars}자 추출"
                              + (f" (tessdata: {resolved_tessdata})" if resolved_tessdata else ""))
                except Exception as e:
                    if not ocr_warned["done"]:
                        print(f"[경고] {pno + 1}페이지가 스캔본으로 보이지만 OCR을 사용할 수 없습니다: {e}")
                        if resolved_tessdata:
                            print(f"       tessdata 경로는 찾음({resolved_tessdata})인데도 실패했습니다. "
                                  f"Tesseract 실행파일 자체나 언어 데이터가 손상됐을 수 있습니다.")
                        else:
                            print("       Tesseract의 언어 데이터(tessdata) 폴더를 자동으로 찾지 못했습니다. "
                                  "Tesseract가 설치돼 있다면 --tessdata-dir로 직접 경로를 지정하세요 "
                                  "(보통 Windows는 'C:\\Program Files\\Tesseract-OCR\\tessdata'). "
                                  "설치가 안 돼 있다면 https://github.com/tesseract-ocr/tesseract 에서 설치하세요.")
                        print("       (OCR을 못 쓰면 이 페이지는 원문 없이 빈 상태로 남습니다.)")
                        ocr_warned["done"] = True
                        ocr_warned["done"] = True

        bno = 0
        for block in data.get("blocks", []):
            if block.get("type") != 0:           # 0 = 텍스트 블록
                continue

            line_infos = []  # 각 줄: (text, bbox, sizes, colors, bold_votes, is_vertical)
            for line in block.get("lines", []):
                line_text = "".join(sp.get("text", "") for sp in line.get("spans", []))
                if not line_text.strip():
                    continue
                l_sizes, l_colors, l_bold = [], [], []
                for sp in line.get("spans", []):
                    l_sizes.append(round(float(sp.get("size", 11.0)), 1))
                    l_colors.append(int(sp.get("color", 0)))
                    l_bold.append(bool(sp.get("flags", 0) & 16) or "bold" in sp.get("font", "").lower())
                is_vert = _is_vertical_dir(line.get("dir", (1, 0)))
                line_infos.append((line_text, tuple(line.get("bbox", block["bbox"])),
                                   l_sizes, l_colors, l_bold, is_vert))
            if not line_infos:
                continue

            # 블록 전체의 세로쓰기 여부: 과반수 줄이 세로 방향이면 세로쓰기 블록으로 판정
            # 블록 전체의 세로쓰기 여부 판정: 두 가지 근거를 함께 본다.
            #   1) dir 벡터 기반: 과반수 줄의 방향 벡터가 세로(y성분 지배적)
            #   2) 위치 퍼짐 기반: 줄들이 세로로 넓게 퍼져 있고(y_range) 가로로는 좁게
            #      모여있으면(x_range) 세로쓰기로 본다.
            #   1)만으로는 부족하다 - 세로쓰기 문서에서 한 글자만 있는 줄(흔한 경우, 특히
            #   영숫자나 조사 한 글자)은 pymupdf가 dir을 방향성 없는 기본값 (1,0)으로 보고할
            #   때가 있어서, 실제로는 세로로 죽 이어지는 문단인데도 dir만 보면 전부 가로로
            #   오판될 수 있다(그러면 회전 없이 삽입되어 좁고 긴 bbox에 텍스트가 가로로
            #   욱여넣어지며 심하게 깨진다). 위치 퍼짐을 보조 근거로 추가해 이를 보완한다.
            vertical_by_dir = sum(1 for li in line_infos if li[5]) > len(line_infos) / 2
            if len(line_infos) > 1:
                y0s_all = [li[1][1] for li in line_infos]
                x0s_all = [li[1][0] for li in line_infos]
                y_spread = max(y0s_all) - min(y0s_all)
                x_spread = max(x0s_all) - min(x0s_all)
                avg_line_len = sum(len(li[0]) for li in line_infos) / len(line_infos)
                # 왼쪽 정렬된 일반 가로쓰기 문단도 "x0가 거의 같고 y0가 줄마다 증가"하는
                # 구조라 y_spread > x_spread만으로는 세로쓰기와 구분이 안 된다(오탐 발생 확인됨:
                # 여러 줄짜리 영문 문단이 전부 세로쓰기로 오판됨). 결정적 차이는 줄 하나에
                # 담긴 글자 수다 - 세로쓰기 컬럼은 줄마다 한자/가나/문자 1~3개 정도인 반면,
                # 가로쓰기 문단은 줄마다 단어 여러 개(보통 수십 자)가 들어간다. 그래서 줄이
                # 충분히 짧을 때만 위치 퍼짐 판정을 적용한다.
                short_lines = avg_line_len <= 4.0
                vertical_by_spread = short_lines and y_spread > x_spread * 1.5
            else:
                vertical_by_spread = False
            block_vertical = vertical_by_dir or vertical_by_spread

            if block_vertical:
                # 세로쓰기(일본어 종서 등) 판정은 두 단계다.
                #
                # 1) 같은 컬럼(x0가 거의 동일)인 줄들 = 한 세로줄 안에서 위->아래로 이어지는
                #    글자/단어들이다. 이건 무조건 하나의 문단이다 - 순서대로 아래로 내려가니
                #    y-range가 서로 안 겹치는 게 정상인데, 이걸 "안 겹치니 표"로 오판하면
                #    (실제로 이전 버전의 버그) 한 문장이 낱글자 단위로 쪼개지고, 그 결과 각
                #    조각의 bbox 높이가 번역문 길이에 비해 턱없이 부족해져서 극단적으로
                #    축소되며 "2줄로 들어가고 그 안에서 글자가 가로쓰기처럼 나열되는" 현상이
                #    생긴다(폭 안에 여러 글자가 들어갈 만큼 폰트가 작아지면서 세로 1글자당
                #    1줄 원칙이 깨짐).
                # 2) 서로 다른 컬럼(x0가 다름)이 섞여 있을 때만 표/문단을 구분해야 하는데,
                #    이때는 y-range 겹침으로 판단한다: 겹치면 같은 문단의 여러 컬럼(오른쪽에서
                #    왼쪽으로 읽는 구조), 안 겹치면 표의 다른 행일 가능성이 높다.
                x0s = [li[1][0] for li in line_infos]
                if (max(x0s) - min(x0s)) <= TABLE_LIKE_X0_TOLERANCE:
                    table_like = False
                else:
                    def _y_overlap_ratio(a, b):
                        top, bot = max(a[0], b[0]), min(a[1], b[1])
                        if bot <= top:
                            return 0.0
                        return (bot - top) / max(min(a[1] - a[0], b[1] - b[0]), 1e-6)

                    y_ranges = [(li[1][1], li[1][3]) for li in line_infos]
                    ref = y_ranges[0]
                    table_like = any(_y_overlap_ratio(ref, r) < 0.3 for r in y_ranges[1:])
            else:
                x0s = [li[1][0] for li in line_infos]
                table_like = (max(x0s) - min(x0s)) > TABLE_LIKE_X0_TOLERANCE

            if not table_like:
                # 일반 문단: 지금까지처럼 블록 전체를 한 세그먼트로 (문맥 유지, 번역 품질 우선)
                text = "\n".join(li[0] for li in line_infos)
                sizes = [s for li in line_infos for s in li[2]]
                colors = [c for li in line_infos for c in li[3]]
                bold_votes = [b for li in line_infos for b in li[4]]
                line_boxes = [li[1] for li in line_infos]
                seg = make_seg(pno, bno, text, tuple(block["bbox"]), sizes, colors,
                              bold_votes, line_boxes, vertical=block_vertical, is_ocr=is_ocr_page)
                if seg:
                    segments.append(seg)
                    bno += 1
            else:
                # 표/다단 의심(줄마다 시작 x가 다름): 각 줄을 독립 세그먼트로 분리해
                # 각자 원래 위치(그 줄의 bbox)에 개별 번역·배치한다. 셀 경계가 깨지지 않는다.
                for text, bbox, sizes, colors, bold_votes, is_vert in line_infos:
                    seg = make_seg(pno, bno, text, bbox, sizes, colors, bold_votes, [bbox],
                                  vertical=is_vert, is_ocr=is_ocr_page)
                    if seg:
                        segments.append(seg)
                        bno += 1
    return segments


_SENTENCE_END_RE = re.compile(r'[.!?:;"\u201d\u2026]\s*$')


def merge_adjacent_segments(segments: list[Segment]) -> list[Segment]:
    """
    V3.8 layout-safe policy.

    번역 품질을 위해 물리 PDF 블록을 합치면, 번역 결과를 원래 블록들로 정확히
    역분배할 방법이 없다. 특히 목차/표/다단 문서에서 내용 누락, 겹침, 위치 이동을
    유발한다. 따라서 물리 블록은 절대 병합하지 않는다.

    문맥 연결은 배치 프롬프트와 prev_context가 담당하고, 재구성은 추출 당시의
    1 Segment = 1 PDF block 관계를 끝까지 유지한다.
    """
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
    revive_at: float | None = None  # 할당량 소진 키의 부활 예정 시각(time.monotonic 기준). None=영구 제외


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
        has_local = bool(_parse_local_devices(args))
        if has_local:
            print("[정보] 클라우드 API 키를 찾지 못함 -> 로컬 장치 지정됨, 로컬만으로 진행")
            return []
        sys.exit(
            f"[오류] API 키를 찾지 못했습니다"
            f"{f' (provider={args.provider} 필터 적용됨)' if args.provider else ''}. "
            f"다음 중 하나로 제공하세요:\n"
            f"       1) api.txt에 한 줄씩 키 추가 (형태로 provider 자동판별, 또는 'gemini:키'처럼 명시)\n"
            f"       2) export ANTHROPIC_API_KEY=... / GEMINI_API_KEY=... / OPENAI_API_KEY=... (콤마로 여러 개)\n"
            f"       3) 클라우드 키 없이 로컬만 쓰려면 --local-device npu (또는 gpu, npu,gpu)를 추가하세요"
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
# 로컬 AI 런타임 자동 기동 (Lemonade / Ollama / LM Studio 등 - RUNTIME_REGISTRY 참고)
# ---------------------------------------------------------------------------
_LOCAL_PROC = None  # 스크립트가 직접 띄운 서버 프로세스 (없으면 None = 이미 켜져 있던 것)


def local_base_url(port: int, runtime: str = DEFAULT_LOCAL_RUNTIME) -> str:
    spec = get_runtime_spec(runtime)
    return f"http://localhost:{port}{spec['api_prefix']}"


def is_local_runtime_up(port: int, runtime: str = DEFAULT_LOCAL_RUNTIME) -> bool:
    """서버가 이미 떠서 응답하는지 확인."""
    import urllib.request
    spec = get_runtime_spec(runtime)
    try:
        with urllib.request.urlopen(f"http://localhost:{port}{spec['health_path']}", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


# 하위 호환용 별칭 (기존 코드/외부에서 이 이름으로 참조하던 곳 대비)
lemonade_base_url = local_base_url
is_lemonade_up = lambda port: is_local_runtime_up(port, "lemonade")


def _tail_file(path: Path, n_lines: int = 25) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n_lines:]) if lines else "(로그가 비어 있음)"
    except Exception as e:
        return f"(로그 읽기 실패: {e})"


def _try_start_one(exe: str, extra_args: list[str], port: int, args, runtime: str) -> bool:
    """한 개의 실행 명령으로 서버 기동을 시도. 성공하면 True."""
    global _LOCAL_PROC
    import subprocess

    serve_args = [exe] + list(extra_args)
    default_port = get_runtime_spec(runtime)["default_port"]
    if port != default_port and "--port" not in extra_args:
        serve_args += ["--port", str(port)]
    log_path = Path(args.input).with_suffix(f".{runtime}.log")
    print(f"[로컬] 기동 시도: {' '.join(serve_args)} (포트 {port})")

    # 한국어 Windows에서 자식 프로세스의 stdout이 파일로 리다이렉트되면 기본 인코딩이 cp949가 되어
    # (구버전) lemonade-server-dev 내부 print()의 유니코드 문자(예: '•')에서 UnicodeEncodeError로 즉시 죽는다.
    # UTF-8을 강제해 이 크래시를 막는다. (다른 런타임에도 동일하게 안전장치로 적용)
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"

    try:
        logf = open(log_path, "w", encoding="utf-8")
        creationflags = 0
        if os.name == "nt":
            # 콘솔 창을 새로 열지 않고 백그라운드로 (CREATE_NO_WINDOW), 프로세스 그룹 분리
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW
        _LOCAL_PROC = subprocess.Popen(
            serve_args, stdout=logf, stderr=subprocess.STDOUT,
            creationflags=creationflags, env=child_env,
        )
    except Exception as e:
        print(f"[로컬][오류] '{exe}' 실행 자체 실패: {e}")
        return False

    print("[로컬] 서버 준비 대기 중 (최대 180초, 첫 실행은 모델 초기화로 오래 걸릴 수 있음)...")
    for _ in range(180):
        if is_local_runtime_up(port, runtime):
            print("[로컬] 서버 준비 완료")
            return True
        if _LOCAL_PROC.poll() is not None:
            print(f"[로컬][오류] '{exe}' 프로세스가 조기 종료됨 (exit code {_LOCAL_PROC.returncode}).")
            print(f"[로컬] --- 서버 로그 (마지막 25줄) ---")
            print(_tail_file(log_path))
            print(f"[로컬] --- 로그 끝 (전체: {log_path}) ---")
            _LOCAL_PROC = None
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


def ensure_local_runtime(args) -> bool:
    """
    로컬 AI 런타임(args.local_runtime)이 떠 있으면 재사용, 없으면 백그라운드로 자동 기동한다.
    RUNTIME_REGISTRY에 등록된 실행 명령 후보를 순서대로 시도하고, 하나라도 성공하면 True.
    Lemonade 전용 부가 작업(컨텍스트 명시 로드, 모델 선택 메뉴)은 그 런타임일 때만 수행한다.
    Ollama/LM Studio 등은 사용자가 이미 설치해서 모델까지 받아둔 상태를 그대로 재사용하는
    쪽이 기본 전제이므로, 자동 기동은 시도하되 실패하면 "수동으로 켜두라"고 안내하고 넘어간다.
    """
    runtime = getattr(args, "local_runtime", DEFAULT_LOCAL_RUNTIME)
    spec = get_runtime_spec(runtime)
    port = args.local_port

    def _after_up():
        if spec.get("needs_model_menu"):
            prepare_local_model(args)
        elif spec.get("needs_ctx_load"):
            load_local_model(args)
        # 그 외(Ollama/LM Studio 등)는 별도 후처리 없음 - 사용자가 그쪽 앱/CLI로 이미 모델을
        # 받아 로드해뒀다고 가정한다.

    if is_local_runtime_up(port, runtime):
        print(f"[로컬] 이미 실행 중인 {spec['label']} 감지 (포트 {port}) -> 재사용")
        _after_up()
        return True

    if args.local_serve_cmd:
        candidates = [(args.local_serve_cmd, [])]
    else:
        candidates = list(spec["serve_candidates"])
    found = [(exe, extra) for exe, extra in candidates if shutil.which(exe)]
    if not found:
        names = ", ".join(c[0] for c in candidates)
        print(f"[로컬][오류] {spec['label']} 실행파일을 찾지 못했습니다 (시도: {names}).")
        print(f"[로컬] 해결책: 별도 터미널에서 {spec['label']}를 먼저 켜두면 "
              f"이 스크립트가 포트 {port}에서 자동 감지해 재사용합니다.")
        return False

    for exe, extra in found:
        if _try_start_one(exe, extra, port, args, runtime):
            _after_up()
            return True
        # 이 후보가 실패했지만 그 사이 다른 프로세스가 포트를 잡았을 수도 있으니 재확인
        if is_local_runtime_up(port, runtime):
            print(f"[로컬] 서버가 포트 {port}에 떠 있음 -> 재사용")
            _after_up()
            return True

    print(f"[로컬][오류] 모든 기동 명령({', '.join(c[0] for c in found)})이 실패했습니다.")
    print(f"[로컬] 위 서버 로그를 확인하세요. 흔한 원인:")
    print(f"        - 포트 {port} 이미 사용 중 -> 그 서버를 재사용해야 하는데 감지 실패")
    print(f"        - 메모리 부족(다른 앱, 특히 브라우저를 닫고 재시도)")
    print(f"        - 해결이 안 되면 수동으로 {spec['label']}를 먼저 켜두고 이 스크립트를 다시 실행")
    return False


# 하위 호환용 별칭
ensure_lemonade_server = ensure_local_runtime


def shutdown_local_runtime():
    """스크립트가 직접 띄운 서버만 종료 (원래 켜져 있던 건 건드리지 않음)."""
    global _LOCAL_PROC
    if _LOCAL_PROC is not None:
        print("[로컬] 자동 기동한 로컬 서버 종료")
        try:
            _LOCAL_PROC.terminate()
            _LOCAL_PROC.wait(timeout=10)
        except Exception:
            try:
                _LOCAL_PROC.kill()
            except Exception:
                pass
        _LOCAL_PROC = None


# 하위 호환용 별칭
shutdown_lemonade_server = shutdown_local_runtime


def make_local_entry(args, device: str = "npu") -> KeyEntry:
    """로컬 NPU/GPU용 KeyEntry 생성 (OpenAI 호환 클라이언트를 로컬 엔드포인트로 지정).
    device는 로그 라벨 구분용("local-NPU"/"local-GPU")이며 실제 호출 경로는 동일하다
    (같은 런타임 서버가 내부적으로 NPU/GPU 중 뭘 쓸지는 그 런타임이 알아서 결정)."""
    from openai import OpenAI as OpenAIClient
    runtime = getattr(args, "local_runtime", DEFAULT_LOCAL_RUNTIME)
    model = resolve_local_model_for_device(args, device)
    client = OpenAIClient(base_url=local_base_url(args.local_port, runtime), api_key="local",
                          timeout=args.local_timeout, max_retries=0)
    label = f"local-{device.upper()}({get_runtime_spec(runtime)['label']})"
    return KeyEntry(provider="openai", model=model, client=client,
                    label=label, is_local=True)


# ---------------------------------------------------------------------------
# 로컬 모델 선택 메뉴 + 양자화 프리셋
# ---------------------------------------------------------------------------
# 양자화 비트별 로컬 처리 파라미터 (낮은 비트 = 낮은 품질/불안정 -> 작게 나눠서 실패 파장 축소)
_QUANT_PRESETS = {
    2: {"batch_chars": 450,  "batch_segs": 2,  "max_tokens": 3072},
    4: {"batch_chars": 1000, "batch_segs": 5,  "max_tokens": 4096},
    8: {"batch_chars": 2500, "batch_segs": 16, "max_tokens": 6144},
}
_QUANT_RE = re.compile(r'(?:^|[-_.])(?:e(?P<eb>[2-8])b|(?P<plain>[2-8])b|q(?P<q>[2-8])(?:[_-]\d+)?|int(?P<int>[2-8]))(?:$|[-_.])', re.IGNORECASE)


def detect_quant_bits(model_name: str) -> int | None:
    """모델명에서 e2b/e4b, 2b/4b/8b, q4_1, int4 형식의 양자화 비트를 감지한다."""
    m = _QUANT_RE.search(model_name)
    if not m:
        return None
    for key in ("eb", "plain", "q", "int"):
        if m.groupdict().get(key):
            return int(m.group(key))
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
    if getattr(args, "model_select_timeout", 10.0) <= 0:
        # GUI 등에서 모델을 이미 지정한 경우: 메뉴 없이 즉시 진행 (stdin 없는 환경 대응)
        return default_model
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
        # 소형 로컬 모델이 translations 배열을 중간에 닫고 뒤 객체를 배열 밖에
        # 이어 쓰는 흔한 오류를 복구한다. JSON 전체가 깨져도 완전한 segment 객체는 회수한다.
        items = []
        obj_pat = re.compile(
            r'\{\s*"segment_id"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*'
            r'"translated_text"\s*:\s*"((?:\\.|[^"\\])*)"\s*\}', re.DOTALL)
        for m in obj_pat.finditer(payload):
            try:
                sid = json.loads('"' + m.group(1) + '"')
                txt = json.loads('"' + m.group(2) + '"', strict=False)
                items.append({"segment_id": sid, "translated_text": txt})
            except Exception:
                continue
        if items:
            data = {"translations": items}
            print(f"    [로컬] 비정상 JSON 자동 복구: {len(items)}개 세그먼트 회수")
        else:
            try:
                data = json.loads(payload, strict=False)
            except Exception:
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


def is_auth_error(e: Exception) -> bool:
    """
    키 자체가 잘못됐거나 차단된 '진짜 영구' 오류 (시간이 지나도 절대 안 풀림).
    이 키는 revive 대상에서 제외한다.
    """
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code in (401, 403):
        return True
    s = str(e).lower()
    return any(kw in s for kw in (
        "401",                          # 인증 실패 (잘못된/만료된 키)
        "unauthenticated",              # Gemini: 인증 자격 증명 오류
        "unauthorized",
        "invalid_api_key", "invalid api key", "api key not valid",
        "access_token_type_unsupported",
        "permission_denied", "denied access",  # 403: 프로젝트/키 자체가 차단됨
        "invalid authentication credentials",
        "billing",                      # 결제 관련 하드 한도 (결제 등록 전엔 안 풀림)
        "credit balance",               # Anthropic: 크레딧 부족
    ))


def is_quota_exhaustion(e: Exception) -> bool:
    """
    할당량 소진 계열 (일일 한도 등). 지금은 못 쓰지만 리셋 시간이 지나면
    다시 쓸 수 있으므로, revive_at을 설정해 나중에 자동 복귀시킨다.
    """
    s = str(e).lower()
    return any(kw in s for kw in (
        "perday",                       # Gemini: GenerateRequestsPerDayPerProjectPerModel-FreeTier 등
        "insufficient_quota",           # OpenAI: 크레딧/결제 한도 소진 (충전 시 풀리므로 재확인 가치 있음)
        "quota exceeded", "quota_exceeded",
    ))


def is_permanent_exhaustion(e: Exception) -> bool:
    """
    '이 키로는 지금 당장 계속 시도해도 안 되는' 종류인지 판별
    (인증/차단/결제 + 일일 할당량 소진 모두 포함).
    호출측에서 is_auth_error()로 진짜 영구인지, is_quota_exhaustion()으로
    시간이 지나면 부활 가능한지 구분해 revive_at을 결정한다.
    """
    return is_auth_error(e) or is_quota_exhaustion(e)


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
        if STOP_EVENT.is_set():
            print(f"    [로컬] 사용자 중단 요청 -> 남은 {total - ci + 1}개 청크 건너뜀")
            break
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
        할당량 소진으로 죽었던 키는 revive_at(서버가 알려준 리셋 시각)이 지나면
        자동으로 부활시킨다 -> 로컬 NPU로 작업 중이어도 다음 배치부터 API로 복귀.
        """
        now = time.monotonic()
        for e2 in pool:
            if not e2.alive and e2.revive_at is not None and now >= e2.revive_at:
                e2.alive = True
                e2.revive_at = None
                print(f"  [부활] 키 {e2.label} 할당량 리셋 시간 경과 -> 재시도 대상으로 복귀")
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
                local_label = pool[local[0]].label
                print(f"  [폴백] {reason} -> {local_label}(으)로 전환 시도")
                if not ensure_local_runtime(args):
                    # 서버 기동 실패 -> 로컬도 못 쓰므로 죽은 것으로 처리
                    for i in local:
                        pool[i].alive = False
                    return _wait_for_revival()
                # 메뉴에서 선택된(또는 기본) 모델을 반영하되, 각 로컬 엔트리는 자기 device
                # (NPU/GPU)에 맞는 모델만 받는다 - 예전엔 전부 같은 모델로 덮어써서 GPU
                # 엔트리도 NPU 전용(-FLM) 모델을 강제로 받는 버그가 있었다(Lemonade는 장치를
                # 모델의 recipe로 고정하므로, 이러면 "GPU 체크"가 무시되고 NPU만 도는 결과가 됨).
                for i in local:
                    device_of_entry = model_recipe_device(pool[i].model)
                    pool[i].model = resolve_local_model_for_device(args, device_of_entry)
                local_started["presets"] = local_presets_for(pool[local[0]].model)
                local_started["done"] = True
            return local[0]
        return _wait_for_revival()

    def _wait_for_revival() -> int | None:
        """
        번역 수단이 하나도 없지만 할당량 리셋으로 부활 예정인 키가 있으면
        (10분 이내 한정) 그때까지 대기했다가 부활시켜 반환. 없으면 None(중단).
        """
        pending = [e2 for e2 in pool if not e2.alive and e2.revive_at is not None]
        if not pending:
            return None
        soonest = min(e2.revive_at for e2 in pending)
        wait = soonest - time.monotonic()
        if wait > 600:
            print(f"  [대기 포기] 가장 빠른 할당량 리셋까지 {wait/60:.0f}분 남음 (10분 초과) -> 중단")
            return None
        if wait > 0:
            print(f"  [대기] 번역 수단 없음. 할당량 리셋까지 {wait:.0f}초 대기...")
            end = time.monotonic() + wait
            while time.monotonic() < end:
                if STOP_EVENT.is_set():
                    return None
                time.sleep(min(1.0, end - time.monotonic()))
        return next_alive_index(0)

    aborted = False
    abort_page: int | None = None
    stopped_by_user = False
    total_pages = len({s.page for s in targets})  # 번역 대상이 있는 페이지 수 (진행 표시용)
    pages_done: set[int] = set()

    for bi, batch in enumerate(batches, 1):
        if STOP_EVENT.is_set():
            stopped_by_user = True
            first_left = min(s.page for s in batch) + 1
            print(f"  [중단] 사용자 요청 -> {bi}번째 배치({first_left}페이지)부터 원문 유지하고 저장 진행")
            break
        remaining = {s.seg_id: s for s in batch}
        attempt = 0
        rl_retry = 0
        keys_tried_since_success = 0
        no_progress = 0  # 성공 응답인데 remaining이 줄지 않은 연속 횟수 (모델의 세그먼트 누락 반복 감지)
        while remaining:
            if STOP_EVENT.is_set():
                stopped_by_user = True
                print(f"  [중단] 사용자 요청 -> 현재 배치의 남은 {len(remaining)}개 세그먼트는 "
                      f"원문 유지하고 저장 진행")
                break
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
                    # 인증/차단(진짜 영구) vs 할당량 소진(리셋 시간 지나면 부활 가능) 구분
                    entry.alive = False
                    if is_auth_error(e):
                        entry.revive_at = None
                        print(f"  [batch {bi}/{len(batches)}] 키 {entry.label} 영구 오류(인증/권한/결제) "
                              f"-> 이번 실행에서 완전 제외: {str(e)[:200]}")
                    else:
                        # 할당량 소진: 서버 제시 리셋 시간(없으면 30분) 후 자동 부활 예약
                        delay = extract_retry_delay(e, default=1800.0)
                        entry.revive_at = time.monotonic() + delay
                        print(f"  [batch {bi}/{len(batches)}] 키 {entry.label} 할당량 소진 "
                              f"-> {delay/60:.0f}분 후 자동 재시도 예약 (그동안 다른 키/NPU 사용)")
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
                        end = time.monotonic() + delay
                        while time.monotonic() < end and not STOP_EVENT.is_set():
                            time.sleep(min(1.0, max(end - time.monotonic(), 0.05)))
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
            pages_done.add(s.page)
        prev_pairs = prev_pairs[-12:]
        total_chars_sent += sum(len(s.text) for s in batch)
        done = sum(1 for s in targets if s.translated is not None and s.translated != s.text)
        print(f"  [batch {bi}/{len(batches)}] 완료 (실제 번역 누적 {done}/{len(targets)} 세그먼트)")
        # GUI 진행 표시용 구조화 라인 (사람도 읽을 수 있는 형식)
        pct = 100.0 * bi / max(len(batches), 1)
        print(f"  [진행] batch={bi}/{len(batches)} pages={len(pages_done)}/{total_pages} "
              f"pct={pct:.1f}")

        if aborted:
            break

    # 처리되지 못한 이후 배치들도 원문 유지로 채워둔다 (재구성 단계 안전장치)
    for s in targets:
        if s.translated is None:
            s.translated = s.text
            s.translation_failed = True

    if stopped_by_user:
        status_word = "사용자 중단(진행분까지 저장)"
    elif aborted:
        status_word = "중단됨"
    else:
        status_word = "완료"
    print(f"[3/4] 번역 {status_word}: {len(targets)}개 세그먼트, "
          f"원문 {total_chars_sent:,}자 전송")
    return aborted or stopped_by_user


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


def _normalize_translation_text(text: str) -> str:
    """모델이 만든 불필요한 공백만 정리하고 명시적 줄바꿈은 보존한다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _insert_vertical_text_manual(page, rect, text: str, seg: Segment, font_scale: float) -> bool:
    """
    세로쓰기(일본어/한국어 종서) 전용 렌더러.

    insert_htmlbox의 rotate=90 파라미터는 텍스트 줄 전체를 하나의 강체로 90도
    돌려버려서 글자 자체가 옆으로 누운 채 나온다(고개를 기울여야 읽히고, 읽는
    방향도 위->아래가 아니라 회전된 좌->우가 됨) - 진짜 세로쓰기가 아니다.
    CSS 'writing-mode: vertical-rl'도 mupdf Story가 지원하지 않는 것으로 확인됐다.
    그래서 글자를 하나씩 직접 배치해 각 글자는 똑바로 세운 채 위->아래로 쌓는다
    (실제 세로쓰기와 동일한 방식). 한 컬럼(세로줄)에 다 안 들어가면 오른쪽에서
    왼쪽으로 새 컬럼을 만들어 이어간다(전통적 세로쓰기 진행 방향과 동일 - 원본도
    이 순서로 배치돼 있었다). 원래 bbox의 상단에 딱 붙여 시작해 원본과 같은
    위치를 유지한다.
    """
    plain = _normalize_translation_text(text).replace("\n", "")
    # 세로쓰기에서는 공백이 별도 칸을 차지하지 않아야 한다 - 공백마다 한 칸씩 비우면
    # (원래 코드가 그랬음) 번역문에 있는 여러 개의 공백(한국어는 띄어쓰기가 잦음)만큼
    # 예상보다 훨씬 많은 세로 공간이 필요해져서, 텍스트가 여러 조각으로 쪼개진 것처럼
    # 큰 간격이 생기거나(원래 bbox 상단에 붙어야 할 텍스트가 아래로 밀려 보임의 원인),
    # 그 공간을 맞추려다 폰트가 불필요하게 축소되는 문제가 있었다. 완전히 제거한다.
    plain = plain.replace(" ", "").replace("\u3000", "")
    if not plain:
        return True

    rect = pymupdf.Rect(rect)
    color = hex_to_rgb01(seg.color)
    base_fs = max(4.0, seg.font_size * font_scale)
    min_fs = max(3.5, base_fs * 0.4)

    size = base_fs
    while size >= min_fs:
        row_h = size * 1.15   # 글자 하나가 차지하는 세로 칸 높이
        col_w = size * 1.15   # 컬럼(세로줄) 하나의 가로 폭
        rows_per_col = max(1, int(rect.height // row_h))
        n_cols = math.ceil(len(plain) / rows_per_col)
        needed_w = n_cols * col_w
        if needed_w <= rect.width + 0.5:
            try:
                idx = 0
                for c_i in range(n_cols):
                    # 오른쪽 끝 컬럼부터 시작해 왼쪽으로 진행 (세로쓰기 전통적 읽기 순서)
                    x = rect.x1 - col_w * (c_i + 1) + col_w * 0.1
                    y = rect.y0 + size  # 첫 글자의 baseline (bbox 상단에 붙임)
                    for _ in range(rows_per_col):
                        if idx >= len(plain):
                            break
                        ch = plain[idx]
                        page.insert_text((x, y), ch, fontsize=size,
                                         fontname="korea", color=color)
                        y += row_h
                        idx += 1
                    if idx >= len(plain):
                        break
                return True
            except Exception:
                pass
        size *= 0.92
    return False


def _insert_text_in_rect(page, rect, text, seg: Segment, font_scale: float) -> bool:
    """
    V3.8: 원래 bbox 밖으로 확장하지 않는다.
    확장은 인접 목차 항목/다단 텍스트를 침범해 겹침을 만들기 때문이다.
    원본 블록의 위치/폭/높이를 고정하고 글꼴 크기만 단계적으로 줄인다.
    """
    text = _normalize_translation_text(text)
    if not text:
        return True

    rect = pymupdf.Rect(rect)
    base_fs = max(4.0, seg.font_size * font_scale)
    min_fs = max(3.5, base_fs * 0.45)
    color = hex_to_rgb01(seg.color)
    weight = "bold" if seg.bold else "normal"

    # 세로쓰기는 전용 수동 렌더러를 최우선 사용 (아래 rotate=90 방식은 글자가
    # 통째로 누워버리는 문제가 있어 폴백으로만 남겨둠).
    if seg.vertical:
        if _insert_vertical_text_manual(page, rect, text, seg, font_scale):
            return True

    # HTML 삽입: CJK 폰트 폴백과 자동 맞춤을 우선 사용.
    if hasattr(page, "insert_htmlbox"):
        body = html_mod.escape(text).replace("\n", "<br>")
        # pt를 사용해 PDF 원본 font_size와 단위를 맞춘다 (기존 px 사용은 크기 왜곡 원인).
        css = ("* {margin:0;padding:0;font-family:sans-serif;"
               f"font-size:{base_fs:.2f}pt;color:{seg.color};font-weight:{weight};"
               "line-height:1.08;}")
        # 주의: CSS 'writing-mode: vertical-rl'는 mupdf Story가 지원하지 않는다(CSS2 수준까지만
        # 지원 확인됨). rotate=90은 줄 전체를 강체로 돌려 글자가 누운 채 나오므로
        # (실사용 테스트에서 확인) 세로쓰기의 정식 방법이 아니다 - 위 수동 렌더러 실패시의
        # 최후 폴백으로만 사용한다.
        rotate = 90 if seg.vertical else 0
        try:
            spare, scale = page.insert_htmlbox(
                rect, f"<div>{body}</div>", css=css, scale_low=0.45, rotate=rotate
            )
            if spare is None or spare >= 0:
                return True
        except Exception:
            pass

    # 폴백: bbox 안에 들어갈 때까지 점진 축소.
    size = base_fs
    while size >= min_fs:
        try:
            rc = page.insert_textbox(
                rect, text, fontsize=size, fontname="korea",
                color=color, lineheight=1.08
            )
            if rc >= 0:
                return True
        except Exception:
            pass
        size *= 0.92
    return False


def insert_translated_text(page, seg: Segment, font_scale: float) -> bool:
    # V3.8에서는 물리 블록 병합을 하지 않으므로 항상 원래 bbox 하나에 삽입한다.
    text = (seg.translated or "").replace("|||SUB_SEPARATOR|||", "\n").strip()
    return _insert_text_in_rect(page, seg.bbox, text, seg, font_scale)


def _estimate_bg_color(page, bbox) -> tuple:
    """
    OCR 세그먼트(이미지 위 텍스트) 영역의 배경색을 추정한다. 원본이 이미지라 텍스트를
    redact로 지울 수 없으므로(별도 텍스트 객체가 아니라 픽셀이라서), 번역문을 얹기 전에
    이 배경색으로 사각형을 그려 원본(원어) 글자를 가려야 한다 - 안 그러면 원문 픽셀과
    번역문 글자가 겹쳐 보인다. 해당 영역을 저해상도로 렌더링해 가장 흔한 색상을 뽑는다
    (실패하면 흰색으로 폴백 - 스캔 문서 대부분의 배경).
    """
    try:
        rect = pymupdf.Rect(bbox)
        pix = page.get_pixmap(clip=rect, dpi=36)  # 대표 색상만 필요하므로 저해상도로 충분
        samples = pix.samples
        n = pix.n
        counter: dict[bytes, int] = {}
        step = max(n, 1)
        for i in range(0, len(samples) - step + 1, step):
            key = bytes(samples[i:i + min(3, step)])
            counter[key] = counter.get(key, 0) + 1
        if counter:
            best = max(counter.items(), key=lambda kv: kv[1])[0]
            if len(best) >= 3:
                return (best[0] / 255, best[1] / 255, best[2] / 255)
            elif len(best) == 1:
                g = best[0] / 255
                return (g, g, g)
    except Exception:
        pass
    return (1, 1, 1)


def rebuild_pdf(doc, segments: list[Segment], font_scale: float) -> int:
    by_page: dict[int, list[Segment]] = defaultdict(list)
    for s in segments:
        if s.needs_translation and s.translated:
            by_page[s.page].append(s)

    truncated = 0
    for pno in sorted(by_page):
        page = doc[pno]
        # OCR로 얻은 세그먼트는 원본에 텍스트 레이어가 없다(이미지 위의 픽셀일 뿐이라
        # redact로 지울 대상 자체가 없음). 대신 배경색으로 그 영역을 덮어 원문 픽셀을
        # 가린 뒤 번역문을 얹는다 - 안 그러면 원어 글자가 번역문과 겹쳐 보인다.
        ocr_segs = [s for s in by_page[pno] if s.is_ocr]
        redactable = [s for s in by_page[pno] if not s.is_ocr]
        for s in redactable:
            page.add_redact_annot(pymupdf.Rect(s.bbox), fill=False)
        if redactable:
            apply_redactions_safe(page)
        for s in ocr_segs:
            bg = _estimate_bg_color(page, s.bbox)
            # bbox가 OCR로 추정한 영역이라 실제 원본 글자보다 약간 작게 잡힐 수 있어(특히
            # 상단 획이나 하강 부분), 살짝 확장해서 가장자리에 원문 잔여 픽셀이 안 남게 한다.
            pad = max(1.0, s.font_size * 0.12)
            cover_rect = pymupdf.Rect(s.bbox) + (-pad, -pad, pad, pad)
            page.draw_rect(cover_rect, color=None, fill=bg, overlay=True)
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
_RANGE_TOKEN = r"\d{3}-\d{3}(?:-MULTI\d+)?"
RESUME_FILENAME_RE = re.compile(
    rf"^(?P<base>.+?)_(?:translated|T)_(?P<tranges>{_RANGE_TOKEN}(?:_{_RANGE_TOKEN})*)"
    rf"_(?:untranslated|unT)_(?P<uranges>{_RANGE_TOKEN}(?:_{_RANGE_TOKEN})*)$"
)
# 파일명에 구간을 직접 나열하는 대신 압축(MULTI) 표기로 전환하는 기준
_COMPACT_RANGE_COUNT_THRESHOLD = 5   # 구간 수가 이보다 많으면 압축
_COMPACT_STEM_LENGTH_THRESHOLD = 140  # 풀어쓴 stem 길이가 이보다 길면 압축


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


def _parse_range_tokens(s: str) -> tuple[list[tuple[int, int]], bool]:
    """'010-020_030-034' 또는 압축형 '010-090-MULTI12'를 파싱. (구간목록, 압축여부)"""
    ranges: list[tuple[int, int]] = []
    is_compact = False
    for part in s.split("_"):
        m = re.match(r"(\d{3})-(\d{3})(?:-MULTI(\d+))?$", part)
        if not m:
            continue
        ranges.append((int(m.group(1)), int(m.group(2))))
        if m.group(3) is not None:
            is_compact = True
    return ranges, is_compact


def parse_resume_filename(stem: str) -> dict | None:
    """
    '<base>_translated_###-@@@_untranslated_$$$-%%%[_...]' (축약형 _T_/_unT_, 압축형 -MULTIn 포함)
    패턴을 파일명에서 감지한다. 압축형(MULTIn)이면 정확한 구간을 파일명만으로는 복원할 수 없으므로
    u_ranges/t_ranges를 None으로 반환해 호출측이 사이드카 JSON을 찾도록 신호한다.
    """
    m = RESUME_FILENAME_RE.match(stem)
    if not m:
        return None
    t_ranges, t_compact = _parse_range_tokens(m.group("tranges"))
    u_ranges, u_compact = _parse_range_tokens(m.group("uranges"))
    if t_ranges == [(0, 0)]:
        t_ranges = []
    if u_ranges == [(0, 0)]:
        u_ranges = []
    unresolved = t_compact or u_compact
    return {
        "base": m.group("base"),
        "t_ranges": None if unresolved else t_ranges,
        "u_ranges": None if unresolved else u_ranges,
        "t_start": t_ranges[0][0] if t_ranges else 0,
        "t_end": t_ranges[-1][1] if t_ranges else 0,
        "unresolved": unresolved,
    }


def sidecar_path_for(pdf_path: Path) -> Path:
    return pdf_path.with_name(pdf_path.stem + ".progress.json")


def write_progress_sidecar(out_path: Path, base_stem: str,
                           t_ranges: list[tuple[int, int]],
                           u_ranges: list[tuple[int, int]],
                           doc_page_count: int) -> None:
    """
    출력 PDF 옆에 정확한 페이지 진행정보를 JSON으로 남긴다. 파일명이 압축형(MULTIn)으로
    표시된 경우에도 이 파일이 있으면 이어서-번역 시 정확한 구간을 그대로 복원할 수 있다.
    파일명을 사람이 옮기거나 사이드카만 지워도, 파일명이 비압축형이면 파일명만으로 복원 가능.
    """
    data = {
        "base": base_stem,
        "t_ranges": [list(r) for r in t_ranges],
        "u_ranges": [list(r) for r in u_ranges],
        "doc_page_count": doc_page_count,
    }
    try:
        sidecar_path_for(out_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[경고] 진행정보 사이드카(.progress.json) 저장 실패(무시하고 계속): {e}")


def load_resume_info(in_path: Path) -> dict | None:
    """
    사이드카 JSON을 우선 사용하고(가장 정확), 없으면 파일명에서 파싱한다.
    파일명이 압축형(MULTIn)인데 사이드카가 없으면 정확한 구간 복원이 불가하므로 경고 후 None.
    """
    sc = sidecar_path_for(in_path)
    if sc.exists():
        try:
            data = json.loads(sc.read_text(encoding="utf-8"))
            t_ranges = [tuple(r) for r in data["t_ranges"]]
            u_ranges = [tuple(r) for r in data["u_ranges"]]
            return {
                "base": data["base"], "t_ranges": t_ranges, "u_ranges": u_ranges,
                "t_start": t_ranges[0][0] if t_ranges else 0,
                "t_end": t_ranges[-1][1] if t_ranges else 0,
                "unresolved": False, "from_sidecar": True,
            }
        except Exception as e:
            print(f"[경고] 사이드카 진행정보(.progress.json) 손상, 무시하고 파일명으로 시도: {e}")
    info = parse_resume_filename(in_path.stem)
    if info and info.get("unresolved"):
        print("[경고] 파일명이 압축 형식(MULTIn)인데 사이드카(.progress.json)를 찾지 못해 "
              "정확한 이어서-번역이 불가합니다. 이 파일은 새 문서로 처리합니다. "
              "(사이드카 파일을 원본 PDF와 같은 폴더에 그대로 둬야 합니다)")
        return None
    return info


def build_output_stem(base_stem: str, t_ranges: list[tuple[int, int]],
                      u_ranges: list[tuple[int, int]]) -> tuple[str, bool]:
    """
    번역 완료/미완료 페이지 집합을 파일명에 기록한다.
    구간 수가 많거나(> 5) 풀어쓴 길이가 길면(> 140자) 압축형(-MULTIn)으로 전환하고,
    정확한 구간은 사이드카(.progress.json)에 저장하도록 True를 반환한다.
    반환값: (파일명 stem, 사이드카 필요 여부)
    """
    fmt = lambda n: f"{n:03d}"

    def full_part(tag: str, ranges: list[tuple[int, int]]) -> str:
        disp = ranges if ranges else [(0, 0)]
        return f"_{tag}_" + "_".join(f"{fmt(a)}-{fmt(b)}" for a, b in disp)

    def compact_part(tag: str, ranges: list[tuple[int, int]]) -> str:
        if not ranges:
            return f"_{tag}_000-000"
        lo, hi = min(a for a, _ in ranges), max(b for _, b in ranges)
        return f"_{tag}_{fmt(lo)}-{fmt(hi)}-MULTI{len(ranges)}"

    needs_compact = len(t_ranges) > _COMPACT_RANGE_COUNT_THRESHOLD or \
        len(u_ranges) > _COMPACT_RANGE_COUNT_THRESHOLD
    if not needs_compact:
        stem = base_stem + full_part("translated", t_ranges) + full_part("untranslated", u_ranges)
        if len(stem) <= _COMPACT_STEM_LENGTH_THRESHOLD:
            return stem, False
        # 구간 수는 적은데 base_stem 자체가 길어서 넘친 경우 -> 축약 태그(_T_/_unT_)만 우선 시도
        short_stem = base_stem + full_part("translated", t_ranges).replace("_translated", "_T") + \
            full_part("untranslated", u_ranges).replace("_untranslated", "_unT")
        if len(short_stem) <= _COMPACT_STEM_LENGTH_THRESHOLD + 20:
            return short_stem, False

    stem = base_stem + compact_part("translated", t_ranges) + compact_part("untranslated", u_ranges)
    if len(stem) > 200:
        # base_stem 자체가 극단적으로 긴 경우: 해시로 축약(사이드카 JSON이 유일한 진실 소스가 됨)
        h = hashlib.sha1(base_stem.encode("utf-8")).hexdigest()[:8]
        stem = f"{base_stem[:60]}_{h}" + \
            compact_part("translated", t_ranges) + compact_part("untranslated", u_ranges)
    return stem, True


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
    # --- 로컬 NPU/GPU (Lemonade / Ollama / LM Studio 등) 폴백 ---
    ap.add_argument("--local-runtime", default=DEFAULT_LOCAL_RUNTIME,
                    choices=list(RUNTIME_REGISTRY),
                    help=f"클라우드 API 소진 시 폴백으로 쓸 로컬 AI 런타임 (기본: {DEFAULT_LOCAL_RUNTIME}). "
                         f"지원: {', '.join(RUNTIME_REGISTRY)}. NPU 가속은 지금 lemonade(AMD XDNA2)만 "
                         f"지원하고 나머지는 GPU만 지원한다.")
    ap.add_argument("--local-device", default=None,
                    help="로컬 폴백에 사용할 장치, 콤마로 여러 개 지정 가능 (예: 'npu', 'gpu', 'npu,gpu'). "
                         "먼저 지정한 장치를 우선 사용하고, 그 장치 쪽 키가 전부 죽어야 다음 장치로 "
                         "넘어간다. --local-npu(하위호환)만 주면 'npu'와 동일하게 동작한다.")
    ap.add_argument("--local-npu", action="store_true",
                    help="(하위호환 별칭) --local-device npu 와 동일. 클라우드 API가 전부 소진되면 "
                         "로컬 NPU로 이어서 번역. 서버가 안 떠 있으면 자동으로 백그라운드 기동함")
    ap.add_argument("--no-local-npu", action="store_true",
                    help="로컬 폴백을 비활성화 (--local-device/--local-npu가 지정돼 있어도 무시)")
    ap.add_argument("--model-local", default=None,
                    help=f"로컬 모델 이름 (기본: device별로 자동 선택, "
                         f"npu={DEFAULT_LOCAL_MODEL_BY_DEVICE['npu']}, "
                         f"gpu={DEFAULT_LOCAL_MODEL_BY_DEVICE['gpu']}). "
                         f"NPU/GPU를 동시에 쓸 땐 --model-local-npu/--model-local-gpu로 "
                         f"각각 따로 지정하는 걸 권장 (모델은 장치별 recipe가 고정돼 있어서 "
                         f"하나의 모델로 NPU/GPU를 겸용할 수 없다).")
    ap.add_argument("--model-local-npu", default=None,
                    help=f"NPU 전용 모델 지정 (기본: {DEFAULT_LOCAL_MODEL_BY_DEVICE['npu']})")
    ap.add_argument("--model-local-gpu", default=None,
                    help=f"GPU 전용 모델 지정 (기본: {DEFAULT_LOCAL_MODEL_BY_DEVICE['gpu']})")
    ap.add_argument("--local-port", type=int, default=None,
                    help="로컬 런타임 포트 (기본: 선택한 --local-runtime의 기본 포트, "
                         f"lemonade={RUNTIME_REGISTRY['lemonade']['default_port']}, "
                         f"ollama={RUNTIME_REGISTRY['ollama']['default_port']}, "
                         f"lmstudio={RUNTIME_REGISTRY['lmstudio']['default_port']})")
    ap.add_argument("--local-serve-cmd", default=None,
                    help="로컬 런타임 실행 명령/경로 직접 지정 (기본: RUNTIME_REGISTRY의 후보를 자동 탐색)")
    ap.add_argument("--local-timeout", type=float, default=300.0,
                    help="로컬 NPU/GPU 요청 타임아웃(초). 느릴 수 있으므로 넉넉하게 (기본: 300)")
    ap.add_argument("--local-ctx-size", type=int, default=8192,
                    help="(Lemonade 전용) 로컬 모델 로드시 컨텍스트 크기(토큰). 번역 프롬프트가 길어 "
                         "기본값(보통 4096 이하)으로는 JSON 출력 지시가 잘릴 수 있어 넉넉히 잡음 (기본: 8192)")
    ap.add_argument("--model-select-timeout", type=float, default=10.0,
                    help="(Lemonade 전용) 로컬 모델 선택 메뉴의 입력 대기 시간(초). 시간 내 입력이 없으면 "
                         "기본 모델로 자동 진행 (기본: 10)")
    ap.add_argument("--no-merge", action="store_true",
                    help="문장 단절 블록 자동 병합 비활성화 (PDF가 문장을 여러 블록으로 쪼갠 경우 "
                         "기본적으로 병합해서 번역 품질을 높임)")
    ap.add_argument("--no-compress", action="store_true",
                    help="번역 후 PDF 압축본(<파일명>_compressed.pdf) 생성을 건너뜀. "
                         "기본적으로는 저장 직후 자동으로 압축본을 별도 생성한다(원본은 그대로 유지).")
    ap.add_argument("--tessdata-dir", default=None,
                    help="Tesseract 언어 데이터(tessdata) 폴더 직접 지정. 자동 탐지가 실패할 때 사용 "
                         "(Windows 기본 경로 예: 'C:\\Program Files\\Tesseract-OCR\\tessdata')")
    ap.add_argument("--ocr-lang", default=None,
                    help="OCR 언어 코드 (Tesseract 언어 데이터 이름 기준, 예: eng/jpn/kor/jpn_vert). "
                         "여러 언어를 함께 인식하려면 '+'로 연결: 'eng+jpn'. "
                         "기본값: --source-lang에서 자동 매핑(예: Japanese -> jpn+jpn_vert)")
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


def _parse_local_devices(args) -> list[str]:
    """--local-device/--local-npu/--no-local-npu를 종합해 사용할 장치 순서 목록을 만든다."""
    if getattr(args, "no_local_npu", False):
        return []
    if getattr(args, "local_device", None):
        devices = [d.strip().lower() for d in args.local_device.split(",") if d.strip()]
        valid = {"npu", "gpu"}
        bad = [d for d in devices if d not in valid]
        if bad:
            raise SystemExit(f"[오류] --local-device에 알 수 없는 장치: {bad} (사용 가능: npu, gpu)")
        return devices
    if getattr(args, "local_npu", False):
        return ["npu"]
    return []


def main():
    args = parse_args()

    # 로컬 런타임/포트 정규화: --local-port를 안 줬으면 선택한 런타임의 기본 포트를 쓴다.
    if args.local_port is None:
        args.local_port = get_runtime_spec(args.local_runtime)["default_port"]

    in_path = Path(args.input)
    if not in_path.exists():
        sys.exit(f"[오류] 입력 파일이 없습니다: {in_path}")

    # 이어서 번역: 파일명에 이전 실행의 페이지 범위 정보가 있으면 감지
    resume_info = load_resume_info(in_path)
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
    segments = extract_segments(doc, page_filter, args.translate_all,
                                tessdata_dir=args.tessdata_dir,
                                ocr_lang=resolve_ocr_lang(args.source_lang, args.ocr_lang))
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
        # 로컬 NPU/GPU 폴백: --local-device로 지정한 장치들을 풀 맨 뒤(최후 순위)에 추가.
        # 여러 장치를 지정하면 먼저 적은 장치부터 순서대로 시도한다(예: "npu,gpu" -> NPU 우선,
        # NPU 쪽 키가 전부 죽어야 GPU로 넘어감 - next_alive_index가 pool 등장 순서를 따름).
        requested_devices = _parse_local_devices(args)
        if requested_devices:
            runtime = args.local_runtime
            spec = get_runtime_spec(runtime)
            added = []
            for device in requested_devices:
                supports_key = f"supports_{device}"
                if not spec.get(supports_key, False):
                    print(f"[정보] {spec['label']}는 {device.upper()}를 지원하지 않아 건너뜀 "
                          f"(--local-runtime {runtime} --local-device {device})")
                    continue
                entry = make_local_entry(args, device=device)
                pool.append(entry)
                added.append(entry.label)
            if added:
                print(f"[정보] 로컬 폴백 활성화: {', '.join(added)} "
                      f"(모델 {args.model_local or DEFAULT_MODELS['local']}, "
                      f"포트 {args.local_port}, 클라우드 전부 소진 시에만 사용)")
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
            shutdown_local_runtime()

    if args.export_json:
        export_translations(args.export_json, segments)

    # 이번 실행에서 (사유 불문하고) 결국 원문으로 남은 페이지를 전부 집계
    # -> 산발적으로 흩어진 실패도 각각의 구간으로 표현된다.
    target_segments = [s for s in segments if s.needs_translation]
    run_failed_pages = sorted({s.page + 1 for s in target_segments if s.translation_failed})
    run_untranslated_ranges = collapse_to_ranges(run_failed_pages)

    # '_translated_###-@@@'는 이 문서가 다루는 전체 페이지 범위(스코프)를 뜻하며,
    # 이어서-번역 시에는 최초 실행의 스코프를 그대로 유지한다(재번역 대상 페이지만 좁혀서 처리해도 안 바뀜).
    # 파일명 상태는 "실제로 번역 완료된 페이지 집합"을 누적 관리한다.
    # 이전 번역 완료 페이지 + 이번 실행에서 성공한 페이지를 합치고,
    # 전체 PDF 페이지 집합에서 이를 뺀 나머지를 미번역 페이지로 기록한다.
    # '_translated_###-@@@'는 이 문서가 다루는 전체 페이지 범위(스코프)를 뜻한다.
    # 스코프는 "문서 전체"가 아니라 "이번 작업이 다루기로 한 범위"다:
    #   - 최초 실행: --pages로 좁혔으면 그 범위, 안 좁혔으면 문서 전체
    #   - 이어서 번역: 최초 실행 때의 스코프를 그대로 유지 (재번역 대상만 좁혀도 안 바뀜)
    # 문서 전체로 고정하면, 처음부터 특정 챕터만 번역할 의도로 --pages를 준 경우에도
    # 나머지 미지정 페이지 전부가 "미번역"으로 잘못 표시된다 (예: 77-78만 지정했는데
    # 1-1095 전체가 미번역으로 찍히는 버그) - 그래서 반드시 스코프 안에서만 계산한다.
    if resume_info:
        scope_pages = set(range(resume_info["t_start"], resume_info["t_end"] + 1))
    else:
        scope_pages = set(range(run_first_page, run_last_page + 1))

    if resume_info:
        prior_scope = set(range(resume_info["t_start"], resume_info["t_end"] + 1))
        prior_untranslated = set()
        for a, b in resume_info["u_ranges"]:
            prior_untranslated.update(range(a, b + 1))
        prior_translated = prior_scope - prior_untranslated
    else:
        prior_translated = set()

    current_target_pages = {s.page + 1 for s in target_segments}
    current_failed_pages = set(run_failed_pages)
    current_success_pages = current_target_pages - current_failed_pages
    final_translated_pages = prior_translated | current_success_pages
    final_untranslated_pages = scope_pages - final_translated_pages

    final_translated_ranges = collapse_to_ranges(sorted(final_translated_pages))
    final_untranslated_ranges = collapse_to_ranges(sorted(final_untranslated_pages))

    # [4] 재구성
    # 중요: 대형/구조가 복잡한 PDF 전체를 doc.save(..., garbage=3)로 다시 쓰면
    # 원본의 손상된/비표준 xref 객체까지 전부 재해석하면서 MuPDF repair 오류가 날 수 있다.
    # 따라서 원본 파일을 먼저 임시 출력으로 그대로 복사한 뒤, 그 복사본에서
    # 실제 번역 대상 페이지만 수정하고 증분 저장(saveIncr)한다.
    # 이렇게 하면 지정 범위 밖 페이지는 재생성/변환하지 않고 원본 바이트 구조를 유지한다.
    if args.output:
        out_path = Path(args.output)
        needs_sidecar = True  # -o로 직접 지정해도 정확한 진행정보는 항상 남겨둔다
    else:
        out_stem, needs_sidecar = build_output_stem(base_stem, final_translated_ranges,
                                                    final_untranslated_ranges)
        out_path = in_path.with_name(out_stem + in_path.suffix)

    if needs_sidecar:
        write_progress_sidecar(out_path, base_stem, final_translated_ranges,
                               final_untranslated_ranges, doc.page_count)
        print(f"[정보] 미번역 구간이 많아 파일명을 압축 표기(MULTIn)했습니다. "
              f"정확한 페이지 목록은 {sidecar_path_for(out_path).name}에 저장됨 - "
              f"이어서 번역할 때 이 파일도 PDF와 같은 폴더에 있어야 합니다.")

    tmp_path = out_path.with_name(out_path.stem + ".tmp" + out_path.suffix)
    if tmp_path.exists():
        tmp_path.unlink()

    # 추출에 사용한 문서는 더 이상 저장하지 않는다.
    doc_page_count = doc.page_count  # close() 후에도 검증용으로 참조해야 하므로 미리 저장
    doc.close()
    shutil.copy2(in_path, tmp_path)

    work_doc = None
    try:
        work_doc = pymupdf.open(tmp_path)
        if work_doc.needs_pass:
            raise RuntimeError("임시 출력 PDF가 암호화되어 있습니다")

        truncated = rebuild_pdf(work_doc, segments, args.font_scale)
        try:
            # 전체 문서 폰트 재구성은 하지 않는다. subset_fonts()가 비대상 페이지의
            # 객체까지 순회할 수 있으므로 부분 번역 모드에서는 오히려 위험하다.
            pass
        except Exception:
            pass

        # 원본 복사본에 변경 객체만 추가 기록. 지정 범위 밖 페이지는 그대로 유지.
        if work_doc.can_save_incrementally():
            work_doc.saveIncr()
            work_doc.close()
            work_doc = None
        else:
            # MuPDF가 원본을 repair하여 증분 저장이 불가능한 경우의 안전 폴백.
            # PDF 페이지를 이미지/텍스트로 재렌더링하지 않는다. 수정 페이지만 별도 PDF로
            # 내보낸 뒤 pypdf가 원본 페이지 객체를 복제하고 해당 페이지만 교체한다.
            # 따라서 비대상 페이지의 글꼴/좌표/콘텐츠 스트림은 재조판되지 않는다.
            patch_path = tmp_path.with_name(tmp_path.stem + ".patch.pdf")
            patched_pages = sorted(current_target_pages)
            patch_doc = pymupdf.open()
            for page_no in patched_pages:
                patch_doc.insert_pdf(work_doc, from_page=page_no - 1, to_page=page_no - 1)
            patch_doc.save(patch_path, garbage=0, deflate=False)
            patch_doc.close()
            work_doc.close()
            work_doc = None

            try:
                from pypdf import PdfReader, PdfWriter
            except ImportError as ie:
                raise RuntimeError(
                    "증분 저장 불가 PDF 폴백에 pypdf가 필요합니다. "
                    "먼저 'pip install pypdf'를 실행하세요."
                ) from ie

            src_reader = PdfReader(str(in_path), strict=False)
            patch_reader = PdfReader(str(patch_path), strict=False)
            writer = PdfWriter()
            patch_map = {pno: i for i, pno in enumerate(patched_pages)}
            for pno in range(1, len(src_reader.pages) + 1):
                if pno in patch_map:
                    writer.add_page(patch_reader.pages[patch_map[pno]])
                else:
                    writer.add_page(src_reader.pages[pno - 1])
            with open(tmp_path, "wb") as fp:
                writer.write(fp)
            try:
                patch_path.unlink()
            except Exception:
                pass
            print(f"[저장] 증분 저장 불가 -> pypdf 페이지 객체 교체 폴백 사용 ({len(patched_pages)}페이지 수정)")

        # 저장 후 새 프로세스 관점으로 다시 열어 페이지 수와 접근 가능 여부 검증
        check = pymupdf.open(tmp_path)
        expected_pages = doc_page_count
        if check.page_count != expected_pages:
            raise RuntimeError(
                f"저장 결과 페이지 수 불일치: 기대 {expected_pages}, 실제 {check.page_count}"
            )
        # 모든 페이지를 강제로 파싱하면 원본의 비표준 객체 때문에 불필요한 repair가
        # 발생할 수 있다. 수정한 페이지만 실제 접근 검증한다.
        verify_pages = sorted(current_target_pages)
        for page_no in verify_pages:
            _ = check[page_no - 1].rect
            _ = check[page_no - 1].get_text("text")
        check.close()

    except Exception as e:
        if work_doc is not None:
            try:
                work_doc.close()
            except Exception:
                pass
        try:
            tmp_path.unlink()
        except Exception:
            pass
        sys.exit(f"[오류] 출력 PDF 저장/검증 실패. 기존 출력 파일은 교체하지 않았습니다: {e}")

    os.replace(tmp_path, out_path)
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

    final_path = out_path
    if not getattr(args, "no_compress", False):
        compressed = compress_pdf(out_path)
        if compressed is not None:
            final_path = compressed
    # GUI(및 다른 자동화 도구)가 "번역이 끝나고 최종적으로 열어야 할 파일"을 명확히
    # 파싱할 수 있도록 고유 마커 라인으로 출력한다 (압축본이 있으면 압축본, 없으면 원본).
    print(f"[최종파일] {final_path}")


def compress_pdf(src_path: Path) -> Path | None:
    """
    최종 산출물을 별도 파일(<stem>_compressed.pdf)로 재저장하며 최적화한다.
    saveIncr/pypdf 폴백 저장은 안정성을 위해 원본 바이트 구조를 최대한 보존하는 대신
    가비지 컬렉션/폰트 서브셋 같은 최적화를 하지 않아 용량이 커진다(특히 CJK 폰트를
    새로 임베드하는 번역 PDF에서 두드러짐). 저장이 끝난 뒤 완성본을 다시 열어
    한 번 더 최적화 저장하는 후처리 단계로 분리해, 기존의 검증된 안전한 저장 경로는
    건드리지 않는다. 원본(비압축) 파일은 그대로 남기고 압축본만 별도로 만든다.
    실패해도 원본엔 영향 없음(예외를 잡아 None 반환, 원본 그대로 사용).
    """
    compressed_path = src_path.with_name(src_path.stem + "_compressed" + src_path.suffix)
    try:
        cdoc = pymupdf.open(src_path)
        try:
            cdoc.subset_fonts()  # 완성된 최종본이라 전체 서브셋해도 안전 (증분저장 중엔 위험했음)
        except Exception:
            pass
        cdoc.save(compressed_path, garbage=4, deflate=True, deflate_images=True,
                  deflate_fonts=True, clean=True)
        cdoc.close()
        before = src_path.stat().st_size
        after = compressed_path.stat().st_size
        pct = 100.0 * (1 - after / before) if before else 0.0
        print(f"[압축] {before / 1048576:.1f}MB -> {after / 1048576:.1f}MB "
              f"({pct:.0f}% 감소) -> {compressed_path.name}")
        return compressed_path
    except Exception as e:
        print(f"[압축][경고] 압축 저장 실패(원본 파일은 그대로 유지됨): {e}")
        try:
            if compressed_path.exists():
                compressed_path.unlink()
        except Exception:
            pass
        return None


if __name__ == "__main__":
    main()