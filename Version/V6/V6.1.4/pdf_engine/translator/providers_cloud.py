"""
클라우드 AI 제공자(Anthropic Claude, Google Gemini, OpenAI) 클라이언트 생성,
API 키 풀 관리, LLM 호출, 에러 유형 판별(인증/할당량/429 등)을 담당한다.
"""
from __future__ import annotations
# 주의: pdf_engine.validator.api_validator에도 같은 이름의 함수들이 있지만 그쪽은
# '문자열'을 받는 구버전 시그니처다. 이 모듈은 '예외 객체'를 받는 아래쪽 정의를 쓴다.
# (예전엔 여기서 api_validator를 import했는데, 아래 def들이 그 이름을 다시 덮어써서
#  import 자체가 죽은 코드였고 읽는 사람만 헷갈리게 했다 - 그래서 제거했다.)
from pdf_engine.logger import get_logger


import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pdf_engine.config.settings import DEFAULT_MODELS, _parse_local_devices
from pdf_engine.placeholder.batching import is_label_like
from pdf_engine.translator.ratelimit import GLOBAL_LEDGER, key_fingerprint, limits_for

@dataclass
class KeyEntry:
    provider: str
    model: str
    client: object
    label: str          # 로그 표기용 (예: "gemini#1", "openai#1", "anthropic#1", "local-NPU")
    alive: bool = True   # False = 일시 쿨다운(429) 또는 일일/영구 할당량 소진으로 제외
    is_local: bool = False  # True = 로컬 NPU(Lemonade). 클라우드 키가 전부 죽은 뒤에만 사용
    revive_at: float | None = None  # 부활 예정 시각(time.monotonic 기준). None=영구 제외
    priority: int = 0   # 낮을수록 먼저 쓴다. 같은 키의 모델 폴백 체인에서 모델의 순위.
                        # Gemini는 한도가 모델별로 독립이라, 키가 하나여도 우선순위가 높은
                        # 모델부터 쓰다가 그 모델이 한도에 걸리면 다음 모델로 자동 전환된다.
    key_id: str = ""    # 키의 짧은 해시(원본 키는 저장하지 않는다). 사용량 장부의 키.
    key_no: int = 0     # 같은 provider 안에서 몇 번째 키인지 (키 단위 분산에 쓴다)
    rpm_limit: int | None = None  # 분당 요청 한도(모델·키별). None=모름/무제한
    rpd_limit: int | None = None  # 일일 요청 한도(모델·키별). None=모름/무제한
    calls: int = 0      # 이번 실행에서 이 항목으로 보낸 요청 수 (분산 계산 + 마지막 요약용)
    last_used: float = 0.0        # 마지막 사용 시각(time.monotonic). 같은 순위끼리 LRU 분산


_KEY_PREFIXES = {
    "anthropic": ("sk-ant-",),
    "gemini": ("AIza", "AQ."),
    "openai": ("sk-proj-", "sk-"),  # sk- 는 openai가 마지막 순위(anthropic의 sk-ant-와 겹치므로 순서 중요)
}
_PROVIDER_ALIASES = {"gpt": "openai", "claude": "anthropic", "google": "gemini"}


def detect_provider(key: str) -> str | None:
    """
    'provider:키' 또는 'provider@model:키' 형식이면 명시적으로 그 provider를 쓴다.
    아니면 키 형태(prefix)로 자동 판별한다. sk-ant-(Anthropic) > AIza/AQ.(Gemini) > sk-(OpenAI) 순으로 검사
    (OpenAI 키가 'sk-'로 시작해 Anthropic의 'sk-ant-'와 겹치므로 Anthropic을 먼저 검사).
    """
    if ":" in key:
        prefix, rest = key.split(":", 1)
        prefix = prefix.strip()
        if "@" in prefix:
            prefix = prefix.split("@", 1)[0].strip()
        p = _PROVIDER_ALIASES.get(prefix.lower(), prefix.lower())
        if p in DEFAULT_MODELS or p in ("deepseek", "openrouter", "groq", "ollama"):
            return p
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith(("AIza", "AQ.")):
        return "gemini"
    if key.startswith("sk-"):
        return "openai"
    return None


