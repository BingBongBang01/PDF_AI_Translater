# -*- coding: utf-8 -*-
# 주의: 셰뱅 라인을 일부러 두지 않는다 - Windows의 py 런처는 첫 줄이
# '#!/usr/bin/env python3'이면 그걸 보고 실행할 인터프리터를 다시 고르는데,
# PATH의 'python3'가 마이크로소프트 스토어 스텁(WindowsApps\python3.exe)을
# 가리키는 PC가 많아 'py gui.py'로 실행해도 실제로는 그 깨진 스텁으로 넘어가
# 버려 패키지를 하나도 못 찾는 문제가 생긴다. 이 앱은 Windows 전용이라
# 셰뱅이 필요 없으므로 완전히 제거하는 것이 가장 확실한 해결책이다.
import sys, os, subprocess, re
from pdf_engine.logger import set_logger
from pdf_engine.logger.gui import GUILogger

from pathlib import Path

def _ensure_valid_environment():
    if getattr(sys, "frozen", False):
        return
    try:
        import customtkinter
        import pymupdf
        return
    except ImportError:
        pass

    NOWIN = 0x08000000 if os.name == "nt" else 0
    script_path = str(Path(__file__).resolve())
    
    if os.environ.get("_PDF_TRANSLATER_RELAUNCHED") == "1":
        req_file = Path(__file__).parent / "requirements.txt"
        if req_file.exists():
            print(f"[알림] 현재 Python({sys.executable})에 필수 패키지를 설치합니다...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
        return

    candidates = []
    if os.name == "nt":
        try:
            out = subprocess.check_output(["py", "-0p"], text=True, stderr=subprocess.DEVNULL, timeout=5, creationflags=NOWIN)
            for line in out.splitlines():
                m = re.search(r'(\S+python\.exe)\s*$', line.strip(), re.I)
                if m:
                    p = m.group(1)
                    if "WindowsApps" not in p and Path(p).is_file() and p not in candidates:
                        candidates.append(p)
        except Exception:
            pass

        progs = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
        if progs.is_dir():
            for exe in sorted(progs.glob("Python3*/python.exe"), reverse=True):
                if str(exe) not in candidates and "WindowsApps" not in str(exe):
                    candidates.append(str(exe))

    for pyexe in candidates:
        if pyexe.lower() == sys.executable.lower():
            continue
        try:
            res = subprocess.run([pyexe, "-c", "import customtkinter, pymupdf"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 timeout=10, creationflags=NOWIN)
            if res.returncode == 0:
                print(f"[자동 전환] 패키지가 설치된 Python으로 재실행합니다: {pyexe}")
                os.environ["_PDF_TRANSLATER_RELAUNCHED"] = "1"
                proc = subprocess.run([pyexe, script_path, *sys.argv[1:]])
                sys.exit(proc.returncode)
        except Exception:
            continue

    req_file = Path(__file__).parent / "requirements.txt"
    if req_file.exists():
        print(f"[알림] 필요한 패키지를 현재 Python({sys.executable})에 자동으로 설치합니다...")
        os.environ["_PDF_TRANSLATER_RELAUNCHED"] = "1"
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

_ensure_valid_environment()

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading, queue, tempfile, json, urllib.request
import contextlib, io, traceback, importlib, shutil as _shutil, time, webbrowser, base64

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ENGINE = APP_DIR / "translate_pdf.py"
PORT = 13305

# ---------------------------------------------------------------------------
# Material-style 팔레트/치수 (CustomTkinter 위에서 카드형 레이아웃을 구현하기 위한 상수).
# 완전한 Material Design 컴포넌트 세트는 아니지만, 색·모서리·여백 규칙을 일관되게
# 적용해 "머티리얼 느낌"의 톤을 낸다.
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

PRIMARY = "#3762E4"
PRIMARY_HOVER = "#2C4FC0"
DANGER = "#D8534F"
DANGER_HOVER = "#B8433F"
CARD_RADIUS = 14
CARD_PAD = 14


def _read_engine_version() -> str:
    """
    translate_pdf.py 전체를 import하지 않고 __version__ 값만 텍스트로 읽는다.
    (전체 import는 pymupdf 등 무거운 의존성을 미리 로드하게 되어, 그게 없는 환경에서
    GUI 시작 자체가 막힐 위험이 있다 - 버전 표시 하나 때문에 그 위험을 감수할 필요 없음)
    v4.28 모듈화 이후 __version__의 실제 위치가 translate_pdf.py에서 pdf_engine/config.py로
    옮겨졌다(translate_pdf.py는 이제 파사드라 값을 import만 함) - 둘 다 확인한다.
    """
    candidates = [APP_DIR / "pdf_engine" / "config" / "settings.py",
                  APP_DIR / "pdf_engine" / "config.py", ENGINE]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
            m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
            if m:
                return m.group(1)
        except Exception:
            continue
    return "?"


APP_VERSION = _read_engine_version()

# GUI에서 NPU/GPU 체크박스를 런타임별로 활성/비활성화하기 위한 최소 정보.
# translate_pdf.py 전체를 여기서 import하면 pymupdf 등 무거운 의존성이 GUI 시작 시점에
# 미리 로드돼버려서(그게 없는 환경에서 GUI 자체가 안 뜰 위험), 필요한 정보만 가볍게 복제해둔다.
# translate_pdf.py의 RUNTIME_REGISTRY를 바꾸면 이 사전도 함께 갱신해야 한다.
LOCAL_RUNTIMES = {
    "lemonade":    {"label": "Lemonade",    "supports_npu": True,  "supports_gpu": True},
    "ollama":      {"label": "Ollama",      "supports_npu": False, "supports_gpu": True},
    "lmstudio":    {"label": "LM Studio",   "supports_npu": False, "supports_gpu": True},
    "jan":         {"label": "Jan.ai",      "supports_npu": False, "supports_gpu": True},
    "koboldcpp":   {"label": "KoboldCPP",   "supports_npu": False, "supports_gpu": True},
    "anythingllm": {"label": "AnythingLLM", "supports_npu": False, "supports_gpu": True},
}

# 사용자 설정(API 키 등) 저장 위치 - 실행파일 위치와 무관하게 항상 같은 곳을 사용
CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "PDFTranslaterGUI"
CONFIG_PATH = CONFIG_DIR / "config.json"

# 언어 콤보박스 프리셋 (자유 입력도 가능 - 콤보박스가 readonly가 아님)
SOURCE_LANG_OPTIONS = ["English", "자동 인식", "한국어", "Japanese", "Chinese (Simplified)",
                       "French", "German", "Spanish"]
TARGET_LANG_OPTIONS = ["한국어", "English", "Japanese", "Chinese (Simplified)",
                       "French", "German", "Spanish"]
# GUI 표시용 '자동 인식'을 엔진이 이해하는 sentinel로 변환 (engine.resolve_source_lang과 짝)
AUTO_DETECT_LABEL = "자동 인식"
AUTO_DETECT_SENTINEL = "auto"

# API 제공자별 모델 목록 및 추천 기본값 ("직접 입력" 옵션 포함)
PROVIDER_MODELS = {
    # Gemini: 계정 할당량 표에서 RPM/TPM/RPD가 모두 0/0인 모델(= 이 계정으로는 호출 자체가
    # 불가)은 목록에서 제외했다. 제외된 것: Gemini 2 Flash / 2 Flash Lite / 2.5 Pro / 3.1 Pro.
    # 괄호 안은 (RPM / TPM / RPD) - RPD(일일 요청 수)가 실질적인 병목이라 flash-lite 계열
    # (500 RPD)이 PDF 한 권을 번역하기에 압도적으로 유리하다. flash 계열은 20 RPD라
    # 문서 하나에 하루치가 다 소진될 수 있으니 배치를 크게 잡아 요청 수를 줄인다.
    "gemini": {
        "default": "gemini-3.7-flash",
        "models": [
            "gemini-3.7-flash",        #  5 / 250K / 20  - 품질 1순위
            "gemini-3.6-flash",        #  5 / 250K / 20
            "gemini-3.5-flash",        #  5 / 250K / 20
            "gemini-3-flash",          #  5 / 250K / 20
            "gemini-2.5-flash",        #  5 / 250K / 20
            "gemini-3.5-flash-lite",   # 15 / 250K / 500 - 대량 이어받기용
            "gemini-3.1-flash-lite",   # 15 / 250K / 500
            "gemini-2.5-flash-lite",   # 10 / 250K / 20
            "직접 입력",
        ]
    },
    "anthropic": {
        "default": "claude-3-7-sonnet-20250219",
        "models": ["claude-3-7-sonnet-20250219", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229", "직접 입력"]
    },
    "openai": {
        "default": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.5-preview", "o3-mini", "o1", "직접 입력"]
    },
    "deepseek": {
        "default": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner", "직접 입력"]
    },
    "openrouter": {
        "default": "google/gemini-2.5-flash-lite",
        "models": ["google/gemini-2.5-flash-lite", "anthropic/claude-3.7-sonnet", "google/gemini-2.5-flash", "openai/gpt-4o-mini", "deepseek/deepseek-chat", "직접 입력"]
    },
    "groq": {
        "default": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "직접 입력"]
    },
    "ollama": {
        "default": "qwen2.5",
        "models": ["qwen2.5", "llama3.1", "gemma2", "직접 입력"]
    }
}

def get_provider_models(provider_name: str) -> list[str]:
    p = (provider_name or "").lower().strip()
    if p in PROVIDER_MODELS:
        return PROVIDER_MODELS[p]["models"]
    return ["default", "직접 입력"]

def get_default_model(provider_name: str) -> str:
    p = (provider_name or "").lower().strip()
    if p in PROVIDER_MODELS:
        return PROVIDER_MODELS[p]["default"]
    return "default"


# ---------------------------------------------------------------------------
# 모델 폴백 체인 - 키 하나로 여러 모델을 순서대로 갈아쓰기 위한 정보
# ---------------------------------------------------------------------------
# Gemini의 RPM/TPM/RPD 한도는 계정이 아니라 '모델별'로 따로 매겨진다. 그래서 API 키가
# 하나뿐이어도 1순위 모델의 하루 한도를 다 쓰면 2순위 모델로 갈아타 계속 번역할 수 있다.
# 엔진이 실제로 쓰는 순서/기본값의 원본은 pdf_engine/config/settings.py의 MODEL_CHAIN_INFO다
# (여기서 import해 쓰므로 두 곳이 어긋날 일이 없다). import가 실패해도 GUI는 떠야 하므로
# 실패 시엔 PROVIDER_MODELS 목록으로 대체한다.
try:
    from pdf_engine.config.settings import MODEL_CHAIN_INFO
except Exception:
    MODEL_CHAIN_INFO = {}


def get_model_chain_info(provider_name: str) -> list[dict]:
    """[{'id','rpm','rpd','note'}...] 형태의 권장 순서 목록. 정보가 없으면 목록만 만들어 준다."""
    p = (provider_name or "").lower().strip()
    info = MODEL_CHAIN_INFO.get(p)
    if info:
        return [dict(m) for m in info]
    return [{"id": m, "note": ""} for m in get_provider_models(p) if m != "직접 입력"]


def default_chain_for(provider_name: str) -> list[str]:
    """새 API 행을 만들 때 기본으로 '전부 체크'해 둘 모델 목록 (권장 순서)."""
    return [m["id"] for m in get_model_chain_info(provider_name)]


def parse_chain(text: str) -> list[str]:
    return [m.strip() for m in (text or "").split(",") if m.strip()]


def format_chain_label(models: list[str], total: int) -> str:
    """모델 선택 버튼에 표시할 요약 문자열."""
    if not models:
        return "⚠ 모델 미선택"
    head = models[0]
    if len(models) == 1:
        return f"{head}  (단일)"
    return f"{head} 외 {len(models)-1}개  ({len(models)}/{total} 사용)"


def chain_preset(models: list[str]):
    """
    폴백 체인 전체에 안전한 배치 설정을 고른다. 배치는 실행 시작 시 한 번 나뉘는데
    도중에 어떤 모델로 갈아탈지는 알 수 없으므로, 선택된 모델들 중 '가장 보수적인'
    값(배치 문자/세그먼트는 최솟값, max_tokens는 최댓값)을 쓴다. 안 그러면 큰 배치로
    나눠 놓고 작은 모델로 폴백했을 때 응답이 잘린다.
    """
    presets = [preset(m) for m in models] or [preset("")]
    return (min(p[0] for p in presets), min(p[1] for p in presets), max(p[2] for p in presets))

# Windows에서 서브프로세스가 부모(windowed EXE)와 별도로 콘솔 창을 새로 띄우는 것을 막는 플래그.
# --windowed로 빌드해도 이 플래그 없이 subprocess를 부르면 자식 프로세스용 콘솔이 반짝 뜰 수 있다.
_NOWIN = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

def _real_python_candidates():
    found=[]
    if os.name=="nt":
        try:
            out=subprocess.check_output(["py","-0p"],text=True,stderr=subprocess.DEVNULL,
                                        timeout=10,creationflags=_NOWIN)
            for line in out.splitlines():
                m=re.search(r'(\S+python\.exe)\s*$',line.strip(),re.I)
                if m:
                    p=m.group(1)
                    if "WindowsApps" not in p and Path(p).is_file() and p not in found:
                        found.append(p)
        except Exception:
            pass
        progs=Path(os.environ.get("LOCALAPPDATA",""))/"Programs"/"Python"
        if progs.is_dir():
            for exe in sorted(progs.glob("Python3*/python.exe"), reverse=True):
                if str(exe) not in found: found.append(str(exe))
    if "WindowsApps" not in str(sys.executable) and Path(sys.executable).is_file() \
       and sys.executable not in found:
        found.append(sys.executable)
    return found

def _pick_working_python():
    candidates=_real_python_candidates()
    for p in candidates:
        if _has_pymupdf(p):
            return p
    if "WindowsApps" not in str(sys.executable):
        return sys.executable
    return candidates[0] if candidates else None

def _has_pymupdf(python_exe):
    try:
        return subprocess.run([python_exe,"-c","import pymupdf"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,
            creationflags=_NOWIN).returncode==0
    except Exception:return False

def _double_click_bootstrap():
    if getattr(sys,"frozen",False) or os.name!="nt" or "WindowsApps" not in str(sys.executable):
        return
    script=str(Path(__file__).resolve())
    for pyexe in _real_python_candidates():
        if "WindowsApps" not in pyexe and _has_pymupdf(pyexe):
            subprocess.Popen([pyexe,script,*sys.argv[1:]],cwd=str(Path(__file__).resolve().parent))
            raise SystemExit(0)

_double_click_bootstrap()

PRESETS={2:(450,2,3072),4:(1000,5,4096),8:(2500,16,6144)}

CLOUD_PRESETS = {
    # (배치 문자 수, 배치 세그먼트 수, max_tokens) - 각 모델의 실제 API 상한을 웹에서
    # 확인해 그 60~80%만 쓰도록 잡았다(2026-08 기준, 출처는 각 provider 공식 문서/
    # 커뮤니티 확인 값). 상한에 딱 맞추면 번역문(특히 한글/CJK는 원문 대비 토큰 소모가
    # 크다) + JSON 래핑 오버헤드로 응답이 잘리는 사고가 나서, 항상 여유를 둔다.
    #
    # --- Gemini: 실제 max_output_tokens 상한은 2.5/3.x 계열 공통 65,536이다
    #     (thinking은 이 앱이 thinking_budget=0으로 꺼서 번역 출력에 전부 쓴다 -
    #     providers_cloud.call_gemini 참고). 진짜 병목은 max_tokens가 아니라 RPD(일일
    #     요청 수)라서, RPD 20짜리는 배치를 크게 잡아 '요청 수' 자체를 줄이는 게 유리하고
    #     (TPM 250K는 이 배치 크기에서도 여유가 있다), RPD 500인 flash-lite 2종은 굳이
    #     크게 뭉칠 필요가 없어 중간 크기를 쓴다.
    "gemini-3.7-flash": (12000, 50, 32768),
    "gemini-3.6-flash": (12000, 50, 32768),
    "gemini-3.5-flash": (12000, 50, 32768),
    "gemini-3-flash": (12000, 50, 32768),
    "gemini-2.5-flash": (12000, 50, 32768),        # RPD 20
    "gemini-2.5-flash-lite": (12000, 50, 32768),   # RPD 20 (이름은 lite지만 한도는 표준 flash와 동일)
    "gemini-3.5-flash-lite": (4000, 25, 8192),     # RPD 500 - 대량 이어받기용, 배치는 적당히
    "gemini-3.1-flash-lite": (4000, 25, 8192),     # RPD 500
    "gemini-2.5-pro": (2800, 20, 16384),           # Pro 계열 - ceiling은 같지만 응답 시간/비용 고려
    "gemini-1.5-pro": (2800, 20, 8192),            # 구세대 - ceiling 자체가 8192

    # --- Anthropic Claude: beta 헤더(output-128k-2025-02-19) 없이는 실제 상한이
    #     8,192(3.7/3.5 Sonnet, 3.5 Haiku)다. 이 앱은 그 헤더를 보내지 않으므로 보수적으로
    #     맞춘다. Opus는 애초에 상한 자체가 4,096으로 낮다.
    "claude-3-7-sonnet-20250219": (2800, 20, 8192),
    "claude-3-5-sonnet-20241022": (2800, 20, 8192),
    "claude-3-5-haiku-20241022": (3000, 20, 8192),
    "claude-3-opus-20240229": (1400, 10, 4096),

    # --- OpenAI: gpt-4o/4o-mini 실제 상한 16,384. o1/o3-mini는 상한이 100,000이지만
    #     Gemini의 thinking처럼 추론(reasoning) 토큰이 같은 예산을 갉아먹으므로 절반
    #     이하로 여유 있게 잡는다.
    "gpt-4o-mini": (5500, 28, 16384),
    "gpt-4o": (5500, 28, 16384),
    "gpt-4.5-preview": (5000, 25, 16384),
    "o3-mini": (6000, 25, 32768),
    "o1": (6000, 25, 32768),

    # --- DeepSeek: deepseek-chat 상한 8K. deepseek-reasoner는 최종 응답 상한이 기본
    #     4K/최대 8K이고, 사고 과정(최대 32K)은 별도 예산이라 이 max_tokens엔 안 잡힌다.
    "deepseek-chat": (2800, 20, 8192),
    "deepseek-reasoner": (2500, 16, 8192),

    # --- Groq: llama-3.3-70b-versatile 실제 상한 32,768. 속도는 빠르지만 70B 모델
    #     품질 편차를 고려해 배치는 절반 이하로만 채운다.
    "llama-3.3-70b-versatile": (4000, 20, 12288),
}

def bits(name):
    for p in (r'(?:^|[-_.])e([2-8])b(?:$|[-_.])',r'(?:^|[-_.])([2-8])b(?:$|[-_.])',r'(?:^|[-_.])q([2-8])(?:[_-]\d+)?(?:$|[-_.])',r'int([2-8])'):
        m=re.search(p,name,re.I)
        if m:return int(m.group(1))
    return 4

def preset(name):
    """모델 이름으로 (배치 문자 수, 배치 세그먼트 수, max_tokens) 추천값을 고른다.
    반드시 3-튜플을 반환한다 - 예전엔 어느 조건에도 안 걸리는 이름(예: llama-3.1-8b-instant)에서
    None이 반환돼 호출측의 `c, s, t = preset(...)`가 TypeError로 터졌다."""
    if not name:
        return (1000, 5, 4096)
    n = name.strip().lower()
    if n in CLOUD_PRESETS:
        return CLOUD_PRESETS[n]
    # 부분 일치는 '가장 긴 키'를 우선한다. 안 그러면 gemini-3.5-flash-lite가
    # gemini-3.5-flash 항목에 먼저 걸려 엉뚱한(훨씬 큰) 프리셋을 받는다.
    matches = [k for k in CLOUD_PRESETS if k in n or n in k]
    if matches:
        return CLOUD_PRESETS[max(matches, key=len)]
    # 목록에 없는 신규 모델용 대략치 - CLOUD_PRESETS의 실제 실측값과 같은 톤으로 잡는다.
    if "flash" in n and "lite" not in n:
        return (12000, 50, 32768)   # 미지의 Gemini 표준 Flash 계열로 가정
    if "lite" in n:
        return (4000, 25, 8192)     # 미지의 Lite 계열
    if any(k in n for k in ("mini", "haiku")):
        return (4000, 25, 12288)
    if any(k in n for k in ("pro", "sonnet", "gpt-4", "claude", "deepseek")):
        return (2800, 20, 8192)
    if any(k in n for k in ("reason", "o1", "o3")):
        return (6000, 25, 32768)
    if any(k in n for k in ("gguf", "flm", "-b", "instant", "qwen", "gemma", "llama")):
        return _local_preset(n)
    return (2800, 20, 8192)


def _local_preset(name):
    """로컬(양자화) 모델 이름이면 비트 수 기반 프리셋을 쓴다."""
    b = bits(name)
    if b in PRESETS:
        return PRESETS[b]
    lo = max(x for x in PRESETS if x < b)
    hi = min(x for x in PRESETS if x > b)
    t = (b - lo) / (hi - lo)
    return tuple(round(PRESETS[lo][i] + t * (PRESETS[hi][i] - PRESETS[lo][i])) for i in range(3))


def card(parent, title=None):
    """카드형 CTkFrame 하나를 만들어 parent에 붙이고 반환한다 (Material 'surface' 톤)."""
    try:
        parent_bg = parent.cget("fg_color")
        if parent_bg == "transparent" or not parent_bg:
            parent_bg = ("gray95", "gray14")
    except Exception:
        parent_bg = ("gray95", "gray14")

    outer = ctk.CTkFrame(parent, corner_radius=CARD_RADIUS, bg_color=parent_bg)
    outer.pack(fill="x", padx=0, pady=(0, 12))
    if title:
        ctk.CTkLabel(outer, text=title, font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=CARD_PAD, pady=(CARD_PAD, 4))
    body = ctk.CTkFrame(outer, fg_color="transparent")
    body.pack(fill="x", padx=CARD_PAD, pady=(0, CARD_PAD))
    return body


class OptionRow:
    """StringVar 기반 고정목록 드롭다운을 CTkOptionMenu로 감싸는 얇은 어댑터.
    (CTkOptionMenu는 ttk.Combobox(readonly)와 달리 textvariable을 직접 안 받으므로
    command 콜백으로 var를 동기화한다.)"""
    def __init__(self, master, var, values, width=160, command=None):
        self.var = var
        self._external_command = command
        val_list = list(values) if values else []
        cur = var.get()
        if cur and cur not in val_list:
            val_list.insert(0, cur)
        self.widget = ctk.CTkOptionMenu(master, values=val_list, width=width,
                                        command=self._on_select)
        if cur:
            self.widget.set(cur)
        elif val_list:
            self.widget.set(val_list[0]); var.set(val_list[0])

    def _on_select(self, value):
        self.var.set(value)
        if self._external_command:
            self._external_command(value)

    def set_values(self, values):
        val_list = list(values) if values else []
        cur = self.var.get()
        if cur and cur not in val_list:
            val_list.insert(0, cur)
        if not val_list:
            val_list = [""]
        self.widget.configure(values=val_list)
        if cur in val_list:
            self.widget.set(cur)
        elif val_list:
            self.widget.set(val_list[0]); self.var.set(val_list[0])

    def grid(self, **kw): self.widget.grid(**kw)
    def pack(self, **kw): self.widget.pack(**kw)
    def configure(self, **kw): self.widget.configure(**kw)


class ModelChainDialog(ctk.CTkToplevel):
    """
    한 API 키에 사용할 '모델 폴백 체인'을 고르는 창.

    왜 필요한가: Gemini는 RPM/TPM/RPD 한도를 모델마다 따로 센다. 그래서 키가 하나여도
    1순위 모델의 하루 한도(예: 20건)를 다 쓰면 2순위 모델의 20건, 그다음 Flash Lite의
    500건까지 이어서 쓸 수 있다. 다만 구글이 자동으로 바꿔주진 않으므로 우리 엔진이
    429를 감지해 다음 모델로 재요청한다. 이 창은 그 '순서'와 '사용 여부'를 정한다.

    - 기본값: 권장 순서대로 전부 체크 (품질 좋은 최신 Flash -> 구세대 -> 대용량 Lite)
    - 체크를 풀면 그 모델은 번역에 아예 쓰지 않는다
    - ▲▼로 순서를 바꾸면 그 순서가 곧 폴백 순서가 된다
    """

    def __init__(self, master, provider: str, selected: list[str], on_apply):
        super().__init__(master)
        self.provider = (provider or "").strip()
        self.on_apply = on_apply
        self.title(f"모델 선택 & 폴백 순서 — {self.provider or '직접 입력'}")
        self.geometry("720x620")
        self.transient(master)
        self.after(120, self.grab_set)   # 창이 뜬 뒤에 모달로 (WM 타이밍 이슈 회피)

        info = get_model_chain_info(self.provider)
        known = {m["id"]: m for m in info}
        # 저장된 체인이 우선(사용자가 정한 순서), 목록에만 있는 모델은 뒤에 미체크로 붙인다
        self.items: list[dict] = []
        for mid in selected:
            meta = known.get(mid, {"id": mid, "note": "직접 추가한 모델"})
            self.items.append({**meta, "on": tk.BooleanVar(value=True)})
        for m in info:
            if m["id"] not in selected:
                self.items.append({**m, "on": tk.BooleanVar(value=False)})

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(head, text="이 API 키로 사용할 모델", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(
            head, justify="left", text_color=("#555555", "#AAAAAA"),
            text=("Gemini는 사용량 한도(RPM·TPM·RPD)를 모델마다 따로 계산합니다.\n"
                  "위에서부터 순서대로 사용하고, 한도에 걸리면(429) 자동으로 다음 모델로 넘어갑니다.\n"
                  "→ 키가 하나여도 체크된 모델 수만큼 하루 번역량이 늘어납니다. 한도가 풀리면 다시 위쪽 모델로 복귀합니다."),
        ).pack(anchor="w", pady=(4, 0))

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=16, pady=(6, 4))
        ctk.CTkButton(tools, text="전체 선택", width=90, command=lambda: self._set_all(True)).pack(side="left")
        ctk.CTkButton(tools, text="전체 해제", width=90, command=lambda: self._set_all(False)).pack(side="left", padx=6)
        ctk.CTkButton(tools, text="권장값으로 되돌리기", width=150, command=self._reset).pack(side="left")
        self.custom_var = tk.StringVar()
        ctk.CTkEntry(tools, textvariable=self.custom_var, width=190,
                     placeholder_text="목록에 없는 모델 ID 직접 추가").pack(side="right", padx=(6, 0))
        ctk.CTkButton(tools, text="+ 추가", width=64, command=self._add_custom).pack(side="right")

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=("gray95", "gray14"))
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=6)

        self.summary = tk.StringVar()
        ctk.CTkLabel(self, textvariable=self.summary, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=16)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(6, 14))
        ctk.CTkButton(btns, text="확인", width=110, fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
                      command=self._apply).pack(side="right")
        ctk.CTkButton(btns, text="취소", width=90, fg_color=("gray70", "gray30"),
                      command=self.destroy).pack(side="right", padx=8)

        self._render()

    # -- 내부 동작 -------------------------------------------------------
    def _set_all(self, value: bool):
        for it in self.items:
            it["on"].set(value)
        self._render()

    def _reset(self):
        info = get_model_chain_info(self.provider)
        self.items = [{**m, "on": tk.BooleanVar(value=True)} for m in info]
        self._render()

    def _add_custom(self):
        mid = self.custom_var.get().strip()
        if not mid:
            return
        if any(it["id"] == mid for it in self.items):
            return messagebox.showinfo("안내", "이미 목록에 있는 모델입니다.", parent=self)
        self.items.append({"id": mid, "note": "직접 추가한 모델", "on": tk.BooleanVar(value=True)})
        self.custom_var.set("")
        self._render()

    def _move(self, idx: int, delta: int):
        j = idx + delta
        if 0 <= j < len(self.items):
            self.items[idx], self.items[j] = self.items[j], self.items[idx]
            self._render()

    def _render(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        rank = 0
        for i, it in enumerate(self.items):
            used = it["on"].get()
            if used:
                rank += 1
            rowf = ctk.CTkFrame(self.list_frame, corner_radius=8,
                                fg_color=("white", "gray20") if used else ("gray92", "gray16"))
            rowf.pack(fill="x", pady=3, padx=2)

            ctk.CTkCheckBox(rowf, text="", width=26, variable=it["on"],
                            command=self._render).pack(side="left", padx=(8, 2), pady=8)
            badge = f"{rank}순위" if used else "미사용"
            ctk.CTkLabel(rowf, text=badge, width=52,
                         text_color=(PRIMARY if used else ("#999999", "#777777")),
                         font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

            textf = ctk.CTkFrame(rowf, fg_color="transparent")
            textf.pack(side="left", fill="x", expand=True, padx=(4, 8))
            ctk.CTkLabel(textf, text=it["id"], anchor="w",
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            limits = []
            if it.get("rpm"):
                limits.append(f"분당 {it['rpm']}회")
            if it.get("rpd"):
                limits.append(f"하루 {it['rpd']}회")
            sub = " · ".join(limits + ([it["note"]] if it.get("note") else []))
            if sub:
                ctk.CTkLabel(textf, text=sub, anchor="w", text_color=("#666666", "#999999"),
                             font=ctk.CTkFont(size=11)).pack(anchor="w")

            ctk.CTkButton(rowf, text="▼", width=32, fg_color=("gray80", "gray30"),
                          hover_color=("gray70", "gray40"),
                          command=lambda i=i: self._move(i, 1)).pack(side="right", padx=(2, 8), pady=8)
            ctk.CTkButton(rowf, text="▲", width=32, fg_color=("gray80", "gray30"),
                          hover_color=("gray70", "gray40"),
                          command=lambda i=i: self._move(i, -1)).pack(side="right", pady=8)

        chosen = self._chosen()
        if chosen:
            est = self._estimate(chosen)
            self.summary.set(f"선택됨 {len(chosen)}개 · 1순위 {chosen[0]}{est}")
        else:
            self.summary.set("⚠ 모델이 하나도 선택되지 않았습니다 (이 키는 번역에 사용되지 않습니다)")

    def _chosen(self) -> list[str]:
        return [it["id"] for it in self.items if it["on"].get()]

    def _estimate(self, chosen: list[str]) -> str:
        """체크된 모델들의 RPD 합계 = 키 하나로 하루에 보낼 수 있는 대략적인 요청 수."""
        total = sum(next((it.get("rpd") or 0 for it in self.items if it["id"] == m), 0) for m in chosen)
        return f" · 하루 최대 약 {total}회 요청 (선택 모델 합계)" if total else ""

    def _apply(self):
        chosen = self._chosen()
        if not chosen:
            return messagebox.showwarning("모델 미선택",
                                          "최소 1개 이상의 모델을 선택해야 합니다.", parent=self)
        self.on_apply(chosen)
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"PDF Translater v{APP_VERSION}")
        self.geometry("1080x860")
        self.minsize(920,680)

        # 프로그램 창 아이콘 설정
        try:
            base_dir = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
            ico_path = base_dir / "icon.ico"
            png_path = base_dir / "icon.png"
            if os.name == "nt" and ico_path.exists():
                self.iconbitmap(str(ico_path))
            elif png_path.exists():
                img = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, img)
        except Exception:
            pass
        self.q=queue.Queue(); self.proc=None; self.keyfile=None; self.engine_completed=False
        self.engine=None; self.start_time=None; self.pct=0.0
        self.trans_pct=0.0   # 번역 단계 자체의 진행률(0~100). 전체 진행률과는 별개로 표시한다
        self.inp=tk.StringVar(); self.out=tk.StringVar(); self.pages=tk.StringVar()
        self.src=tk.StringVar(value="English"); self.dst=tk.StringVar(value="한국어")
        self.model_npu=tk.StringVar(value="gemma4-it-e2b-FLM")
        self.model_gpu=tk.StringVar(value="Gemma-3-4b-it-GGUF")
        # 기본 provider(gemini)의 권장 체인 전체(3.7~2.5 flash + 3.5/3.1 flash-lite)를
        # 기준으로 한 chain_preset() 결과와 동일한 값. add_api()/load_config() 뒤에
        # model_changed()를 호출해 실제 값으로 다시 계산하지만, 그 전에도 화면에 어색한
        # 값이 잠깐 보이지 않도록 초기값 자체를 미리 맞춰 둔다.
        self.cloud_chars = tk.StringVar(value="4000")
        self.cloud_segs = tk.StringVar(value="25")
        self.cloud_tokens = tk.StringVar(value="32768")
        self.local_chars = tk.StringVar(value="1000")
        self.local_segs = tk.StringVar(value="5")
        self.local_tokens = tk.StringVar(value="4096")
        self.chars = self.cloud_chars
        self.segs = self.cloud_segs
        self.tokens = self.cloud_tokens
        self.use_npu=tk.BooleanVar(value=True); self.api_rows=[]
        self.runtime=tk.StringVar(value="lemonade")
        self.use_gpu=tk.BooleanVar(value=False)
        self.compress=tk.BooleanVar(value=True)
        self.auto_open=tk.BooleanVar(value=True)
        # 여러 API 키/모델을 고르게 나눠 쓸지(기본) 아니면 1순위 모델만 쓸지.
        # 무료 티어 한도(RPM/RPD)는 모델별·키별로 따로 세므로, 고르게 쓰면 하루에
        # 처리할 수 있는 양이 (키 수 × 모델 수)배로 늘어난다.
        self.api_balance=tk.BooleanVar(value=True)
        self.last_output_path=None
        self.cache_stats_var = tk.StringVar(value="조회 중...")
        self.build()
        if not self.load_config():
            self.add_api("gemini"); self.add_api("anthropic"); self.add_api("openai")
        self.model_changed()  # 방금 만든/복원한 API 행들의 모델 체인 기준으로 고급 설정값을 바로 반영
        self.on_runtime_changed()
        self.refresh_models()
        self.refresh_cache_stats()
        self.after(100,self.poll)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # 화면 구성: 상단 바 + 탭(번역 / API·로컬AI / 설치 / 로그)
    # ------------------------------------------------------------------
    @staticmethod
    def _is_korean_locale() -> bool:
        try:
            import locale
            loc = (locale.getlocale()[0] or os.environ.get("LANG", "") or "").lower()
            return loc.startswith("ko") or "korean" in loc
        except Exception:
            return True

    def build(self):
        topbar = ctk.CTkFrame(self, fg_color="transparent")
        topbar.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(topbar, text=f"PDF Translater", font=ctk.CTkFont(size=19, weight="bold")).pack(side="left")
        ctk.CTkLabel(topbar, text=f"v{APP_VERSION}", text_color=("#666666","#999999")).pack(side="left", padx=(8,0))
        self.appearance_switch = ctk.CTkSwitch(topbar, text="다크 모드", command=self.toggle_appearance)
        self.appearance_switch.pack(side="right")
        if ctk.get_appearance_mode() == "Dark":
            self.appearance_switch.select()

        # 후원 (Sponsor / Support) 버튼 - Ko-fi 하이라이트 코랄 브랜드 색상 (#FF5E5B)
        sponsor_text = "☕ 후원" if self._is_korean_locale() else "☕ Support"
        self.sponsor_btn = ctk.CTkButton(
            topbar,
            text=sponsor_text,
            width=85,
            height=28,
            fg_color="#FF5E5B",
            hover_color="#D94845",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: webbrowser.open("https://ko-fi.com/thk7410")
        )
        self.sponsor_btn.pack(side="right", padx=(0, 16))

        self.tabs = ctk.CTkTabview(self, corner_radius=CARD_RADIUS)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=12)
        self.tabs.add("번역")
        self.tabs.add("API / 로컬 AI")
        self.tabs.add("설치 & 환경")
        self.tabs.add("로그")

        self.build_translate_tab(self.tabs.tab("번역"))
        self.build_ai_tab(self.tabs.tab("API / 로컬 AI"))
        self.build_setup_tab(self.tabs.tab("설치 & 환경"))
        self.build_log_tab(self.tabs.tab("로그"))

    def toggle_appearance(self):
        ctk.set_appearance_mode("Dark" if self.appearance_switch.get() else "Light")

    # -- 탭 1: 번역 --------------------------------------------------------
    def build_translate_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color=("gray95", "gray14"))
        scroll.pack(fill="both", expand=True)

        f = card(scroll, "파일")
        f.columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text="입력 PDF", width=140, anchor="w").grid(row=0, column=0, padx=(0,8), pady=6, sticky="w")
        ctk.CTkEntry(f, textvariable=self.inp).grid(row=0, column=1, pady=6, sticky="ew")
        ctk.CTkButton(f, text="찾기", width=70, command=lambda: self.pick(self.inp, False)).grid(row=0, column=2, padx=6)
        ctk.CTkButton(f, text="폴더 열기", width=90, command=self.open_input_folder).grid(row=0, column=3)
        ctk.CTkLabel(f, text="출력 PDF (비우면 자동)", width=140, anchor="w").grid(row=1, column=0, padx=(0,8), pady=6, sticky="w")
        ctk.CTkEntry(f, textvariable=self.out).grid(row=1, column=1, pady=6, sticky="ew")
        ctk.CTkButton(f, text="찾기", width=70, command=lambda: self.pick(self.out, True)).grid(row=1, column=2, padx=6)

        o = card(scroll, "언어 & 옵션")
        row1 = ctk.CTkFrame(o, fg_color="transparent"); row1.pack(fill="x", pady=(0,8))
        ctk.CTkLabel(row1, text="페이지 범위").pack(side="left")
        ctk.CTkEntry(row1, textvariable=self.pages, width=140, placeholder_text="예: 1-10").pack(side="left", padx=(8,20))
        ctk.CTkLabel(row1, text="원문 언어").pack(side="left")
        ctk.CTkComboBox(row1, variable=self.src, values=SOURCE_LANG_OPTIONS, width=160).pack(side="left", padx=(8,20))
        ctk.CTkLabel(row1, text="번역 언어").pack(side="left")
        ctk.CTkComboBox(row1, variable=self.dst, values=TARGET_LANG_OPTIONS, width=160).pack(side="left", padx=8)
        row2 = ctk.CTkFrame(o, fg_color="transparent"); row2.pack(fill="x")
        ctk.CTkSwitch(row2, text="번역 후 PDF 압축", variable=self.compress, onvalue=True, offvalue=False).pack(side="left", padx=(0,24))
        ctk.CTkSwitch(row2, text="완료 시 결과 PDF 자동 열기", variable=self.auto_open, onvalue=True, offvalue=False).pack(side="left")
        row3 = ctk.CTkFrame(o, fg_color="transparent"); row3.pack(fill="x", pady=(6,0))
        ctk.CTkSwitch(row3, text="API 키·모델 고르게 분산 (무료 한도 절약, 권장)",
                      variable=self.api_balance, onvalue=True, offvalue=False).pack(side="left")
        ctk.CTkLabel(row3, text="끄면 1순위 모델만 쓰고 막힐 때만 아래 모델로 내려갑니다",
                     text_color=("gray40", "gray60"), font=ctk.CTkFont(size=11)).pack(side="left", padx=10)

        # 번역 디스크 캐시 카드
        cache_c = card(scroll, "💾 번역 디스크 캐시 (SQLite)")
        c_row1 = ctk.CTkFrame(cache_c, fg_color="transparent")
        c_row1.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(c_row1, textvariable=self.cache_stats_var, font=ctk.CTkFont(size=12)).pack(side="left")
        c_btn_row = ctk.CTkFrame(cache_c, fg_color="transparent")
        c_btn_row.pack(fill="x")
        ctk.CTkButton(c_btn_row, text="🔄 통계 새로고침", width=120, command=self.refresh_cache_stats).pack(side="left")
        ctk.CTkButton(c_btn_row, text="🗑️ 캐시 전체 비우기", width=140, fg_color=DANGER, hover_color=DANGER_HOVER, command=self.clear_cache).pack(side="left", padx=8)

        r = card(scroll, "실행")
        self.status=tk.StringVar(value="대기 중")
        ctk.CTkLabel(r, textvariable=self.status, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        self.prog_info=tk.StringVar(value="")
        ctk.CTkLabel(r, textvariable=self.prog_info, text_color=("#666666","#999999")).pack(anchor="w", pady=(2,8))
        self.progress = ctk.CTkProgressBar(r); self.progress.pack(fill="x"); self.progress.set(0)
        buttons = ctk.CTkFrame(r, fg_color="transparent"); buttons.pack(fill="x", pady=(12,0))
        self.startbtn = ctk.CTkButton(buttons, text="번역 시작", fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
                                      height=38, command=self.start)
        self.startbtn.pack(side="left")
        self.stopbtn = ctk.CTkButton(buttons, text="중단 (진행분까지 저장)", fg_color=DANGER, hover_color=DANGER_HOVER,
                                     height=38, state="disabled", command=self.stop)
        self.stopbtn.pack(side="left", padx=8)
        self.openresultbtn = ctk.CTkButton(buttons, text="결과 PDF 열기", height=38, state="disabled",
                                           command=self.open_last_output)
        self.openresultbtn.pack(side="left")

    # -- 탭 2: API / 로컬 AI ----------------------------------------------
    def build_ai_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color=("gray95", "gray14"))
        scroll.pack(fill="both", expand=True)

        a = card(scroll, "API 키 — 체크된 API만 사용")
        ctk.CTkLabel(
            a, justify="left", text_color=("#555555", "#AAAAAA"),
            text=("사용량 한도는 모델마다 따로 계산됩니다. 오른쪽 🧩 버튼에서 모델을 여러 개 골라 두면\n"
                  "키가 하나여도 1순위 모델 → 한도 소진 시 다음 모델로 자동 전환하며 계속 번역합니다."),
        ).pack(anchor="w", pady=(0, 8))
        self.api_frame = ctk.CTkFrame(a, fg_color="transparent")
        self.api_frame.pack(fill="x")
        ctk.CTkButton(a, text="+ API 추가", width=110, command=lambda: self.add_api("gemini")).pack(anchor="w", pady=(8,0))

        n = card(scroll, "로컬 AI 설정 (NPU / GPU)")
        row0 = ctk.CTkFrame(n, fg_color="transparent"); row0.pack(fill="x", pady=(0,8))
        ctk.CTkLabel(row0, text="런타임").pack(side="left")
        self.runtime_opt = OptionRow(row0, self.runtime, list(LOCAL_RUNTIMES), width=130,
                                     command=lambda v: self.on_runtime_changed())
        self.runtime_opt.pack(side="left", padx=(8,20))
        self.npu_check = ctk.CTkSwitch(row0, text="NPU 사용", variable=self.use_npu, onvalue=True, offvalue=False,
                                       command=self.on_device_toggled)
        self.npu_check.pack(side="left", padx=(0,16))
        self.gpu_check = ctk.CTkSwitch(row0, text="GPU 사용", variable=self.use_gpu, onvalue=True, offvalue=False,
                                       command=self.on_device_toggled)
        self.gpu_check.pack(side="left")
        ctk.CTkButton(row0, text="모델 새로고침", width=110, command=self.refresh_models).pack(side="right")

        # NPU/GPU는 서로 다른 모델(recipe)이 필요하므로(FLM=NPU전용, GGUF=GPU용) 드롭다운을 분리한다.
        # 체크 안 된 장치의 드롭다운은 비활성화해서, 안 쓰는 장치의 모델을 실수로 잘못 고르지 않게 한다.
        row1 = ctk.CTkFrame(n, fg_color="transparent"); row1.pack(fill="x", pady=4)
        ctk.CTkLabel(row1, text="NPU 모델", width=90, anchor="w").pack(side="left")
        self.npu_models = OptionRow(row1, self.model_npu, [self.model_npu.get()], width=260,
                                    command=lambda v: self.model_changed())
        self.npu_models.pack(side="left", padx=8)
        row2 = ctk.CTkFrame(n, fg_color="transparent"); row2.pack(fill="x", pady=4)
        ctk.CTkLabel(row2, text="GPU 모델", width=90, anchor="w").pack(side="left")
        self.gpu_models = OptionRow(row2, self.model_gpu, [self.model_gpu.get()], width=260,
                                    command=lambda v: self.model_changed())
        self.gpu_models.pack(side="left", padx=8)

        adv = ctk.CTkFrame(scroll, fg_color="transparent"); adv.pack(fill="x", padx=16)
        self._adv_visible = tk.BooleanVar(value=False)
        self.adv_toggle_btn = ctk.CTkButton(adv, text="▸ 고급 설정 (클라우드 & 로컬 AI 배치 크기 / max_tokens 분리 설정)", fg_color="transparent",
                                            text_color=PRIMARY, hover=False, anchor="w",
                                            command=self.toggle_advanced)
        self.adv_toggle_btn.pack(anchor="w", pady=(8,0))
        self.adv_frame = ctk.CTkFrame(scroll, fg_color="transparent")

        # 클라우드 AI 전용 배치 설정 카드
        c_adv = card(self.adv_frame, "☁️ 클라우드 AI 배치 옵션 (모델 선택 시 자동 추천 & 자유 변경)")
        c_adv_row = ctk.CTkFrame(c_adv, fg_color="transparent")
        c_adv_row.pack(fill="x", pady=4)
        for i, (label, var) in enumerate((("배치 문자 수", self.cloud_chars), ("세그먼트 수", self.cloud_segs), ("max_tokens", self.cloud_tokens))):
            ctk.CTkLabel(c_adv_row, text=label).grid(row=0, column=i*2, padx=(0 if i==0 else 16, 6), pady=6)
            ctk.CTkEntry(c_adv_row, textvariable=var, width=110).grid(row=0, column=i*2+1)

        # 로컬 AI 전용 배치 설정 카드
        l_adv = card(self.adv_frame, "🖥️ 로컬 AI (NPU/GPU) 배치 옵션 (모델 선택 시 자동 추천 & 자유 변경)")
        l_adv_row = ctk.CTkFrame(l_adv, fg_color="transparent")
        l_adv_row.pack(fill="x", pady=4)
        for i, (label, var) in enumerate((("배치 문자 수", self.local_chars), ("세그먼트 수", self.local_segs), ("max_tokens", self.local_tokens))):
            ctk.CTkLabel(l_adv_row, text=label).grid(row=0, column=i*2, padx=(0 if i==0 else 16, 6), pady=6)
            ctk.CTkEntry(l_adv_row, textvariable=var, width=110).grid(row=0, column=i*2+1)

    def toggle_advanced(self):
        show = not self._adv_visible.get()
        self._adv_visible.set(show)
        if show:
            self.adv_frame.pack(fill="x", padx=16, pady=(6,0))
            self.adv_toggle_btn.configure(text="▾ 고급 설정 (클라우드 & 로컬 AI 배치 크기 / max_tokens 분리 설정)")
        else:
            self.adv_frame.pack_forget()
            self.adv_toggle_btn.configure(text="▸ 고급 설정 (클라우드 & 로컬 AI 배치 크기 / max_tokens 분리 설정)")

    # -- 탭 3: 설치 & 환경 --------------------------------------------------
    # -- 탭 3: 설치 & 환경 --------------------------------------------------
    def build_setup_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color=("gray95", "gray14"))
        scroll.pack(fill="both", expand=True)

        # ------------------------------------------------------------------
        # 카드 1: 📊 시스템 파이썬 & 필수 환경 진단
        # ------------------------------------------------------------------
        c1 = card(scroll, "📊 파이썬 & 필수 라이브러리 상태 대시보드")

        self.status_py_var = tk.StringVar(value="진단 중...")
        self.status_pkg_var = tk.StringVar(value="진단 중...")

        row_py = ctk.CTkFrame(c1, fg_color="transparent")
        row_py.pack(fill="x", pady=2)
        ctk.CTkLabel(row_py, text="• Python 환경:", width=150, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(row_py, textvariable=self.status_py_var, anchor="w").pack(side="left", fill="x", expand=True)

        row_pkg = ctk.CTkFrame(c1, fg_color="transparent")
        row_pkg.pack(fill="x", pady=2)
        ctk.CTkLabel(row_pkg, text="• 필수 패키지(pip):", width=150, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(row_pkg, textvariable=self.status_pkg_var, anchor="w").pack(side="left", fill="x", expand=True)

        btn_row1 = ctk.CTkFrame(c1, fg_color="transparent")
        btn_row1.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(btn_row1, text="🔄 진단 새로고침", width=120, command=self.refresh_system_status).pack(side="left")
        ctk.CTkButton(btn_row1, text="📦 패키지(pip) 설치/업데이트", command=self.install_packages).pack(side="left", padx=8)
        ctk.CTkButton(btn_row1, text="⚡ 필수 요소 전체 자동 설치", fg_color=PRIMARY, hover_color=PRIMARY_HOVER,
                      command=self.install_prerequisites).pack(side="left")

        # ------------------------------------------------------------------
        # 카드 2: 🤖 로컬 AI 런타임 현황 & 바로가기
        # ------------------------------------------------------------------
        c2 = card(scroll, "🤖 로컬 AI 런타임 연결 현황 & 다운로드 관리")

        self.status_lemonade_var = tk.StringVar(value="진단 중...")
        self.status_ollama_var = tk.StringVar(value="진단 중...")
        self.status_lmstudio_var = tk.StringVar(value="진단 중...")
        self.status_other_runtimes_var = tk.StringVar(value="진단 중...")

        # Lemonade Row
        r_lem = ctk.CTkFrame(c2, fg_color="transparent")
        r_lem.pack(fill="x", pady=4)
        ctk.CTkLabel(r_lem, text="• Lemonade Server (NPU/GPU):", width=220, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(r_lem, textvariable=self.status_lemonade_var, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r_lem, text="🍋 Lemonade 자동 설치", width=140, command=self.install_lemonade).pack(side="right", padx=(6, 0))
        ctk.CTkButton(r_lem, text="🌐 GitHub 릴리스", width=110, command=lambda: webbrowser.open("https://github.com/lemonade-sdk/lemonade/releases/latest")).pack(side="right")

        # Ollama Row
        r_oll = ctk.CTkFrame(c2, fg_color="transparent")
        r_oll.pack(fill="x", pady=4)
        ctk.CTkLabel(r_oll, text="• Ollama (GPU/CPU):", width=220, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(r_oll, textvariable=self.status_ollama_var, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r_oll, text="🦙 Ollama 공식 사이트", width=140, command=lambda: webbrowser.open("https://ollama.com")).pack(side="right")

        # LM Studio Row
        r_lms = ctk.CTkFrame(c2, fg_color="transparent")
        r_lms.pack(fill="x", pady=4)
        ctk.CTkLabel(r_lms, text="• LM Studio (GPU/CPU):", width=220, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(r_lms, textvariable=self.status_lmstudio_var, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r_lms, text="🧪 LM Studio 웹사이트", width=140, command=lambda: webbrowser.open("https://lmstudio.ai")).pack(side="right")

        # Jan.ai / KoboldCPP Row
        r_oth = ctk.CTkFrame(c2, fg_color="transparent")
        r_oth.pack(fill="x", pady=4)
        ctk.CTkLabel(r_oth, text="• Jan.ai / KoboldCPP 등:", width=220, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(r_oth, textvariable=self.status_other_runtimes_var, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r_oth, text="🤖 Jan.ai 웹사이트", width=140, command=lambda: webbrowser.open("https://jan.ai")).pack(side="right")

        # ------------------------------------------------------------------
        # 카드 3: 🖼️ 선택 기능 (일본어 만화 전용 OCR)
        # ------------------------------------------------------------------
        c3 = card(scroll, "🖼️ 선택 기능 — manga-ocr (일본어 만화 OCR)")

        self.status_manga_var = tk.StringVar(value="진단 중...")

        r_manga = ctk.CTkFrame(c3, fg_color="transparent")
        r_manga.pack(fill="x", pady=4)
        ctk.CTkLabel(r_manga, text="• manga-ocr 설치 상태:", width=180, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(r_manga, textvariable=self.status_manga_var, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r_manga, text="📥 manga-ocr (1GB) 설치", command=self.install_manga_ocr).pack(side="right")

        ctk.CTkLabel(c3, text="※ 일본어 만화 전용 OCR engine - 설치 시 텍스트 인식률 대폭 향상. 미설치 시 기본 Tesseract 사용.",
                     text_color=("#666666","#999999"), justify="left").pack(anchor="w", pady=(6,0))

        # Initial status refresh
        self.after(200, self.refresh_system_status)

    def refresh_system_status(self):
        """시스템 환경 및 로컬 AI 런타임 연결 상태를 백그라운드에서 실시간 진단."""
        def work():
            py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            py_str = f"✅ 사용 중 ({sys.executable} - Python {py_ver})"

            pkgs = ["pymupdf", "customtkinter", "anthropic", "google.genai", "openai", "numpy", "cv2", "PIL"]
            missing = []
            for pkg in pkgs:
                try:
                    importlib.import_module(pkg)
                except Exception:
                    missing.append(pkg)

            if not missing:
                pkg_str = "✅ 모든 필수 패키지 정상 설치됨 (PyMuPDF, customtkinter, numpy 등)"
            else:
                pkg_str = f"⚠️ 누락된 패키지 있음 ({', '.join(missing)}) - [패키지 설치] 권장"

            def check_url(port, path):
                try:
                    with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=1.5) as r:
                        if r.status == 200:
                            return True
                except Exception:
                    pass
                return False

            lem_active = check_url(13305, "/api/v1/models")
            lem_installed = self._lemonade_ok()
            if lem_active:
                lem_str = "✅ 실행 중 / 연동 가능 (http://localhost:13305)"
            elif lem_installed:
                lem_str = "⚠️ 설치됨 (현재 서버 미실행 상태)"
            else:
                lem_str = "❌ 미설치"

            oll_ok = check_url(11434, "/v1/models")
            oll_str = "✅ 실행 중 / 연동 가능 (http://localhost:11434)" if oll_ok else "⚠️ 미실행 또는 미설치"

            lms_ok = check_url(1234, "/v1/models")
            lms_str = "✅ 실행 중 / 연동 가능 (http://localhost:1234)" if lms_ok else "⚠️ 미실행 또는 미설치"

            jan_ok = check_url(1337, "/v1/models")
            kob_ok = check_url(5001, "/v1/models")
            if jan_ok and kob_ok:
                oth_str = "✅ Jan.ai 및 KoboldCPP 모두 실행 중"
            elif jan_ok:
                oth_str = "✅ Jan.ai 실행 중 (http://localhost:1337)"
            elif kob_ok:
                oth_str = "✅ KoboldCPP 실행 중 (http://localhost:5001)"
            else:
                oth_str = "⚠️ 미실행 또는 미설치"

            try:
                importlib.import_module("manga_ocr")
                manga_str = "✅ 설치 완료 (일본어 만화 OCR 활성화)"
            except Exception:
                manga_str = "💡 미설치 (기본 Tesseract OCR 사용 중)"

            self.after(0, lambda: self._apply_status_vars(py_str, pkg_str, lem_str, oll_str, lms_str, oth_str, manga_str))

        threading.Thread(target=work, daemon=True).start()

    def _apply_status_vars(self, py_str, pkg_str, lem_str, oll_str, lms_str, oth_str, manga_str):
        if hasattr(self, 'status_py_var'):
            self.status_py_var.set(py_str)
            self.status_pkg_var.set(pkg_str)
            self.status_lemonade_var.set(lem_str)
            self.status_ollama_var.set(oll_str)
            self.status_lmstudio_var.set(lms_str)
            self.status_other_runtimes_var.set(oth_str)
            self.status_manga_var.set(manga_str)

    # -- 탭 4: 로그 ---------------------------------------------------------
    def build_log_tab(self, tab):
        wrap = ctk.CTkFrame(tab, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        top = ctk.CTkFrame(wrap, fg_color="transparent"); top.pack(fill="x", pady=(0,8))
        ctk.CTkButton(top, text="로그 지우기", width=100,
                     command=lambda: self.log.delete("1.0", "end")).pack(side="right")
        self.log = ctk.CTkTextbox(wrap, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self.log.pack(fill="both", expand=True)

    def add_api(self, provider="gemini", initial_model=None):
        """
        API 키 행 하나를 만든다. 모델은 이제 '하나'가 아니라 '폴백 체인'(콤마로 이어진
        여러 모델)이며, mv에는 "modelA,modelB,..." 형태로 담긴다. 기본값은 그 provider의
        권장 모델 '전부'다 - Gemini는 한도가 모델별로 독립이라 전부 켜 두는 편이 하루
        처리량이 가장 크고, 사용자는 [모델] 버튼에서 원하지 않는 모델만 체크 해제하면 된다.
        """
        row = ctk.CTkFrame(self.api_frame, fg_color="transparent")
        row.pack(fill="x", pady=3)
        on = tk.BooleanVar(value=False)
        pv = tk.StringVar(value=provider)
        chain = parse_chain(initial_model) if initial_model else default_chain_for(provider)
        mv = tk.StringVar(value=",".join(chain))
        key = tk.StringVar()

        ctk.CTkCheckBox(row, text="", variable=on, width=24, command=self.model_changed).pack(side="left")

        presets = ["gemini", "anthropic", "openai", "deepseek", "openrouter", "groq", "ollama", "직접 입력"]
        if provider and provider not in presets:
            presets.insert(0, provider)

        provider_combo = ctk.CTkComboBox(
            row,
            variable=pv,
            values=presets,
            width=110,
            command=lambda choice: self._on_provider_select(choice, pv, provider_combo, mv, model_btn)
        )
        provider_combo.pack(side="left", padx=(0, 4))

        ctk.CTkEntry(row, textvariable=key, show="●", placeholder_text="API Key 입력").pack(side="left", fill="x", expand=True, padx=(0, 4))

        model_btn = ctk.CTkButton(row, text="", width=250, anchor="w",
                                  fg_color=("gray85", "gray25"), hover_color=("gray75", "gray35"),
                                  text_color=("gray10", "gray90"),
                                  command=lambda: self._open_model_dialog(pv, mv, model_btn))
        model_btn.pack(side="left", padx=(0, 4))
        self._refresh_model_button(pv, mv, model_btn)

        item = [row, on, pv, key, mv, model_btn]
        ctk.CTkButton(row, text="삭제", width=55, fg_color=DANGER, hover_color=DANGER_HOVER,
                      command=lambda: self.remove_api(item)).pack(side="left")
        self.api_rows.append(item)

    def _refresh_model_button(self, pv_var, mv_var, model_btn):
        models = parse_chain(mv_var.get())
        total = len(get_model_chain_info(pv_var.get()))
        model_btn.configure(text="🧩 " + format_chain_label(models, max(total, len(models))))

    def _open_model_dialog(self, pv_var, mv_var, model_btn):
        def apply(new_models):
            mv_var.set(",".join(new_models))
            self._refresh_model_button(pv_var, mv_var, model_btn)
            self.model_changed()
        ModelChainDialog(self, pv_var.get(), parse_chain(mv_var.get()), apply)

    def _on_provider_select(self, choice, pv_var, provider_combo, mv_var, model_btn):
        if choice == "직접 입력":
            pv_var.set("")
            provider_combo.set("")
            provider_combo.focus_set()
            mv_var.set("")
        else:
            mv_var.set(",".join(default_chain_for(choice)))
        self._refresh_model_button(pv_var, mv_var, model_btn)
        self.model_changed()

    def remove_api(self, item):
        item[0].destroy()
        if item in self.api_rows:
            self.api_rows.remove(item)
        self.model_changed()

    # ------------------------------------------------------------------
    # 필수사항 설치: Python 3.12 -> Lemonade Server -> pip requirements 순차 진행
    # ------------------------------------------------------------------
    def _log(self,msg): self.q.put(("LOG",msg if msg.endswith("\n") else msg+"\n"))

    def _python_ok(self):
        """실행에 쓸 수 있는 실제(비-스토어) Python이 하나라도 있는지 - 버전은 따지지 않는다."""
        return any("WindowsApps" not in p for p in _real_python_candidates())

    def _lemonade_ok(self):
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/api/v1/models",timeout=2):return True
        except Exception:pass
        bin_dir=Path(os.environ.get("LOCALAPPDATA",""))/"lemonade_server"/"bin"
        return (bin_dir/"LemonadeServer.exe").is_file() or bool(_shutil.which("LemonadeServer") or _shutil.which("lemonade-server"))

    def _run_stream(self,cmd):
        """명령을 실행하고 출력을 로그 큐로 스트리밍. 종료코드 반환."""
        flags=0x08000000 if os.name=="nt" else 0
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                           encoding="utf-8",errors="replace",creationflags=flags)
        for line in p.stdout:self.q.put(("LOG",line))
        return p.wait()

    # Windows용 바이너리(exe 설치 프로그램)가 제공되는 마지막 3.12.x 버전.
    # 3.12.11부터는 "source-only" 보안 릴리스라 exe 설치 프로그램 자체가 없다 - 이후
    # 버전으로 URL을 만들면 다운로드가 404로 실패한다.
    PYTHON312_INSTALLER_VERSION = "3.12.10"
    PYTHON312_INSTALLER_URL = (
        f"https://www.python.org/ftp/python/{PYTHON312_INSTALLER_VERSION}/"
        f"python-{PYTHON312_INSTALLER_VERSION}-amd64.exe"
    )

    def _install_python_worker(self) -> bool:
        """
        Python 설치. 반환값: 성공(이미 설치돼 있던 경우 포함) 여부.
        버전은 따지지 않는다 - PC에 이미 어떤 버전이든 실제(비-스토어) Python이 설치돼 있으면
        그대로 사용하고, 하나도 없을 때만 새로 설치한다(설치 프로그램이 있는 3.12.10을 기준으로
        받지만, 이후 패키지 설치는 이미 있는 다른 버전에도 그대로 동작한다).

        중요한 두 가지 문제를 피해야 한다:
        1) winget으로 설치할 때 소스를 명시 안 하면 'winget'(공식 python.org 빌드)과
           'msstore'(마이크로소프트 스토어의 껍데기 앱, PATH/환경변수 문제가 많아 부적합)
           소스가 같은 ID로 겹쳐서 스토어 버전이 설치될 위험이 있다 -> --source winget 명시.
        2) winget 자체가 없는 PC(구버전 Windows, App Installer 미설치 등)에서는 지금까지
           자동 설치가 전혀 안 되고 브라우저만 열어줬다 -> winget이 없거나 winget 설치가
           실패하면, python.org 공식 설치 프로그램을 직접 다운로드해 무인 설치하는 것으로
           확실히 폴백한다(스토어를 절대 거치지 않음).
        """
        if self._python_ok():
            self._log("[Python] 사용 가능한 Python이 이미 있음 - 건너뜀")
            return True

        if _shutil.which("winget"):
            self._log("[Python] Python 미설치 -> winget으로 설치 시도 (공식 winget 소스 지정)")
            code=self._run_stream(["winget","install","-e","--id","Python.Python.3.12",
                                   "--source","winget",
                                   "--accept-source-agreements","--accept-package-agreements",
                                   "--silent"])
            if code==0 and self._python_ok():
                self._log("[Python] Python 설치 완료 (winget)")
                return True
            self._log(f"[Python][경고] winget 설치가 완료되지 않음 (코드 {code}). "
                      "공식 인스톨러를 직접 다운로드해 설치를 시도합니다...")
        else:
            self._log("[Python] winget이 없음 -> python.org 공식 인스톨러를 직접 다운로드해 설치합니다.")

        # winget이 없거나 winget 설치가 실패한 경우: python.org 공식 exe를 직접 받아 무인 설치.
        # 마이크로소프트 스토어를 아예 거치지 않으므로, 스토어판의 PATH/환경변수 문제를
        # 원천적으로 피할 수 있다.
        try:
            dst=Path(tempfile.gettempdir())/f"python-{self.PYTHON312_INSTALLER_VERSION}-amd64.exe"
            self._log(f"[Python] 공식 인스톨러 다운로드 중: {self.PYTHON312_INSTALLER_URL}")
            urllib.request.urlretrieve(self.PYTHON312_INSTALLER_URL, dst)
            self._log("[Python] 인스톨러 실행 중 (무인 설치, PATH 자동 등록)...")
            # InstallAllUsers=0: 관리자 권한 없이도 설치 가능(사용자 단위).
            # PrependPath=1: 이번 설치를 PATH 맨 앞에 등록 -> 'python' 명령이 바로 이걸 가리킴.
            # Include_launcher=1: py 런처(py.exe)도 함께 설치 (여러 버전 중 골라 쓰기 위해 필요).
            code=self._run_stream([str(dst), "/quiet", "InstallAllUsers=0", "PrependPath=1",
                                   "Include_launcher=1", "Include_test=0"])
            try:
                dst.unlink()
            except Exception:
                pass
            if code==0 and self._python_ok():
                self._log("[Python] Python 설치 완료 (공식 인스톨러)")
                return True
            self._log(f"[Python][경고] 공식 인스톨러 무인 설치가 완료되지 않음 (코드 {code}).")
        except Exception as e:
            self._log(f"[Python][경고] 공식 인스톨러 다운로드/실행 실패: {e}")

        self._log("[Python][경고] 자동 설치에 실패했습니다. python.org 다운로드 페이지를 엽니다 - "
                  "수동 설치 시 'Add python.exe to PATH' 체크를 꼭 하세요. "
                  "주의: Windows 검색창에서 'python'을 쳤을 때 뜨는 '마이크로소프트 스토어에서 "
                  "다운로드'는 선택하지 마세요 - 그 버전은 PATH/환경변수 문제가 많아 이 "
                  "프로그램과 호환되지 않습니다. 이미 스토어판을 설치했다면, 설정 > 앱 > "
                  "고급 앱 설정 > 앱 실행 별칭에서 'python.exe'/'python3.exe' 별칭을 꺼서 "
                  "비활성화한 뒤 위 공식 인스톨러로 다시 설치하세요.")
        webbrowser.open("https://www.python.org/downloads/release/python-31210/")
        return False

    def install_python(self):
        """'Python 설치' 버튼 - 이것만 단독 실행."""
        self.status.set("Python 확인/설치 중...")
        def work():
            try:
                ok=self._install_python_worker()
                self.after(0,lambda:self.status.set(
                    "Python 준비 완료" if ok else "Python 수동 설치 필요"))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.after(0,lambda:self.status.set("Python 설치 중 오류"))
        threading.Thread(target=work,daemon=True).start()

    def _install_lemonade_worker(self) -> bool:
        """Lemonade Server 설치. 반환값: 성공(이미 설치돼 있던 경우 포함) 여부."""
        if self._lemonade_ok():
            self._log("[Lemonade] Lemonade Server: 이미 설치됨 - 건너뜀")
            return True
        self._log("[Lemonade] Lemonade Server 미설치 -> GitHub 최신 릴리스 조회 중...")
        try:
            with urllib.request.urlopen(
                "https://api.github.com/repos/lemonade-sdk/lemonade/releases/latest",
                timeout=15) as r:
                rel=json.load(r)
            assets=rel.get("assets",[])
            cand=[a for a in assets if a.get("name","").lower().endswith(".exe")]
            cand.sort(key=lambda a:sum(k in a.get("name","").lower()
                                       for k in ("win","setup","installer","server")),reverse=True)
            if not cand:
                raise RuntimeError("릴리스에서 .exe 인스톨러를 찾지 못함")
            url=cand[0]["browser_download_url"]; name=cand[0]["name"]
            dst=Path(tempfile.gettempdir())/name
            self._log(f"[Lemonade] 다운로드: {name} ({cand[0].get('size',0)//1048576}MB)...")
            urllib.request.urlretrieve(url,dst)
            self._log("[Lemonade] 인스톨러 실행 - 설치 창의 안내를 따라 설치를 완료하세요.")
            subprocess.Popen([str(dst)])
            self._log("[Lemonade] 설치가 끝나면 이 버튼을 다시 눌러 확인하세요.")
            return False  # 설치 프로그램은 백그라운드로 뜨므로, 이 시점엔 아직 완료 확인 불가
        except Exception as e:
            self._log(f"[Lemonade][경고] 자동 다운로드 실패({e}). 릴리스 페이지를 엽니다.")
            webbrowser.open("https://github.com/lemonade-sdk/lemonade/releases/latest")
            return False

    def install_lemonade(self):
        """'Lemonade 설치' 버튼 - 이것만 단독 실행."""
        self.status.set("Lemonade Server 확인/설치 중...")
        def work():
            try:
                ok=self._install_lemonade_worker()
                self.after(0,lambda:self.status.set(
                    "Lemonade 준비 완료" if ok else "Lemonade 설치 진행 중/확인 필요 - 로그 참고"))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.after(0,lambda:self.status.set("Lemonade 설치 중 오류"))
        threading.Thread(target=work,daemon=True).start()

    def _install_packages_worker(self) -> bool:
        """pip requirements.txt 설치. 반환값: 성공 여부."""
        req=APP_DIR/"requirements.txt"
        if not req.exists():
            self._log(f"[패키지][오류] requirements.txt를 찾을 수 없습니다: {req}")
            return False
        pyexe=_pick_working_python()
        if not pyexe:
            self._log("[패키지][오류] 실제 Python 실행 파일을 찾지 못했습니다. "
                      "'Python 설치'를 먼저 실행하세요.")
            return False
        self._log(f"[패키지] pip 요구사항 설치 ({pyexe})...")
        code=self._run_stream([pyexe,"-m","pip","install","--upgrade","-r",str(req)])
        self._log("[패키지] pip 요구사항 "+("설치 완료" if code==0 else f"설치 실패 (코드 {code})"))
        return code==0

    def _install_manga_ocr_worker(self) -> bool:
        """manga-ocr(+PyTorch) 설치. 선택 사항이라 별도 버튼으로 분리돼 있다 - 반환값: 성공 여부."""
        pyexe=_pick_working_python()
        if not pyexe:
            self._log("[manga-ocr][오류] 실제 Python 실행 파일을 찾지 못했습니다. "
                      "'Python 설치'를 먼저 실행하세요.")
            return False
        self._log(f"[manga-ocr] 설치 시작 ({pyexe}) - PyTorch 포함, 용량이 크고(~1GB) "
                  "시간이 오래 걸릴 수 있습니다...")
        code=self._run_stream([pyexe,"-m","pip","install","--upgrade","manga-ocr"])
        self._log("[manga-ocr] 설치 "+("완료" if code==0 else f"실패 (코드 {code})"))
        return code==0

    def install_manga_ocr(self):
        """'manga-ocr 설치(선택)' 버튼 - 이것만 단독 실행.
        일본어 만화 전용 OCR(Tesseract보다 정확도가 높음)이지만 PyTorch 의존성 때문에
        용량이 크고(~1GB) 다른 언어는 지원하지 않는다(하이브리드: 일본어만 이걸 쓰고
        나머지 언어는 그대로 Tesseract). 그래서 기본 설치에 포함하지 않고 선택 사항으로
        분리했다 - 미설치 상태에서도 프로그램은 정상 동작한다(자동으로 Tesseract만 사용)."""
        self.status.set("manga-ocr 설치 중(용량이 커 시간이 걸릴 수 있음)...")
        def work():
            try:
                ok=self._install_manga_ocr_worker()
                self.after(0,lambda:self.status.set(
                    "manga-ocr 설치 완료" if ok else "manga-ocr 설치 실패 - 로그 확인"))
                if ok:
                    self.after(0,lambda:messagebox.showinfo(
                        "설치 결과","manga-ocr 설치가 완료되었습니다. 다음 번역부터 "
                        "일본어 OCR에 자동으로 사용됩니다(다른 언어는 계속 Tesseract 사용)."))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.after(0,lambda:self.status.set("manga-ocr 설치 중 오류"))
        threading.Thread(target=work,daemon=True).start()

    def install_packages(self):
        """'패키지(pip) 설치' 버튼 - 이것만 단독 실행."""
        self.status.set("필수 패키지(pip) 설치 중...")
        def work():
            try:
                ok=self._install_packages_worker()
                self.after(0,lambda:self.status.set(
                    "패키지 설치 완료" if ok else "패키지 설치 실패 - 로그 확인"))
                if ok:
                    self.after(0,lambda:messagebox.showinfo(
                        "설치 결과","패키지 설치가 완료되었습니다. GUI를 다시 실행하세요."))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.after(0,lambda:self.status.set("패키지 설치 중 오류"))
        threading.Thread(target=work,daemon=True).start()

    def install_prerequisites(self):
        """'전체 자동 설치' 버튼 - Python -> Lemonade -> 패키지 순서로 전부 실행하는 통합 래퍼.
        개별 설치 함수(_install_*_worker)를 그대로 재사용하므로 로직 중복이 없다."""
        self.status.set("전체 자동 설치 중... (Python -> Lemonade -> 패키지)")
        def work():
            try:
                if not self._install_python_worker():
                    self.after(0,lambda:self.status.set("Python 수동 설치 필요 - 완료 후 다시 눌러주세요"))
                    return
                self._install_lemonade_worker()
                self._install_packages_worker()
                self.after(0,lambda:self.status.set("전체 자동 설치 완료 - 로그 확인"))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.after(0,lambda:self.status.set("전체 자동 설치 중 오류"))
        threading.Thread(target=work,daemon=True).start()

    # ------------------------------------------------------------------
    # 설정(API 키 등) 저장/복원 - 앱 재시작해도 이어서 사용 가능하게
    # 주의: 키는 base64로 살짝 가려둘 뿐 암호화가 아니다(로컬 개인 PC 사용 전제).
    # ------------------------------------------------------------------
    def save_config(self):
        try:
            data={
                # chain_version 2부터 model은 "modelA,modelB,..." 형태의 폴백 체인이다.
                # (1에서 올라올 때 단일 모델 행을 권장 체인 전체로 넓혀 준다 - load_config 참고)
                "chain_version": 2,
                "api_rows":[{"provider":item[2].get(),"on":item[1].get(),
                            "key":base64.b64encode(item[3].get().encode("utf-8")).decode("ascii"),
                            "model":item[4].get() if len(item)>4 else "",
                            "models":parse_chain(item[4].get()) if len(item)>4 else []}
                           for item in self.api_rows],
                "src":self.src.get(),"dst":self.dst.get(),
                "model_npu":self.model_npu.get(),"model_gpu":self.model_gpu.get(),
                "use_npu":self.use_npu.get(),
                "runtime":self.runtime.get(),"use_gpu":self.use_gpu.get(),
                "compress":self.compress.get(),"auto_open":self.auto_open.get(),
                "api_balance":self.api_balance.get(),
                "cloud_chars":self.cloud_chars.get(),"cloud_segs":self.cloud_segs.get(),"cloud_tokens":self.cloud_tokens.get(),
                "local_chars":self.local_chars.get(),"local_segs":self.local_segs.get(),"local_tokens":self.local_tokens.get(),
            }
            CONFIG_DIR.mkdir(parents=True,exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception as e:
            print(f"[설정 저장 실패] {e}",file=sys.stderr)

    def load_config(self) -> bool:
        """저장된 설정이 있으면 복원. 복원했으면 True (기본 API 행 3개를 추가하지 않도록)."""
        if not CONFIG_PATH.exists():
            return False
        try:
            data=json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[설정 로드 실패] {e}",file=sys.stderr)
            return False
        rows=data.get("api_rows") or []
        chain_version = int(data.get("chain_version", 1) or 1)
        for r in rows:
            p = r.get("provider","gemini")
            chain = list(r.get("models") or []) or parse_chain(r.get("model"))
            # 구버전(모델 1개만 저장) 설정 자동 이관: 저장된 모델이 권장 체인에 들어있는
            # 모델이면 그 provider의 권장 모델 전체로 넓힌다. 한도가 모델별로 독립이라
            # 전부 켜 두는 쪽이 항상 이득이고, 원하지 않는 모델은 [모델] 버튼에서 끄면 된다.
            # (권장 목록에 없는 모델을 직접 지정해 둔 경우는 사용자의 의도이므로 그대로 둔다.)
            if chain_version < 2 and len(chain) == 1:
                recommended = default_chain_for(p)
                if chain[0] in recommended and len(recommended) > 1:
                    chain = recommended
            self.add_api(p, initial_model=",".join(chain))
            item=self.api_rows[-1]
            item[1].set(bool(r.get("on",False)))
            try:
                item[3].set(base64.b64decode(r.get("key","").encode("ascii")).decode("utf-8"))
            except Exception:
                pass
        if data.get("src"):self.src.set(data["src"])
        if data.get("dst"):self.dst.set(data["dst"])
        if data.get("model_npu"):self.model_npu.set(data["model_npu"])
        if data.get("model_gpu"):self.model_gpu.set(data["model_gpu"])
        if "use_npu" in data:self.use_npu.set(data["use_npu"])
        if data.get("runtime") in LOCAL_RUNTIMES:self.runtime.set(data["runtime"])
        if "use_gpu" in data:self.use_gpu.set(data["use_gpu"])
        if "compress" in data:self.compress.set(data["compress"])
        if "api_balance" in data:self.api_balance.set(data["api_balance"])
        if "auto_open" in data:self.auto_open.set(data["auto_open"])
        if data.get("cloud_chars"):self.cloud_chars.set(data["cloud_chars"])
        if data.get("cloud_segs"):self.cloud_segs.set(data["cloud_segs"])
        if data.get("cloud_tokens"):self.cloud_tokens.set(data["cloud_tokens"])
        if data.get("local_chars"):self.local_chars.set(data["local_chars"])
        if data.get("local_segs"):self.local_segs.set(data["local_segs"])
        if data.get("local_tokens"):self.local_tokens.set(data["local_tokens"])
        return bool(rows)

    def on_close(self):
        self.save_config()
        self.destroy()

    def pick(self,var,save):
        p=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF","*.pdf")]) if save else filedialog.askopenfilename(filetypes=[("PDF","*.pdf")])
        if p:var.set(p)

    @staticmethod
    def _open_path(path):
        """OS 기본 프로그램으로 파일/폴더 열기 (Windows 전용 os.startfile, 이 앱은 Windows 대상)."""
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except AttributeError:
            # Windows가 아닌 환경(개발/테스트용) 대비 폴백
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(path)])

    def open_input_folder(self):
        """'폴더 열기' 버튼: 입력 PDF가 있는 폴더를 탐색기로 연다 (파일을 선택한 상태로)."""
        p=self.inp.get().strip()
        if not p:
            return messagebox.showerror("오류","먼저 입력 PDF를 선택하세요.")
        path=Path(p)
        if not path.exists():
            return messagebox.showerror("오류",f"파일을 찾을 수 없습니다:\n{path}")
        try:
            if os.name=="nt":
                subprocess.Popen(["explorer","/select,",str(path)])
            else:
                self._open_path(path.parent)
        except Exception as e:
            messagebox.showerror("오류",f"폴더를 여는 중 오류: {e}")

    def open_last_output(self):
        """'결과 열기' 버튼: 마지막으로 저장된 번역 결과 PDF를 기본 프로그램으로 연다."""
        if not self.last_output_path or not Path(self.last_output_path).exists():
            return messagebox.showinfo("안내","아직 번역 결과 파일이 없습니다.")
        self._open_path(self.last_output_path)



    def refresh_cache_stats(self):
        try:
            from pdf_engine.translator.cache import GLOBAL_CACHE
            stats = GLOBAL_CACHE.get_stats()
            count = stats.get("count", 0)
            size_mb = stats.get("size_mb", 0.0)
            self.cache_stats_var.set(f"• 저장된 번역 레코드: {count:,}개  |  DB 용량: {size_mb:.2f} MB")
        except Exception as e:
            self.cache_stats_var.set(f"캐시 조회 실패: {e}")

    def clear_cache(self):
        if not messagebox.askyesno("캐시 비우기 확인", "저장된 모든 번역 캐시 데이터를 비우시겠습니까?\n동일 문장 재번역 시 API를 다시 호출하게 됩니다."):
            return
        try:
            from pdf_engine.translator.cache import GLOBAL_CACHE
            if GLOBAL_CACHE.clear():
                messagebox.showinfo("성공", "번역 캐시가 성공적으로 비워졌습니다.")
            else:
                messagebox.showerror("오류", "캐시 비우기에 실패했습니다.")
            self.refresh_cache_stats()
        except Exception as e:
            messagebox.showerror("오류", f"캐시 비우기 실패: {e}")


    # 런타임별 기본 포트/API 경로 (translate_pdf.RUNTIME_REGISTRY와 동기화)
    _RUNTIME_PORTS = {
        "lemonade": (13305, "/api/v1/models"),
        "ollama": (11434, "/v1/models"),
        "lmstudio": (1234, "/v1/models"),
        "jan": (1337, "/v1/models"),
        "koboldcpp": (5001, "/v1/models"),
        "anythingllm": (3001, "/v1/models"),
    }

    def on_runtime_changed(self,*_):
        """런타임 드롭다운이 바뀌면 그 런타임이 지원하는 장치만 체크 가능하게 하고,
        미지원 장치는 체크 해제 + 비활성화한다."""
        caps=LOCAL_RUNTIMES.get(self.runtime.get(),{"supports_npu":False,"supports_gpu":False})
        if caps["supports_npu"]:
            self.npu_check.configure(state="normal")
        else:
            self.use_npu.set(False); self.npu_check.configure(state="disabled")
        if caps["supports_gpu"]:
            self.gpu_check.configure(state="normal")
        else:
            self.use_gpu.set(False); self.gpu_check.configure(state="disabled")
        self.on_device_toggled()
        self.refresh_models()

    def on_device_toggled(self):
        """NPU/GPU 체크 상태에 맞춰 해당 모델 드롭다운만 활성화한다.
        (체크 안 된 장치의 모델을 실수로 잘못 고르는 걸 막기 위함 - 예전엔 드롭다운이
        하나뿐이라 GPU만 체크해도 NPU 전용 모델이 그대로 남아있어 GPU 체크가 무시되는
        버그가 있었다.)"""
        self.npu_models.configure(state="normal" if self.use_npu.get() else "disabled")
        self.gpu_models.configure(state="normal" if self.use_gpu.get() else "disabled")

    def refresh_models(self):
        rt=self.runtime.get()
        label=LOCAL_RUNTIMES.get(rt,{}).get("label",rt)
        port,path=self._RUNTIME_PORTS.get(rt,(PORT,"/api/v1/models"))
        self.status.set(f"{label} 모델 조회 중...")
        def work():
            found_tuples=[]
            try:
                with urllib.request.urlopen(f"http://localhost:{port}{path}",timeout=3) as r:
                    d=json.load(r)
                items=d.get("data",[]) if isinstance(d,dict) else d
                for x in items:
                    if isinstance(x,dict):
                        m=x.get("id") or x.get("model") or x.get("name")
                        is_dl=bool(x.get("downloaded",False))
                        recipe=str(x.get("recipe","")).lower()
                    else:
                        m=str(x)
                        is_dl=False
                        recipe=""
                    if m:
                        tup=(m,is_dl,recipe)
                        if tup not in found_tuples:
                            found_tuples.append(tup)
            except Exception:
                pass
            self.after(0,lambda:self.set_models(found_tuples,label))
        threading.Thread(target=work,daemon=True).start()

    @staticmethod
    def _is_npu_model(name:str, recipe:str="")->bool:
        """모델명/레시피로 실제 실행 장치 추정."""
        if recipe in ("flm", "ryzen-ai", "npu"):
            return True
        n=name.lower()
        return n.endswith("-flm") or "-flm-" in n or "ryzen" in n or "npu" in n

    def set_models(self,found_tuples,label="Lemonade"):
        if found_tuples:
            # 다운로드 완료된 모델(is_dl=True)을 상위에 노출
            downloaded=[t for t in found_tuples if t[1]]
            other=[t for t in found_tuples if not t[1]]
            ordered=downloaded+other
            npu_found=[m for m,dl,r in ordered if self._is_npu_model(m,r)]
            gpu_found=[m for m,dl,r in ordered if not self._is_npu_model(m,r)]
        else:
            npu_found=[]
            gpu_found=[]

        cur_npu=self.model_npu.get()
        cur_gpu=self.model_gpu.get()

        npu_opts=list(npu_found) or ["gemma4-it-e2b-FLM","gemma4-it-e4b-FLM","qwen3-it-4b-FLM"]
        gpu_opts=list(gpu_found) or ["Gemma-3-4b-it-GGUF","Qwen2.5-Coder-3B-Instruct-GGUF-Q4_K_M"]

        if cur_npu and cur_npu not in npu_opts:
            npu_opts.insert(0,cur_npu)
        if cur_gpu and cur_gpu not in gpu_opts:
            gpu_opts.insert(0,cur_gpu)

        self.npu_models.set_values(npu_opts)
        self.gpu_models.set_values(gpu_opts)

        if cur_npu in npu_opts:
            self.model_npu.set(cur_npu)
        elif npu_found:
            self.model_npu.set(npu_found[0])

        if cur_gpu in gpu_opts:
            self.model_gpu.set(cur_gpu)
        elif gpu_found:
            self.model_gpu.set(gpu_found[0])

        self.model_changed()
        if found_tuples:
            dl_cnt=sum(1 for _,dl,_ in found_tuples if dl)
            self.status.set(f"대기 중 (감지된 모델 {len(found_tuples)}개, 설치 완료 {dl_cnt}개)")
        else:
            self.status.set(f"{label} 서버 연결 실패 (기본 목록 표시)")

    def cloud_model_changed(self, *_):
        """
        체크된 API 행들이 실제로 쓸 모델 전체를 모아 가장 보수적인 배치 설정을 추천한다.
        배치는 실행 시작 때 한 번 나뉘는데 도중에 어떤 모델로 폴백할지는 알 수 없으므로,
        큰 모델 기준으로 크게 잘라 두면 작은 모델로 넘어갔을 때 응답이 잘린다.
        """
        models = []
        for item in self.api_rows:
            on, mv = item[1], item[4]
            if on.get():
                models += parse_chain(mv.get())
        if not models and self.api_rows:
            models = parse_chain(self.api_rows[0][4].get())
        if models:
            c, s, t = chain_preset(models)
            self.cloud_chars.set(str(c))
            self.cloud_segs.set(str(s))
            self.cloud_tokens.set(str(t))

    def local_model_changed(self, *_):
        ref_model = self.model_npu.get() if self.use_npu.get() else self.model_gpu.get()
        if ref_model:
            c, s, t = preset(ref_model)
            self.local_chars.set(str(c))
            self.local_segs.set(str(s))
            self.local_tokens.set(str(t))

    def model_changed(self, *_):
        self.cloud_model_changed()
        self.local_model_changed()

    def start(self):
        if not self.inp.get():
            return messagebox.showerror("오류","입력 PDF를 선택하세요.")

        self.save_config()  # 입력한 API 키/설정을 즉시 저장

        keys=[]
        chain_note=[]
        for item in self.api_rows:
            on, pv, key, mv = item[1], item[2], item[3], item[4]
            if on.get() and key.get().strip():
                prov = pv.get().strip()
                # "provider@modelA,modelB,...:key" - 콤마 순서가 곧 폴백 순서다.
                chain = parse_chain(mv.get())
                if chain:
                    keys.append(f"{prov}@{','.join(chain)}:{key.get().strip()}")
                    chain_note.append(f"{prov}: {' > '.join(chain)}")
                else:
                    keys.append(f"{prov}:{key.get().strip()}")
        devices=[]
        if self.use_npu.get():devices.append("npu")
        if self.use_gpu.get():devices.append("gpu")
        if not keys and not devices:
            return messagebox.showerror("오류","사용할 API 또는 로컬 NPU/GPU를 선택하세요.")

        # 클라우드 API를 사용하는 경우 클라우드 배치 설정 적용, 로컬 AI만 사용하는 경우 로컬 배치 설정 적용
        if keys:
            b_chars = self.cloud_chars.get()
            b_segs = self.cloud_segs.get()
            b_tokens = self.cloud_tokens.get()
        else:
            b_chars = self.local_chars.get()
            b_segs = self.local_segs.get()
            b_tokens = self.local_tokens.get()

        try:
            int(b_chars); int(b_segs); int(b_tokens)
        except ValueError:
            return messagebox.showerror("오류","배치/세그먼트/max_tokens는 숫자여야 합니다.")

        fd,self.keyfile=tempfile.mkstemp(prefix="pdftranslator_",suffix=".txt")
        os.close(fd)
        Path(self.keyfile).write_text("\n".join(keys),encoding="utf-8")

        argv=[str(ENGINE),self.inp.get(),
              "--source-lang",self.src.get(),"--target-lang",self.dst.get(),
              "--batch-chars",b_chars,"--batch-segs",b_segs,
              "--max-tokens",b_tokens,"--api-key-file",self.keyfile,
              "--model-select-timeout","0","--local-runtime",self.runtime.get()]
        if self.use_npu.get(): argv+=["--model-local-npu",self.model_npu.get()]
        if self.use_gpu.get(): argv+=["--model-local-gpu",self.model_gpu.get()]
        if self.pages.get().strip(): argv+=["--pages",self.pages.get().strip()]
        if self.out.get().strip(): argv+=["-o",self.out.get().strip()]
        if devices: argv+=["--local-device",",".join(devices)]
        if not self.compress.get(): argv+=["--no-compress"]
        argv+=["--api-balance","balanced" if self.api_balance.get() else "quality"]

        self.log.delete("1.0","end")
        for note in chain_note:
            self.log.insert("end", f"[모델 순서] {note}\n")
        self.openresultbtn.configure(state="disabled")
        self.last_output_path=None
        self.engine_completed=False
        self.progress.set(0)
        self.pct=0.0
        self.trans_pct=0.0
        self.start_time=time.time()
        self.prog_info.set(f"시작: {time.strftime('%H:%M:%S')}")
        self.startbtn.configure(state="disabled")
        self.stopbtn.configure(state="normal")
        self.status.set("번역 시작")

        class QueueWriter(io.TextIOBase):
            def __init__(self,q): self.q=q
            def write(self,s):
                if s: self.q.put(("LOG",s))
                return len(s)
            def flush(self): pass

        def run():
            old_argv=sys.argv[:]
            old_env={k:os.environ.get(k) for k in ("PYTHONIOENCODING","PYTHONUTF8")}
            try:
                sys.argv=argv
                # EXE에서는 translate_pdf.py를 외부 프로세스로 재실행하지 않고
                # 동일 프로세스에 번들된 모듈로 import하여 main()을 호출한다.
                engine=importlib.import_module("translate_pdf")
                self.engine=engine
                if hasattr(engine,"reset_stop"): engine.reset_stop()
                writer=QueueWriter(self.q)
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    try:
                        engine.main()
                        code=0
                    except SystemExit as e:
                        code=e.code if isinstance(e.code,int) else (0 if e.code is None else 1)
                        if e.code and not isinstance(e.code,int):
                            print(e.code)
                self.q.put(("DONE",code))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.q.put(("ERR","번역 엔진 실행 중 예외가 발생했습니다. 로그를 확인하세요."))
            finally:
                sys.argv=old_argv
                for k,v in old_env.items():
                    if v is None: os.environ.pop(k,None)
                    else: os.environ[k]=v
        threading.Thread(target=run,daemon=True).start()

    # 전체 작업(추출 -> 번역 -> 후처리 -> 저장 -> 압축)에서 각 단계가 차지하는 진행률 구간.
    # 번역만 0~100%로 잡으면, 번역이 끝난 뒤에도 재구성/저장/압축이 몇 분씩 더 걸리는데
    # 진행바는 이미 100%에 붙어 있어 "다 됐다는데 왜 계속 도나" 하는 상태가 된다
    # (실제로 사용자가 겪은 증상). 번역은 전체의 8~85% 구간에 매핑한다.
    STAGE_EXTRACT   = 6.0    # [1/4] 추출 완료
    STAGE_PREPARE   = 8.0    # 문맥 감지/플레이스홀더 등 번역 직전 준비
    STAGE_TRANS_END = 85.0   # 번역 완료
    STAGE_POST      = 88.0   # 후처리/검증
    STAGE_SAVE      = 91.0   # PDF 재구성/저장 시작
    STAGE_REBUILT   = 95.0   # [4/4] 재구성 완료
    STAGE_COMPRESS  = 98.0   # 압축

    def set_overall(self, pct: float):
        """전체 진행률을 갱신한다. 뒤로 가지 않도록(단조 증가) 보정한다."""
        pct = max(0.0, min(100.0, float(pct)))
        if pct < self.pct:
            return
        self.pct = pct
        self.progress.set(pct / 100.0)

    def poll(self):
        try:
            while True:
                typ,val=self.q.get_nowait()
                if typ=="LOG":
                    self.log.insert("end",val);self.log.see("end")
                    fm=re.search(r"\[최종파일\]\s*(.+)",val)
                    if fm:
                        self.last_output_path=fm.group(1).strip()
                        self.openresultbtn.configure(state="normal")
                    # 엔진의 구조화 진행 라인: [진행] batch=i/N segs=d/D pages=p/P pct=xx.x
                    # segs= 필드는 배치 크기와 무관하게 '실제 처리된 세그먼트 수' 기준이라
                    # 진행률이 배치 경계마다 계단식으로 튀지 않고 매끄럽게 올라간다.
                    pm=re.search(r"\[진행\] batch=(\d+)/(\d+)(?: segs=(\d+)/(\d+))? pages=(\d+)/(\d+) pct=([\d.]+)",val)
                    if pm:
                        bi,bn=int(pm.group(1)),int(pm.group(2))
                        sd,st=(int(pm.group(3)),int(pm.group(4))) if pm.group(3) else (None,None)
                        pd,pt,tpct=int(pm.group(5)),int(pm.group(6)),float(pm.group(7))
                        # 엔진의 pct는 '번역 대상 세그먼트 중 몇 개를 끝냈는지'(캐시 복원분
                        # 제외)라서 항상 0%에서 시작해 100%까지 올라간다. 그것을 전체
                        # 작업의 번역 구간(8~85%)에 비례 배분한다.
                        self.trans_pct=tpct
                        self.set_overall(self.STAGE_PREPARE
                                         + (self.STAGE_TRANS_END-self.STAGE_PREPARE)*tpct/100.0)
                        if sd is not None:
                            self.status.set(f"번역 중 - {sd}/{st}세그먼트 · {pd}/{pt}페이지 "
                                            f"(배치 {bi}/{bn}, 번역 {tpct:.1f}% · 전체 {self.pct:.1f}%)")
                        else:
                            self.status.set(f"번역 중 - 전체 {pt}페이지 중 {pd}페이지 진행 "
                                            f"(배치 {bi}/{bn}, 번역 {tpct:.1f}% · 전체 {self.pct:.1f}%)")
                    else:
                        # 요청 전송/응답 대기/응답 수신 - 진행바는 이미 [진행] 라인이 갱신하므로
                        # 여기선 상태 텍스트만 실시간으로 바꿔 "지금 뭘 하는 중인지" 보여준다
                        # (긴 배치 응답을 기다리는 동안 화면이 멈춘 것처럼 보이지 않게).
                        rm=re.search(r"\[batch (\d+)/(\d+)\] (.+?)로 (\d+)개 세그먼트 \(([\d,]+)자\) 요청 전송",val)
                        wm=re.search(r"\[batch (\d+)/(\d+)\] (.+?) 응답 대기 중\.\.\. \((\d+)초 경과\)",val)
                        vm=re.search(r"\[batch (\d+)/(\d+)\] (.+?) 응답 수신 \(([\d.]+)초\) -> (\d+)/(\d+)개",val)
                        if rm:
                            self.status.set(f"번역 중 - {rm.group(3)}에 {rm.group(4)}개 세그먼트 "
                                            f"({rm.group(5)}자) 요청 전송 (배치 {rm.group(1)}/{rm.group(2)})")
                        elif wm:
                            self.status.set(f"번역 중 - {wm.group(3)} 응답 대기 중... "
                                            f"({wm.group(4)}초 경과, 배치 {wm.group(1)}/{wm.group(2)})")
                        elif vm:
                            self.status.set(f"번역 중 - {vm.group(3)} 응답 수신 ({vm.group(4)}초) "
                                            f"- {vm.group(5)}/{vm.group(6)}개 번역됨")
                        else:
                            # 단계 표시 로그를 전체 진행률 구간에 매핑한다.
                            # (번역 구간은 위 [진행] 라인이 담당하므로 여기서는 앞뒤 단계만)
                            m=re.search(r"\[batch (\d+)/(\d+)\]",val)
                            if m and self.trans_pct==0:
                                # [진행] 라인이 아직 안 나온 첫 배치 구간의 임시 추정치
                                bi_,bn_=int(m.group(1)),max(1,int(m.group(2)))
                                self.set_overall(self.STAGE_PREPARE
                                                 + (self.STAGE_TRANS_END-self.STAGE_PREPARE)
                                                 * (bi_-1)/bn_)
                            elif "[1/4]" in val or "[1/5]" in val:
                                self.set_overall(self.STAGE_EXTRACT)
                            elif "[1.5/5]" in val or "[2/5]" in val or "[3/5]" in val:
                                self.set_overall(self.STAGE_PREPARE)
                            elif "[3/4]" in val:
                                self.set_overall(self.STAGE_TRANS_END)
                                self.status.set("번역 완료 - 후처리 중...")
                            elif "[4/5]" in val:
                                self.set_overall(self.STAGE_POST)
                            elif "[저장]" in val:
                                self.set_overall(self.STAGE_SAVE)
                                self.status.set("번역문을 PDF에 삽입하는 중...")
                            elif "[4/4]" in val:
                                self.set_overall(self.STAGE_REBUILT)
                                self.status.set("PDF 재구성 완료 - 마무리 중...")
                                self.engine_completed=True
                            elif "[압축 시작]" in val:
                                self.set_overall(self.STAGE_COMPRESS)
                                self.status.set("PDF 압축 중... (파일이 크면 수십 초 걸립니다)")
                            elif "[압축]" in val:
                                self.set_overall(99.0)
                            elif "[최종파일]" in val:
                                self.set_overall(100.0)
                else:
                    self.cleanup();self.startbtn.configure(state="normal");self.stopbtn.configure(state="disabled")
                    self.start_time=None
                    if typ=="DONE":
                        # 출력 PDF 재구성 완료 로그가 확인되면 후처리의 비핵심 종료코드보다 실제 결과를 우선한다.
                        effective_code = 0 if self.engine_completed else val
                        self.status.set("완료" if effective_code==0 else f"오류 종료 ({effective_code})")
                        if effective_code==0:
                            self.progress.set(1.0)
                            if self.auto_open.get() and self.last_output_path:
                                self.open_last_output()
                        messagebox.showinfo("실행 종료","번역 및 PDF 저장이 완료되었습니다." if effective_code==0 else f"프로세스 종료 코드: {effective_code}")
                    else:self.status.set("오류");messagebox.showerror("오류",val)
        except queue.Empty:pass
        # 경과/예상 시간 갱신 (1초 단위 체감)
        if self.start_time:
            el=time.time()-self.start_time
            h,rem=divmod(int(el),3600); m,s=divmod(rem,60)
            eta="계산 중" if self.pct<=0 else time.strftime("%H:%M:%S",time.gmtime(el/self.pct*(100-self.pct)))
            self.prog_info.set(
                f"시작: {time.strftime('%H:%M:%S',time.localtime(self.start_time))}"
                f" | 경과: {h:02d}:{m:02d}:{s:02d}"
                f" | 예상 남은시간: {eta}"
                f" | 진행률: {self.pct:.1f}%")
        self.after(100,self.poll)

    def cleanup(self):
        if self.keyfile:
            try:os.remove(self.keyfile)
            except:pass
            self.keyfile=None
    def stop(self):
        """우아한 중단: 엔진에 중단 신호 -> 현재 배치까지 번역 후 나머지는 원문 유지 저장.
        저장된 파일명의 _untranslated 구간으로 나중에 이어서-번역 가능."""
        eng=self.engine
        if eng is None:
            eng=sys.modules.get("translate_pdf")
        if eng is not None and hasattr(eng,"request_stop"):
            eng.request_stop()
            self.stopbtn.configure(state="disabled")
            self.status.set("중단 요청됨 - 현재 배치 완료 후 진행분까지 저장합니다...")
            self.log.insert("end","[GUI] 중단 요청 - 현재 처리 중인 배치가 끝나면 "
                                  "번역된 부분까지 PDF로 저장됩니다.\n")
            self.log.see("end")
        else:
            messagebox.showinfo("중지 안내","실행 중인 번역 작업이 없습니다.")

if __name__=="__main__":
    App().mainloop()
