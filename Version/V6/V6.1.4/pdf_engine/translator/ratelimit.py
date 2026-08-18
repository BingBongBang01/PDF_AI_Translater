# -*- coding: utf-8 -*-
"""
pdf_engine/translator/ratelimit.py — API 키·모델별 사용량(RPM/RPD) 장부.

무료 티어(특히 Gemini)는 한도를 '모델별 × 프로젝트(키)별'로 따로 센다.
  예) Gemini 무료: 모델 하나당 5 RPM / 20 RPD  -> 키 2개 × 모델 8개면 이론상 320 RPD

그런데 엔진이 사용량을 전혀 기억하지 않으면 매 실행이 항상 1순위 모델부터 다시
때리게 되고, 그 모델의 RPD 20을 다 쓴 뒤에야(=429를 맞은 뒤에야) 다음 모델로
내려간다. 실제로 사용자의 콘솔 통계에서 1순위 모델만 12/20, 11/20까지 올라가고
나머지 모델은 0~5/20로 남아 있던 것이 이 때문이다.

이 모듈은 (키 지문 + 모델)별로
  - RPM: 최근 요청 시각 목록 (60초 창)
  - RPD: 오늘 성공한 요청 수
를 디스크에 남겨, 다음 실행에서도 "이 모델은 오늘 몇 번 썼는지"를 알고 시작하게 한다.
스케줄러는 이 값을 보고 한도에 닿기 '전에' 다른 모델/키로 미리 분산한다.

장부는 어디까지나 최적화용 보조 정보다. 파일이 없거나 깨졌거나 값이 실제와 달라도
번역 자체는 그대로 동작한다(모든 항목이 장부상 소진이면 장부를 무시하고 시도한다).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CACHE_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "PDFTranslaterGUI" / "cache"
_LEDGER_PATH = _CACHE_DIR / "api_usage.json"

# provider별 기본 한도(무료 티어 기준). 값이 없으면 '한도 모름' = 제한 없이 취급한다.
# 유료 티어를 쓰면 --api-rpm/--api-rpd로 덮어쓸 수 있다.
DEFAULT_RPM = {"gemini": 5}
DEFAULT_RPD = {"gemini": 20}

_RPM_WINDOW = 60.0


def key_fingerprint(key: str) -> str:
    """장부 파일에 원본 API 키를 남기지 않기 위한 짧은 해시."""
    return hashlib.sha256((key or "").encode("utf-8", "ignore")).hexdigest()[:10]


def limits_for(provider: str, args=None) -> tuple[int | None, int | None]:
    """(rpm, rpd) 한도를 돌려준다. --api-rpm/--api-rpd가 있으면 그 값이 우선."""
    rpm = DEFAULT_RPM.get(provider)
    rpd = DEFAULT_RPD.get(provider)
    if args is not None:
        ov_rpm = getattr(args, "api_rpm", 0) or 0
        ov_rpd = getattr(args, "api_rpd", 0) or 0
        if ov_rpm > 0:
            rpm = ov_rpm
        elif ov_rpm < 0:
            rpm = None      # 음수 = 한도 없음으로 강제
        if ov_rpd > 0:
            rpd = ov_rpd
        elif ov_rpd < 0:
            rpd = None
    return rpm, rpd


def quota_reset_date(now: float | None = None) -> str:
    """
    일일 한도의 기준 날짜(문자열). 무료 티어 RPD는 태평양 시간 자정에 리셋된다.
    서머타임까지 정확히 따지지 않고 UTC-8로 고정해도, 실제 리셋 시각(UTC-7 또는 -8)보다
    같거나 늦게 날짜가 바뀌므로 '아직 남았는데 소진으로 본다'는 안전한 방향으로만 틀린다.
    """
    ts = now if now is not None else time.time()
    return (datetime.fromtimestamp(ts, timezone.utc)
            .astimezone(timezone(timedelta(hours=-8)))
            .strftime("%Y-%m-%d"))


class UsageLedger:
    """(키 지문|모델) -> {"rpd": 오늘 성공 요청 수, "recent": [최근 요청 epoch...]}"""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or _LEDGER_PATH)
        self._lock = threading.Lock()
        self._data: dict = {"date": quota_reset_date(), "entries": {}}
        self._load()

    # -- 내부 -----------------------------------------------------------------
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("date") == quota_reset_date():
                entries = raw.get("entries")
                if isinstance(entries, dict):
                    self._data = {"date": raw["date"], "entries": entries}
        except Exception:
            pass  # 없거나 깨진 장부는 무시하고 새로 시작 (보조 정보이므로 치명적이지 않다)

    def _slot(self, key_id: str, model: str) -> dict:
        today = quota_reset_date()
        if self._data.get("date") != today:
            # 날이 바뀌었다 = 무료 티어 일일 한도 리셋
            self._data = {"date": today, "entries": {}}
        return self._data["entries"].setdefault(f"{key_id}|{model}", {"rpd": 0, "recent": []})

    def _trim(self, slot: dict, now: float) -> list[float]:
        recent = [t for t in slot.get("recent", []) if now - t < _RPM_WINDOW * 2]
        slot["recent"] = recent
        return recent

    # -- 기록 -----------------------------------------------------------------
    def note_request(self, key_id: str, model: str, now: float | None = None) -> None:
        """요청을 '보낸' 시점 기록 (RPM 창 계산용). 실패하더라도 분당 창은 소비된 것으로 본다."""
        now = now if now is not None else time.time()
        with self._lock:
            slot = self._slot(key_id, model)
            self._trim(slot, now).append(now)

    def note_success(self, key_id: str, model: str) -> None:
        """서버가 실제로 처리해 준 요청만 RPD로 센다(503/타임아웃은 세지 않음)."""
        with self._lock:
            slot = self._slot(key_id, model)
            slot["rpd"] = int(slot.get("rpd", 0)) + 1
        self.save()

    def mark_daily_exhausted(self, key_id: str, model: str, limit: int | None) -> None:
        """429 'PerDay' 응답을 받으면 장부를 실제 상태(=소진)에 맞춰 올려 둔다."""
        with self._lock:
            slot = self._slot(key_id, model)
            slot["rpd"] = max(int(slot.get("rpd", 0)), int(limit or 0) or 10 ** 6)
        self.save()

    # -- 조회 -----------------------------------------------------------------
    def used_today(self, key_id: str, model: str) -> int:
        with self._lock:
            return int(self._slot(key_id, model).get("rpd", 0))

    def rpm_wait(self, key_id: str, model: str, rpm_limit: int | None,
                 now: float | None = None) -> float:
        """
        분당 한도까지 찼으면 '몇 초 뒤에 한 칸이 비는지'를 돌려준다(여유 있으면 0).
        429를 맞고 나서 대응하는 대신, 맞기 전에 다른 모델/키로 돌리기 위한 값이다.
        """
        if not rpm_limit or rpm_limit <= 0:
            return 0.0
        now = now if now is not None else time.time()
        with self._lock:
            slot = self._slot(key_id, model)
            recent = sorted(t for t in self._trim(slot, now) if now - t < _RPM_WINDOW)
        if len(recent) < rpm_limit:
            return 0.0
        oldest_blocking = recent[len(recent) - rpm_limit]
        return max(0.0, _RPM_WINDOW - (now - oldest_blocking) + 0.5)

    # -- 저장 -----------------------------------------------------------------
    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = json.dumps(self._data, ensure_ascii=False)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            pass  # 장부 저장 실패가 번역을 막아서는 안 된다


GLOBAL_LEDGER = UsageLedger()