def parse_key_line(key: str) -> tuple[str | None, str | None, str]:
    """
    한 줄에서 (provider, model_override, key)를 추출.
    지원 형식:
      - provider@model:key
      - provider:key
      - key (자동 판별)
    """
    raw = key.strip()
    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        prefix = prefix.strip()
        model_override = None
        if "@" in prefix:
            prov, model_override = prefix.split("@", 1)
            prov = prov.strip().lower()
            model_override = model_override.strip() or None
        else:
            prov = prefix.lower()
        p = _PROVIDER_ALIASES.get(prov, prov)
        # 알려진 provider 이름일 때만 'provider:key' 형식으로 해석한다.
        # (키 문자열 자체에 ':'가 들어 있는 경우를 provider 지정으로 오인하면
        #  키가 통째로 잘려 인증 오류가 난다.)
        if p in DEFAULT_MODELS:
            return p, model_override, rest.strip()
    p = detect_provider(raw)
    return p, None, strip_provider_prefix(raw)


def strip_provider_prefix(key: str) -> str:
    if ":" in key:
        prefix, rest = key.split(":", 1)
        if "@" in prefix:
            prefix = prefix.split("@", 1)[0]
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


def load_key_pool(args) -> list[tuple[str, str | None, str]]:
    """
    api.txt(또는 --api-key-file)에서 여러 provider의 키를 한 번에 읽어
    [(provider, model_override, key), ...] 형태로 반환한다.
    """
    candidates: list[Path] = []
    if args.api_key_file:
        candidates.append(Path(args.api_key_file))
    else:
        candidates += [Path.cwd() / "api.txt", Path(__file__).resolve().parent / "api.txt"]

    entries: list[tuple[str, str | None, str]] = []
    unknown = 0
    for p in candidates:
        if p.is_file():
            text = _decode_key_file_text(p.read_bytes(), p)
            for ln in text.splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                provider, model_override, key_str = parse_key_line(ln)
                if provider is None:
                    unknown += 1
                    get_logger().log(f"  [경고] 키 형식을 알 수 없어 건너뜀: {ln[:12]}...")
                    continue
                entries.append((provider, model_override, key_str))
            break  # 첫 번째로 발견된 파일만 사용

    if not entries:
        for provider, env_var in (("anthropic", "ANTHROPIC_API_KEY"),
                                  ("gemini", "GEMINI_API_KEY"),
                                  ("openai", "OPENAI_API_KEY")):
            env_val = os.environ.get(env_var) or \
                (os.environ.get("GOOGLE_API_KEY") if provider == "gemini" else None)
            if env_val:
                entries += [(provider, None, k.strip()) for k in env_val.split(",") if k.strip()]

    if args.provider:
        entries = [e for e in entries if e[0] == args.provider]

    if not entries:
        has_local = bool(_parse_local_devices(args))
        if has_local:
            get_logger().log("[정보] 클라우드 API 키를 찾지 못함 -> 로컬 장치 지정됨, 로컬만으로 진행")
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


def resolve_model_chain(args, provider: str, model_override: str | None = None) -> list[str]:
    """
    이 키로 사용할 모델 목록을 '우선순위 순'으로 돌려준다.

    Gemini처럼 한도(RPM/TPM/RPD)가 모델별로 독립인 provider는 키가 하나뿐이어도
    여러 모델을 순서대로 갈아타며 쓸 수 있다. api.txt에 'gemini@A,B,C:키'처럼 콤마로
    나열하면 그 순서가 곧 폴백 순서다(GUI의 모델 선택 창이 이 형식으로 써 준다).
    모델을 하나만 적었거나 아예 안 적었으면 기존과 똑같이 단일 모델로 동작한다.
    """
    raw = model_override
    if not raw:
        # CLI에서도 --model-gemini "A,B,C"처럼 콤마로 체인을 줄 수 있다.
        raw = {"anthropic": getattr(args, "model_anthropic", None),
               "gemini": getattr(args, "model_gemini", None),
               "openai": getattr(args, "model_openai", None)}.get(provider)
        if not raw and getattr(args, "model", None) and getattr(args, "provider", None) == provider:
            raw = args.model
    models = [m.strip() for m in (raw or "").split(",") if m.strip()]
    if models:
        # 중복 제거하되 순서는 유지 (같은 모델을 두 번 쓰면 한도만 두 번 확인하게 된다)
        seen, chain = set(), []
        for m in models:
            if m not in seen:
                seen.add(m)
                chain.append(m)
        return chain
    return [resolve_model(args, provider)]


