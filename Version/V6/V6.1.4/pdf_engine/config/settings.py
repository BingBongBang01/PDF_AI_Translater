"""
버전, 경로 상수, 실행 중단(STOP) 제어, 로컬 런타임 레지스트리, 기본 모델 설정.
다른 모든 모듈이 가장 먼저 의존하는 기반 모듈이라 여기엔 다른 pdf_engine 모듈을
import하지 않는다(순환 참조 방지).
"""
from __future__ import annotations
from pdf_engine.logger import get_logger


import os
import re
import threading
from pathlib import Path

# 버전 표기는 이 상수 하나에서만 관리한다. gui.py는 이 값을 import해서 타이틀에 쓰고,
# build_exe.bat은 이 값을 읽어 실행파일 이름을 결정한다 (버전 문자열이 여러 곳에 흩어져
# 서로 어긋나는 사고 방지 - 예: v3.82로 하드코딩된 채 zip 이름만 v3.84로 배포됐던 문제).
__version__ = "6.1.4"

# ---------------------------------------------------------------------------
# 로컬 AI 런타임 레지스트리 - Lemonade 외 다른 로컬 서버(Ollama, LM Studio 등)를
# 지원하기 위한 확장 지점.
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
        "serve_candidates": [("lms", ["server", "start"])],
        "needs_ctx_load": False,
        "needs_model_menu": False,
    },
    "jan": {
        "label": "Jan.ai",
        "default_port": 1337,
        "supports_npu": False,
        "supports_gpu": True,
        "api_prefix": "/v1",
        "health_path": "/v1/models",
        "serve_candidates": [("jan", [])],
        "needs_ctx_load": False,
        "needs_model_menu": False,
    },
    "koboldcpp": {
        "label": "KoboldCPP",
        "default_port": 5001,
        "supports_npu": False,
        "supports_gpu": True,
        "api_prefix": "/v1",
        "health_path": "/v1/models",
        "serve_candidates": [("koboldcpp", [])],
        "needs_ctx_load": False,
        "needs_model_menu": False,
    },
    "anythingllm": {
        "label": "AnythingLLM",
        "default_port": 3001,
        "supports_npu": False,
        "supports_gpu": True,
        "api_prefix": "/v1",
        "health_path": "/v1/models",
        "serve_candidates": [("anythingllm", [])],
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
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent  # Root directory containing translate_pdf.py의 부모)

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

LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

DEFAULT_MODELS = {
    "anthropic": "claude-3-7-sonnet-20250219",
    # 모델을 하나만 쓸 때의 기본값 = 폴백 체인의 1순위(MODEL_CHAIN_INFO 참고).
    # 전문 용어가 많은 PDF는 품질이 우선이라 최신 표준 Flash를 앞에 두고, 그 모델의
    # 하루 한도(RPD 20)가 끝나면 체인의 다음 모델(결국 RPD 500인 flash-lite)로 넘어간다.
    "gemini": "gemini-3.7-flash",
    "openai": "gpt-4o-mini",
    "local": "gemma4-it-e2b-FLM",  # 하위 호환용 (device 미지정 시 기본값 = NPU 모델)
    # OpenAI 호환 API를 제공하는 부가 provider들 (providers_cloud.OPENAI_COMPATIBLE_BASES)
    "deepseek": "deepseek-chat",
    "openrouter": "google/gemini-2.5-flash-lite",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "qwen2.5",
}
DEFAULT_MODEL = DEFAULT_MODELS["anthropic"]  # 하위 호환용

# ---------------------------------------------------------------------------
# provider별 모델 폴백 체인 (앞에 있을수록 우선순위가 높다)
# ---------------------------------------------------------------------------
# Gemini의 RPM(분당 요청)/TPM(분당 토큰)/RPD(일일 요청) 한도는 계정·프로젝트 단위가
# 아니라 '모델별로 각각 독립'이다. 즉 gemini-3.7-flash의 하루 20건을 다 써도
# gemini-3.5-flash의 20건, flash-lite의 500건은 그대로 남아 있다. 다만 구글 서버가
# 알아서 다음 모델로 넘겨주지는 않으므로, 429(RESOURCE_EXHAUSTED)를 감지해서
# '같은 키 + 다음 모델'로 재요청하는 폴백을 우리가 직접 돌려야 한다
# (실제 구현: translator/scheduler.py의 next_alive_index + 쿨다운 처리).
#
# 순서 기준은 '번역 품질 우선':
#   최신 표준 Flash -> 구세대 Flash -> RPD가 큰 Flash Lite(대량 처리용 최후 보루)
# rpm/rpd는 무료 티어 기준이며 GUI 모델 선택 창의 안내 문구에만 쓰인다.
MODEL_CHAIN_INFO: dict[str, list[dict]] = {
    "gemini": [
        {"id": "gemini-3.7-flash",      "rpm": 5,  "rpd": 20,  "note": "최신 표준 Flash - 전문용어/긴 문맥 이해 최상"},
        {"id": "gemini-3.6-flash",      "rpm": 5,  "rpd": 20,  "note": "3세대 Flash - 품질 상위"},
        {"id": "gemini-3.5-flash",      "rpm": 5,  "rpd": 20,  "note": "3.5세대 표준 - 안정적 품질"},
        {"id": "gemini-3-flash",        "rpm": 5,  "rpd": 20,  "note": "3세대 기본 - 기술문서 강함"},
        {"id": "gemini-2.5-flash",      "rpm": 5,  "rpd": 20,  "note": "2.5세대 표준 - 3세대 소진 시 대체"},
        {"id": "gemini-3.5-flash-lite", "rpm": 15, "rpd": 500, "note": "일일 500건 - 대량 이어받기용 주력"},
        {"id": "gemini-3.1-flash-lite", "rpm": 15, "rpd": 500, "note": "일일 500건 - 연속 처리용"},
        {"id": "gemini-2.5-flash-lite", "rpm": 10, "rpd": 20,  "note": "마지막 보루"},
    ],
    "anthropic": [
        {"id": "claude-3-7-sonnet-20250219", "note": "품질 우선"},
        {"id": "claude-3-5-sonnet-20241022", "note": "대체"},
        {"id": "claude-3-5-haiku-20241022",  "note": "저비용/고속 - 한도 소진 시 이어받기"},
    ],
    "openai": [
        {"id": "gpt-4o-mini", "note": "번역 기본"},
        {"id": "gpt-4o",      "note": "품질 우선"},
    ],
}


def default_model_chain(provider: str) -> list[str]:
    """provider의 권장 모델 폴백 체인(우선순위 순). 없으면 기본 모델 하나만."""
    chain = [m["id"] for m in MODEL_CHAIN_INFO.get(provider, [])]
    return chain or [DEFAULT_MODELS.get(provider, DEFAULT_MODELS["openai"])]


LEMONADE_DEFAULT_PORT = 13305  # 신버전(C++) Lemonade Server 기본 포트 (구버전 Python 서버는 8000이었음)
LEMONADE_SERVE_CMD = "LemonadeServer"  # 신버전(C++) 실제 서버 실행파일. 'lemonade'는 그 서버에 말 거는 클라이언트일 뿐 서버 본체가 아님
DEFAULT_TERMINOLOGY_POLICY = (
    "Use established target-language technical terminology. "
    "Keep well-known technical abbreviations, protocol names, commands, and product names "
    "(e.g., VXLAN, BGP, OSPF, CLI, API) in their original form. "
    "For an important technical term, the first occurrence may include the original term in parentheses."
)
# ---------------------------------------------------------------------------
# 로컬 NPU/GPU 장치별 기본 모델 (Lemonade에서 NPU/GPU는 모델의 recipe로 고정됨)
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
            get_logger().log(f"[경고] {explicit}은(는) 실제로 {actual.upper()} 전용 모델입니다. "
                  f"{device.upper()}를 요청했지만 이 모델은 항상 {actual.upper()}로 실행됩니다 "
                  f"(Lemonade는 장치를 모델의 recipe로 고정하며, 실행 시점에 전환할 수 없습니다).")
        return explicit
    return DEFAULT_LOCAL_MODEL_BY_DEVICE.get(device, DEFAULT_MODELS["local"])


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
class FeatureFlags:
    """Global feature toggles for the translation pipeline."""
    enable_glossary = True
    enable_validation = True
    enable_placeholder = True
    enable_context_detection = True
    enable_style_fix = True

    @classmethod
    def load_from_args(cls, args):
        cls.enable_glossary = not getattr(args, "disable_glossary", False)
        cls.enable_validation = not getattr(args, "disable_validation", False)
        cls.enable_placeholder = not getattr(args, "disable_placeholder", False)
        cls.enable_context_detection = not getattr(args, "disable_context_detection", False)
        cls.enable_style_fix = not getattr(args, "disable_style_fix", False)