def resolve_model(args, provider: str, model_override: str | None = None) -> str:
    """
    이 키에 실제로 사용할 모델 이름(단일)을 결정한다. 우선순위:
      1) api.txt 한 줄에 'provider@model:key'로 붙여 쓴 키별 모델 (GUI가 이 형식을 쓴다)
      2) --model-anthropic/--model-gemini/--model-openai 같은 provider별 인자
      3) --provider로 단일 provider를 지정했을 때의 --model
      4) DEFAULT_MODELS의 기본값
    """
    if model_override:
        return model_override.split(",")[0].strip()
    override = {"anthropic": getattr(args, "model_anthropic", None),
                "gemini": getattr(args, "model_gemini", None),
                "openai": getattr(args, "model_openai", None)}.get(provider)
    if override:
        return override
    if getattr(args, "model", None) and getattr(args, "provider", None) == provider:
        return args.model  # 단일 provider로 명시했을 때만 --model 허용 (혼합 풀에서는 모호하므로 무시)
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["openai"])


# OpenAI SDK로 그대로 말을 걸 수 있는(=/v1/chat/completions 호환) 부가 provider들.
# GUI의 provider 드롭다운에 이 항목들이 이미 노출돼 있는데 엔진이 anthropic/gemini/openai
# 3개만 지원해서, 고르는 순간 "알 수 없는 provider"로 즉시 종료되던 문제를 해결한다.
OPENAI_COMPATIBLE_BASES = {
    "openai": None,  # 공식 엔드포인트 (base_url 지정 안 함)
    "deepseek": "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://localhost:11434/v1",
}


DEFAULT_API_TIMEOUT = 180.0  # 초. build_client()의 api_timeout 기본값 (아래 설명 참고)


def build_client(provider: str, key: str, api_timeout: float = DEFAULT_API_TIMEOUT):
    """
    provider별 SDK 클라이언트를 만든다. api_timeout(초)을 반드시 명시적으로 넘긴다.

    실제 확인된 문제: google-genai SDK는 클라이언트 생성 시 타임아웃을 지정하지
    않으면 내부적으로 httpx에 timeout=None을 넘긴다 - 즉 서버가 응답을 영영 안 주면
    요청이 '영원히' 걸린 채 예외도 안 나고 진행률도 0%에서 멈춘다(사용자가 겪은
    "한 번 요청되고 10분째 진행이 안 됨" 증상과 정확히 일치). 응답이 없으면 결국
    예외를 던지도록 모든 provider에 명시적 타임아웃을 건다 - 그래야 스케줄러가
    그 예외를 잡아 다음 모델/키로 넘어갈 수 있다.
    """
    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            sys.exit("[오류] anthropic SDK가 없습니다. 설치: pip install anthropic")
        return anthropic.Anthropic(api_key=key, timeout=api_timeout)
    if provider == "gemini":
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            sys.exit("[오류] google-genai SDK가 없습니다. 설치: pip install google-genai")
        return genai.Client(api_key=key,
                            http_options=types.HttpOptions(timeout=int(api_timeout * 1000)))
    if provider in OPENAI_COMPATIBLE_BASES:
        try:
            from openai import OpenAI as OpenAIClient
        except ImportError:
            sys.exit("[오류] openai SDK가 없습니다. 설치: pip install openai")
        base = OPENAI_COMPATIBLE_BASES[provider]
        # ollama 등 로컬 서버는 키가 필요 없지만 SDK가 빈 문자열을 거부하므로 더미를 넣는다.
        return OpenAIClient(api_key=key or "local", timeout=api_timeout,
                            **({"base_url": base} if base else {}))
    sys.exit(f"[오류] 알 수 없는 provider: {provider} "
             f"(지원: anthropic, gemini, {', '.join(OPENAI_COMPATIBLE_BASES)})")


def api_provider_of(provider: str) -> str:
    """호출 규약 기준의 provider (deepseek/groq 등은 OpenAI 호환 규약을 쓴다)."""
    if provider in ("anthropic", "gemini"):
        return provider
    return "openai"


def get_key_pool(args) -> list[KeyEntry]:
    """
    api.txt(여러 provider 혼합 가능)를 읽어 KeyEntry 풀을 구성한다.

    키 하나에 모델이 여러 개 지정돼 있으면 '모델 수만큼' KeyEntry를 만들되 HTTP 클라이언트는
    하나만 만들어 공유하고, priority에 모델 순위를 넣는다. 스케줄러는 살아있는 것 중
    priority가 가장 낮은(=우선순위 높은) 항목부터 쓰므로, 앞 모델이 한도에 걸려 쿨다운되면
    자동으로 다음 모델로 넘어간다. (한도가 모델별로 독립인 Gemini에서 키 1개의 하루
    처리량을 몇 배로 늘려주는 핵심 동작이다.)
    """
    raw_entries = load_key_pool(args)
    counts: dict[str, int] = {}
    chains: dict[str, list[str]] = {}
    pool: list[KeyEntry] = []
    for provider, model_override, key in raw_entries:
        counts[provider] = counts.get(provider, 0) + 1
        key_no = counts[provider]
        chain = resolve_model_chain(args, provider, model_override)
        # 키마다 체인이 다를 수 있으므로(한 키만 모델을 여러 개 지정한 경우 등) 전부 모아 둔다
        chains.setdefault(provider, [])
        if chain not in chains[provider]:
            chains[provider].append(chain)
        api_timeout = getattr(args, "api_timeout", DEFAULT_API_TIMEOUT)
        client = build_client(provider, key, api_timeout)   # 키당 클라이언트 1개를 모든 모델이 공유
        rpm_limit, rpd_limit = limits_for(provider, args)
        fp = key_fingerprint(key)
        for rank, model in enumerate(chain):
            label = f"{provider}#{key_no}"
            if len(chain) > 1:
                label += f"[{rank + 1}/{len(chain)}] {model}"
            pool.append(KeyEntry(
                provider=api_provider_of(provider),
                model=model,
                client=client,
                label=label,
                priority=rank,
                key_id=fp,
                key_no=key_no,
                rpm_limit=rpm_limit,
                rpd_limit=rpd_limit,
            ))
    if pool:
        for p, n in counts.items():
            for chain in chains.get(p, []):
                if len(chain) > 1:
                    get_logger().log(f"[정보] {p} 키 {n}개 로드됨 -> 모델 폴백 체인 {len(chain)}단계: "
                                     + " > ".join(chain))
                else:
                    get_logger().log(f"[정보] {p} 키 {n}개 로드됨 -> 모델 {chain[0] if chain else '?'}")
        limited = [e for e in pool if e.rpd_limit]
        if limited:
            cap = sum(e.rpd_limit for e in limited)
            used = sum(GLOBAL_LEDGER.used_today(e.key_id, e.model) for e in limited)
            get_logger().log(f"[정보] 총 번역 경로 {len(pool)}개 "
                             f"(오늘 사용량 장부 기준 {used}/{cap}회 사용, "
                             f"한도에 닿기 전에 다른 키/모델로 자동 분산)")
            # 이미 오늘 많이 쓴 항목은 미리 알려 준다 - "왜 1순위 모델을 안 쓰지?"를 설명해 준다.
            hot = [e for e in limited
                   if GLOBAL_LEDGER.used_today(e.key_id, e.model) >= max(1, int(e.rpd_limit * 0.5))]
            for e in sorted(hot, key=lambda x: -GLOBAL_LEDGER.used_today(x.key_id, x.model))[:6]:
                get_logger().log(f"       - {e.label}: 오늘 "
                                 f"{GLOBAL_LEDGER.used_today(e.key_id, e.model)}/{e.rpd_limit}회 사용됨")
        else:
            get_logger().log(f"[정보] 총 번역 경로 {len(pool)}개 "
                             f"(한도 소진 시 우선순위 순으로 자동 전환)")
    return pool

def call_claude(client, model: str, system_prompt: str, user_prompt: str,
                max_tokens: int, temperature: float | None) -> str:
    # System Prompt Caching (Anthropic Prompt Caching)
    system_block = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_block,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        msg = client.messages.create(**kwargs)
    except Exception as e:
        # cache_control 파라미터 미지원 또는 temperature 오류 대응 폴백
        err_str = str(e).lower()
        if "cache_control" in err_str or "system" in err_str:
            kwargs["system"] = system_prompt
        if temperature is not None and "temperature" in err_str:
            kwargs.pop("temperature", None)
        try:
            msg = client.messages.create(**kwargs)
        except Exception:
            # 최종 폴백: 기본 string system 및 파라미터 재시도
            kwargs["system"] = system_prompt
            kwargs.pop("temperature", None)
            msg = client.messages.create(**kwargs)
    # thinking 블록 등은 .text 속성이 없으므로 자동 배제
    return "".join(getattr(block, "text", "") for block in msg.content)


def _gemini_finish_info(resp) -> str:
    """응답이 비었을 때 원인을 사람이 읽을 수 있게 요약한다 (전체 resp 덤프는 너무 길다)."""
    bits = []
    try:
        for c in (getattr(resp, "candidates", None) or []):
            fr = getattr(c, "finish_reason", None)
            if fr is not None:
                bits.append(f"finish_reason={getattr(fr, 'name', fr)}")
        fb = getattr(resp, "prompt_feedback", None)
        if fb is not None and getattr(fb, "block_reason", None):
            bits.append(f"block_reason={getattr(fb.block_reason, 'name', fb.block_reason)}")
        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            thoughts = getattr(usage, "thoughts_token_count", None)
            if thoughts:
                bits.append(f"thinking_tokens={thoughts}")
    except Exception:
        pass
    return ", ".join(bits) or "원인 정보 없음"


# thinking_config를 붙이면 400을 돌려주는 모델 이름을 실행 중에 기억해 둔다
# (모델마다 지원 여부가 달라서, 한 번 확인하면 그 뒤로는 헛된 왕복을 안 한다).
_GEMINI_NO_THINKING_CONFIG: set[str] = set()


def call_gemini(client, model: str, system_prompt: str, user_prompt: str,
                max_tokens: int, temperature: float | None) -> str:
    from google.genai import types
    config_kwargs = dict(
        system_instruction=system_prompt,
        max_output_tokens=max_tokens,
        # 응답을 JSON으로 강제 -> parse_model_json의 관대 파싱과 이중 안전장치
        response_mime_type="application/json",
    )
    if temperature is not None:
        config_kwargs["temperature"] = temperature

    # Gemini 2.5 이상(flash/pro/3.x 계열)은 기본적으로 '사고(thinking)'를 하는데, 그 사고
    # 토큰이 max_output_tokens를 같이 소모한다. 번역처럼 출력이 긴 작업에서는 사고만 하다가
    # 예산을 다 써서 finish_reason=MAX_TOKENS로 끝나고 resp.text가 통째로 비어버리는
    # 일이 실제로 자주 발생한다(그러면 배치 전체가 "응답에 텍스트가 없습니다"로 실패).
    # 번역엔 사고가 필요 없으므로 thinking_budget=0으로 끄고, 이 필드를 모르는 구버전
    # SDK/모델이면 조용히 빼고 재시도한다.
    thinking_kwargs = {}
    if model not in _GEMINI_NO_THINKING_CONFIG:
        try:
            thinking_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass

    def _generate(extra: dict):
        config = types.GenerateContentConfig(**{**config_kwargs, **extra})
        return client.models.generate_content(model=model, contents=user_prompt, config=config)

    try:
        resp = _generate(thinking_kwargs)
    except Exception as e:
        msg = str(e).lower()
        # 실제 확인된 문제: gemini-3.6-flash가 위 설정 그대로면 "400 INVALID_ARGUMENT:
        # Request contains an invalid argument."만 돌려준다. 메시지에 'thinking'/'budget'
        # 같은 단서가 전혀 없어서 예전 조건("thinking" in msg)에 안 걸렸고, 그대로 실패로
        # 올라가 그 모델이 폴백 체인에서 통째로 무용지물이 됐다(로그: 문맥 감지 단계에서
        # 3.6-flash가 400으로 즉시 탈락). 400 계열이면 일단 thinking 설정을 빼고 한 번 더
        # 시도하고, 그것이 통하면 이 모델은 이후 요청부터 아예 안 붙인다.
        if thinking_kwargs and ("thinking" in msg or "budget" in msg or is_invalid_argument(e)):
            thinking_kwargs = {}
            try:
                resp = _generate(thinking_kwargs)
                _GEMINI_NO_THINKING_CONFIG.add(model)
            except Exception as e2:
                if temperature is not None and is_invalid_argument(e2):
                    # 이 모델은 temperature까지 거부한다 (일부 신형 모델은 고정값만 허용)
                    config_kwargs.pop("temperature", None)
                    resp = _generate(thinking_kwargs)
                    _GEMINI_NO_THINKING_CONFIG.add(model)
                else:
                    raise
        elif temperature is not None and "temperature" in msg:
            config_kwargs.pop("temperature", None)
            resp = _generate(thinking_kwargs)
        else:
            raise

    text = getattr(resp, "text", None)
    if text:
        return text
    # candidates가 비었거나(safety 차단 등) .text가 없는 경우
    raise RuntimeError(f"Gemini 응답에 텍스트가 없습니다 ({_gemini_finish_info(resp)}). "
                       f"max_tokens를 늘리거나 배치 크기를 줄여보세요.")


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


def parse_model_json(raw: str) -> list[tuple[str, str]]:
    """
    모델 출력에서 {"translations":[...]} JSON을 관대하게 추출.
    반환값은 (segment_id, translated_text) 쌍의 리스트이며 모델이 출력한 순서를 그대로
    보존한다 - 호출측(reconcile_translations)이 "선언된 segment_id"뿐 아니라 "요청 보낸
    순서"까지 함께 대조해 검증할 수 있어야 한다. 특히 소형 로컬 모델은 텍스트 자체는
    올바른 순서로 뽑아내면서도 segment_id 문자열만 엉뚱하게(예: 인접한 다른 세그먼트의
    ID) 베끼는 경우가 실제로 확인됐다 - ID만 보고 그대로 믿으면 그 번역문이 전혀 다른
    위치(다른 bbox)의 세그먼트에 덮어써진다. 순서 정보를 유지해야 이런 경우를 순서
    기반으로 교정할 수 있다.
    """
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
            get_logger().log(f"    [로컬] 비정상 JSON 자동 복구: {len(items)}개 세그먼트 회수")
        else:
            try:
                data = json.loads(payload, strict=False)
            except Exception:
                preview = payload[:300].replace("\n", "\\n")
                raise ValueError(f"JSON 파싱 실패({e}). 추출된 부분(앞 300자): {preview!r}") from e
    out: list[tuple[str, str]] = []
    for item in data.get("translations", []):
        sid, txt = item.get("segment_id"), item.get("translated_text")
        if isinstance(sid, str) and isinstance(txt, str) and txt.strip():
            out.append((sid, txt))
    return out


_TARGET_SCRIPT_CHECKS: list[tuple[tuple[str, ...], "callable"]] = [
    (("korean", "한국어", "ko"), lambda c: "가" <= c <= "힣"),
    (("japanese", "일본어", "ja"), lambda c: ("぀" <= c <= "ヿ") or ("一" <= c <= "鿿")),
    (("chinese", "중국어", "zh", "chinese (simplified)", "chinese (traditional)"),
     lambda c: "一" <= c <= "鿿"),
    (("russian", "러시아어", "ru"), lambda c: "Ѐ" <= c <= "ӿ"),
]


def _target_script_fn(target_lang: str):
    tl = (target_lang or "").strip().lower()
    for names, fn in _TARGET_SCRIPT_CHECKS:
        if tl in names:
            return fn
    return None


def _is_untranslated_echo(source_text: str, translated_text: str, target_lang: str) -> bool:
    """
    모델이 번역을 시도하지 않고 원문을 그대로 돌려준(=사실상 미번역) 응답인지 판정한다.

    실제로 확인된 문제: 의미 없는 더미 텍스트(예: Lorem Ipsum 채움 텍스트)를 소형
    로컬 모델에 보내면, 오류 없이 "성공"으로 응답하면서도 원문을 그대로 복사해
    돌려주는 경우가 있었다. 기존 코드는 이걸 정상 번역 성공으로 간주해 (1) 그대로
    렌더링하고 (2) 디스크 캐시에 "이 원문 -> (원문과 동일한) 번역문"으로 영구
    저장했다 - 캐시에 한 번 이렇게 저장되면, 이후 실제로 번역이 될 수 있는 상황에서도
    캐시가 먼저 히트되어 영원히 미번역 상태로 고정되는 문제가 있었다. 대상 언어가
    한글/일본어/중국어/러시아어처럼 원문과 문자 체계가 확실히 다른 경우, 충분히 긴
    번역 결과에 그 언어 고유 문자가 "단 하나도" 없으면 실제로 번역을 시도하지 않은
    것으로 보고 거부한다(적용도, 캐시 저장도 하지 않음 - 재요청 루프로 넘어가고,
    끝까지 실패하면 최소한 원문 유지 상태가 "번역 실패"로 정직하게 기록된다).
    """
    fn = _target_script_fn(target_lang)
    if fn is None:
        return False
    tr = translated_text.strip()
    if len(tr) < 15:
        return False
    src_letters = sum(1 for c in source_text if c.isalpha())
    if src_letters < 8:
        return False
    return not any(fn(c) for c in tr)


def _looks_plausible(source_text: str, translated_text: str) -> bool:
    """
    (원문, 번역문) 쌍이 서로 형태적으로 맞는 짝인지 대략적으로 검사한다.

    실제로 확인된 문제: ID와 순서가 둘 다 정확해도, 소형 로컬 모델이 짧은 화자 라벨
    ("EMMA:")의 번역문 자리에 옆 문단 전체를, 문단 자리에 라벨 하나만 채워넣는
    경우가 있었다(모델이 "무엇을 어디에 넣을지"는 맞혔지만 "내용 자체"를 혼동한
    경우 - ID/순서 검증만으로는 못 잡는다). 완벽한 검증은 불가능하지만, 원문이
    짧은 라벨류인데 번역문이 문장 부호가 있는 긴 글이거나, 원문이 긴 문단인데
    번역문이 라벨처럼 짧으면 명백히 잘못 짝지어진 것으로 보고 거부한다. 거부된
    항목은 적용하지 않고 그대로 두어 호출측의 기존 재요청 루프가 다시 받아오게
    한다(잘못된 값을 그대로 쓰는 것보다 안전).
    """
    src, tr = source_text.strip(), translated_text.strip()
    if not src or not tr:
        return False
    src_is_label = is_label_like(src)
    tr_is_label = len(tr) <= 15 and not any(p in tr for p in ".!?…")
    if src_is_label and not tr_is_label and len(tr) > len(src) * 5:
        return False
    if not src_is_label and len(src) > 60 and tr_is_label:
        return False
    return True


def reconcile_translations(pairs: list[tuple[str, str]], todo: list,
                           target_lang: str = "") -> dict[str, str]:
    """
    모델이 선언한 segment_id와, 우리가 보낸 순서(todo)를 함께 대조해 실제로 적용할
    seg_id -> translated_text 매핑을 만든다.

    실제 확인된 문제: 소형 로컬 모델이 응답의 "순서"는 우리가 보낸 순서와 동일하게
    유지하면서도, 개별 항목의 segment_id 문자열만 인접한 다른 세그먼트의 것으로 잘못
    베껴 쓰는 경우가 있었다(예: 짧은 화자 라벨 "EMMA:"와 그 다음 문단을 혼동). ID만
    보고 그대로 신뢰하면(과거 동작) 그 번역문이 완전히 다른 위치(다른 bbox)의
    세그먼트에 잘못 삽입된다.

    전략: 모델이 반환한 항목 수가 우리가 보낸 세그먼트 수와 같고, 응답의 segment_id
    "순서"가 요청 순서와 정확히 일치하면(정상적인 모델 응답의 대다수 - ID도 맞고
    순서도 맞음) 그대로 사용한다. 순서가 요청 순서와 다르지만 개수는 같다면 - ID를
    신뢰할 수 없다는 강한 신호이므로 - ID 문자열을 무시하고 "위치"로 재배정한다(모델이
    텍스트 자체는 우리가 보낸 순서로 뽑아냈다는 가정이 ID 필드보다 훨씬 신뢰할 만하다,
    시스템 프롬프트가 "same order"를 명시적으로 요구하기 때문). 개수가 다르면(일부
    세그먼트를 모델이 통째로 누락/병합) 그 경우엔 위치 대응이 무의미하므로, 선언된
    ID가 우리가 보낸 세그먼트 집합에 실제로 존재하는 것만 골라 기존 방식대로 적용한다
    (완전히 틀린 매핑을 새로 만들기보다는, 누락된 나머지는 다음 재요청 루프가 다시
    요청하도록 비워 둔다).
    """
    if not pairs:
        return {}
    text_by_id = {s.seg_id: s.text for s in todo}
    expected_ids = list(text_by_id.keys())
    expected_set = set(expected_ids)
    returned_ids = [sid for sid, _ in pairs]
    if len(pairs) == len(expected_ids):
        if returned_ids == expected_ids:
            candidate = dict(pairs)
        else:
            # 개수는 맞는데 선언된 ID의 순서/배치가 요청과 다름 -> ID 문자열을 신뢰할 수
            # 없다는 신호이므로 버리고, "우리가 보낸 순서 = 모델이 답한 순서"라는 더
            # 신뢰할 수 있는 가정으로 위치 기반 재배정한다.
            candidate = {expected_ids[i]: txt for i, (_sid, txt) in enumerate(pairs)}
    else:
        candidate = {sid: txt for sid, txt in pairs if sid in expected_set}
    return {sid: txt for sid, txt in candidate.items()
            if _looks_plausible(text_by_id[sid], txt)
            and not _is_untranslated_echo(text_by_id[sid], txt, target_lang)}


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


def is_server_overload(e: Exception) -> bool:
    """
    서버 과부하/일시 장애(503 UNAVAILABLE, 500, 502, 504, overloaded 등)인지 판별.

    실제 확인된 문제: Gemini의 503("This model is currently experiencing high demand")은
    지금까지 '일반 오류'로 분류돼 max_attempts(기본 3)를 소비하며 같은 모델을 계속
    때렸다. 게다가 일반 오류의 쿨다운은 2~15초라서 곧바로 부활 -> 두 키의 1순위 모델
    사이만 왕복하다가 배치를 통째로 포기했다(로그의 batch 3: 25세그먼트가 그대로 원문
    유지됨). 과부하는 '그 모델이 지금 붐빈다'는 뜻이지 요청이 잘못된 게 아니므로,
    재시도 횟수를 소비하지 말고 그 모델만 넉넉히 쿨다운시킨 뒤 다른 모델/키로 내려가야
    한다. 같은 순간에 3.6/3.5/3-flash는 멀쩡히 놀고 있었다.
    """
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code in (500, 502, 503, 504):
        return True
    s = str(e).lower()
    return any(kw in s for kw in (
        "unavailable", "overloaded", "high demand", "service_unavailable",
        "503", "502", "504", "internal error", "internal server error",
    ))


def is_invalid_argument(e: Exception) -> bool:
    """
    400 INVALID_ARGUMENT 계열. 같은 요청을 그대로 다시 보내면 100% 또 실패하므로
    (모델이 그 설정/파라미터를 지원하지 않는다는 뜻) 재시도 대신 설정을 빼고 한 번
    더 시도하거나, 그래도 안 되면 그 모델을 이번 실행에서 제외해야 한다.
    """
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code == 400:
        return True
    s = str(e).lower()
    return "invalid_argument" in s or "invalid argument" in s


def is_auth_error(e: Exception) -> bool:
    """
    키 자체가 잘못됐거나 차단된 '진짜 영구' 오류 (시간이 지나도 절대 안 풀림).
    이 키는 revive 대상에서 제외한다.
    """
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code in (401, 403):
        return True
    # 실제 확인된 문제: Gemini 무료 티어의 분당 제한(429) 메시지가
    #   "You exceeded your current quota, please check your plan and billing details..."
    # 라서 아래 'billing' 키워드에 걸려 '영구 인증 오류'로 잘못 분류됐다. 그 결과
    # 잠깐 기다렸다 다시 쓰면 되는 429 한 번에 그 키가 이번 실행에서 통째로 제외되고,
    # 키가 하나뿐이면 곧바로 로컬 NPU 폴백으로 떨어졌다. 429 계열이면 인증 오류가 아니다.
    if code == 429 or is_rate_limit_error(e):
        return False
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


def is_model_not_found(e: Exception) -> bool:
    """
    '그 모델이 이 계정/이 API 버전에는 없다'는 오류인지 판별 (404, model not found 등).
    모델 폴백 체인에는 계정마다 제공 여부가 다른 모델이 섞일 수 있다. 이런 오류는
    재시도해도 절대 안 풀리지만 '키'의 문제도 아니므로, 그 모델 항목 하나만 조용히
    빼고 다음 순위 모델로 넘어가야 한다 (안 그러면 배치마다 없는 모델을 계속 때린다).
    """
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    s = str(e).lower()
    if code == 404:
        return True
    return any(kw in s for kw in (
        "not_found", "not found",
        "does not exist", "is not supported", "unsupported model",
        "unknown model", "invalid model", "model_not_found",
        "no such model",
    )) and ("model" in s or code == 404)


def is_quota_exhaustion(e: Exception) -> bool:
    """
    할당량 소진 계열 (일일 한도 등). 지금은 못 쓰지만 리셋 시간이 지나면
    다시 쓸 수 있으므로, revive_at을 설정해 나중에 자동 복귀시킨다.
    """
    s = str(e).lower().replace(" ", "")
    return any(kw in s for kw in (
        "perday",                       # Gemini: GenerateRequestsPerDayPerProjectPerModel-FreeTier 등
        "requestsperday",
        "insufficient_quota",           # OpenAI: 크레딧/결제 한도 소진 (충전 시 풀리므로 재확인 가치 있음)
        "quotaexceeded", "quota_exceeded",
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