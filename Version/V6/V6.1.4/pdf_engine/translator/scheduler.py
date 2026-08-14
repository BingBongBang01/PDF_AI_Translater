"""
번역 오케스트레이션: 세그먼트를 배치로 나눠 API 키 풀/로컬 런타임에 분배하고,
실패/할당량 소진 시 다음 키로 전환하거나 로컬 폴백으로 넘어가는 전체 흐름을 담당한다.
"""
from __future__ import annotations
from pdf_engine.logger import get_logger


import json
import re
import threading
import time

from pdf_engine.translator.cache import GLOBAL_CACHE
from pdf_engine.config.settings import STOP_EVENT, model_recipe_device, resolve_local_model_for_device
from pdf_engine.placeholder.segment import Segment
from pdf_engine.placeholder.batching import make_batches, render_prev_context, build_user_prompt
from .providers_cloud import (
    KeyEntry, call_llm, parse_model_json, reconcile_translations,
    is_rate_limit_error, is_auth_error, is_quota_exhaustion, is_permanent_exhaustion,
    is_model_not_found, is_server_overload, extract_retry_delay, _is_context_or_400_error,
)
from .ratelimit import GLOBAL_LEDGER
from .providers_local import ensure_local_runtime, local_presets_for


class _Heartbeat:
    """
    API 응답을 기다리는 동안 일정 간격으로 '아직 진행 중'임을 로그로 알린다.

    RPD(일일 요청 수) 한도를 아끼려고 배치를 일부러 크게 잡은 Gemini 모델은 응답에
    수십 초~몇 분이 걸릴 수 있는데, 그동안 로그가 한 줄도 안 나오면 멈춘 것처럼
    보인다(실제로 사용자가 겪은 "진행바가 갑자기 확 오른다" 체감의 큰 원인 - 로그가
    조용한 동안에는 진행바도 그대로였다가, 응답이 오는 순간에만 한 번에 갱신됨).
    실제 API 호출은 여전히 동기 호출이라 응답 내용 자체를 중간에 알 방법은 없지만,
    '아직 기다리는 중'이라는 사실만 주기적으로 보여줘도 체감 대기가 크게 줄어든다.
    스레드 하나만 쓰고 응답이 오는 즉시 멈추므로 실제 처리 성능에는 영향이 없다
    (교체 비용은 무시할 수준 - time.sleep 대기만 하는 데몬 스레드 하나).
    """
    def __init__(self, message_fn, interval: float = 12.0):
        self._message_fn = message_fn
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self):
        while not self._stop.wait(self._interval):
            get_logger().log(self._message_fn())

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
        return False

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
            result.update(reconcile_translations(parse_model_json(raw), chunk,
                                                 getattr(args, "target_lang", "")))
        except Exception as e:
            if _is_context_or_400_error(e) and len(chunk) > 1 and depth < 4:
                mid = len(chunk) // 2
                get_logger().log(f"    [로컬] 청크 오류({str(e)[:80]}) -> {len(chunk)}세그먼트를 "
                      f"반으로 쪼개 재시도")
                run_chunk(chunk[:mid], depth + 1)
                run_chunk(chunk[mid:], depth + 1)
            elif len(chunk) == 1:
                get_logger().log(f"    [로컬] 세그먼트 {chunk[0].seg_id} 번역 실패(원문 유지 예정): "
                      f"{str(e)[:120]}")
                given_up.add(chunk[0].seg_id)
            else:
                raise  # 컨텍스트류가 아닌 오류는 상위 재시도 로직에 위임

    total = len(chunks)
    for ci, chunk in enumerate(chunks, 1):
        if STOP_EVENT.is_set():
            get_logger().log(f"    [로컬] 사용자 중단 요청 -> 남은 {total - ci + 1}개 청크 건너뜀")
            break
        if total > 1:
            get_logger().log(f"    [로컬] 청크 {ci}/{total} ({len(chunk)}세그먼트) 처리 중...")
        run_chunk(chunk)
    return result, given_up


def translate_all_batches(pool: list["KeyEntry"], args, system_prompt: str, template: str,
                          segments: list[Segment], glossary_text: str,
                          system_prompt_local: str | None = None,
                          pbar_callback: "Callable | None" = None) -> bool:
    """
    반환값: aborted (pool의 모든 키가 영구 소진되어 나머지 배치를 건너뛰고 중단했는지 여부).
    어떤 이유로든(할당량 소진, 일반 오류, JSON 파싱 실패 등) 결국 원문으로 남은 세그먼트는
    s.translation_failed=True로 표시되며, 이는 main()에서 페이지 단위로 집계해
    출력 파일명의 미번역 구간을 만드는 데 쓰인다.
    로컬 NPU 엔트리는 컨텍스트가 짧고 소형 모델이라 system_prompt_local(축약판, 없으면
    system_prompt와 동일)을 사용한다.
    """
    system_prompt_local = system_prompt_local or system_prompt
    
    # [최적화] 디스크 캐시 사전 검수
    cache_hits = 0
    src_lang = getattr(args, "source_lang", "English")
    tgt_lang = getattr(args, "target_lang", "Korean")
    for s in segments:
        if s.needs_translation:
            cached = GLOBAL_CACHE.get(s.text, src_lang, tgt_lang, glossary_text)
            if cached:
                s.translated = cached
                cache_hits += 1

    if cache_hits > 0:
        get_logger().log(f"  [캐시 힛] 총 {len(segments)}개 세그먼트 중 {cache_hits}개 세그먼트를 디스크 캐시에서 복원했습니다.")

    targets = [s for s in segments if s.needs_translation]
    batches = list(make_batches(targets, args.batch_chars, args.batch_segs))
    prev_pairs: list[tuple[str, str]] = []
    total_chars_sent = 0
    last_call_time = 0.0
    n_keys = len(pool)
    key_idx = 0  # 배치 간에도 유지
    local_started = {"done": False, "presets": None}  # 로컬 서버를 아직 안 깨웠으면 done=False

    # ------------------------------------------------------------------
    # 분산 정책
    #   balanced(기본): 상위 spread개 모델을 '동급'으로 보고 키·모델에 고르게 나눠 쓴다.
    #   quality:        예전처럼 1순위 모델만 쓰고, 막히면 그때 아래로 내려간다.
    # 무료 티어의 한도(RPM/RPD)는 모델별·키별로 따로 세므로, 고르게 나눠 쓰면
    # 같은 시간에 쓸 수 있는 요청 수가 (키 수 × 모델 수)배로 늘어난다.
    # ------------------------------------------------------------------
    balance_mode = str(getattr(args, "api_balance", "balanced") or "balanced").lower()
    if balance_mode not in ("balanced", "quality"):
        balance_mode = "balanced"
    spread = max(1, int(getattr(args, "api_spread", 4) or 4))
    overload_cooldown = float(getattr(args, "api_overload_cooldown", 45.0) or 45.0)
    cloud_paths = sum(1 for e in pool if not e.is_local)
    ignore_ledger = {"on": False}  # 장부상 전부 소진이면 장부를 무시하고라도 시도한다
    if cloud_paths > 1:
        if balance_mode == "balanced":
            top = sorted({e.priority for e in pool if not e.is_local})[:spread]
            n_top = sum(1 for e in pool if not e.is_local and e.priority in top)
            get_logger().log(f"  [분산] balanced 모드: 상위 {len(top)}개 모델 × 키 = {n_top}개 경로를 "
                             f"고르게 사용 (오늘 덜 쓴 모델부터). 나머지는 예비로 대기")
        else:
            get_logger().log("  [분산] quality 모드: 1순위 모델을 우선 사용하고 막힐 때만 하위 모델로 전환")

    def _group(e: "KeyEntry") -> int:
        """같은 그룹 안에서는 서로 동급으로 보고 고르게 나눠 쓴다."""
        return e.priority if balance_mode == "quality" else e.priority // spread

    def _daily_left(e: "KeyEntry") -> int | None:
        if not e.rpd_limit:
            return None
        return e.rpd_limit - GLOBAL_LEDGER.used_today(e.key_id, e.model)

    def _pick_cloud(cloud: list[int]) -> tuple[int | None, float]:
        """
        클라우드 후보 중 하나를 고른다. 반환: (인덱스, 인덱스가 없을 때 기다리면 되는 초).

        고르는 기준(앞에서부터 우선):
          그룹 -> 오늘 사용 비율(4단계) -> 이번 실행 사용 횟수 -> 그 키의 총 사용 횟수
          -> 모델 순위 -> 마지막 사용 시각(LRU)
        '오늘 사용 비율'을 먼저 보기 때문에, 어제/오늘 이미 많이 쓴 모델은 자동으로
        뒤로 밀리고 손대지 않은 모델부터 쓰인다.
        """
        key_calls: dict[str, int] = {}
        for e in pool:
            if not e.is_local:
                key_calls[e.key_id] = key_calls.get(e.key_id, 0) + e.calls

        usable: list[int] = []
        waiting: list[tuple[float, int]] = []
        over_quota: list[int] = []
        for i in cloud:
            e = pool[i]
            left = _daily_left(e)
            if left is not None and left <= 0 and not ignore_ledger["on"]:
                over_quota.append(i)
                continue
            w = GLOBAL_LEDGER.rpm_wait(e.key_id, e.model, e.rpm_limit)
            if w <= 0:
                usable.append(i)
            else:
                waiting.append((w, i))

        if not usable and not waiting and over_quota:
            # 장부가 실제와 다를 수 있다(유료 티어로 올렸거나, 다른 기기에서 쓴 기록 등).
            # 쓸 수 있는 게 정말 하나도 없으면 장부를 무시하고 일단 보내 본다 -
            # 진짜 소진이면 429가 오고 그때 정식으로 처리된다.
            ignore_ledger["on"] = True
            get_logger().log("  [분산] 장부상 모든 모델이 오늘 한도 소진 -> 장부를 무시하고 실제로 시도해 봅니다")
            return _pick_cloud(cloud)
        if not usable:
            return None, (min(w for w, _ in waiting) if waiting else 0.0)

        def _score(i: int):
            e = pool[i]
            load = 0
            if e.rpd_limit:
                load = int(4 * GLOBAL_LEDGER.used_today(e.key_id, e.model) / e.rpd_limit)
            return (_group(e), load, e.calls, key_calls.get(e.key_id, 0), e.priority, e.last_used)

        return min(usable, key=_score), 0.0

    def _sleep_until(end: float) -> bool:
        """중단 요청이 오면 즉시 False."""
        while time.monotonic() < end:
            if STOP_EVENT.is_set():
                return False
            time.sleep(min(1.0, max(end - time.monotonic(), 0.05)))
        return True

    def next_alive_index(start: int = 0) -> int | None:
        """
        다음에 사용할 항목을 고른다. 선택 규칙:
          1) 클라우드를 항상 로컬보다 우선 (로컬 NPU는 클라우드가 전부 죽은 최후의 폴백)
          2) 클라우드 안에서는 _pick_cloud의 기준(그룹 -> 오늘 사용량 -> 이번 실행
             사용량 -> 키 부하 -> 모델 순위 -> LRU)으로 고른다.

             예전에는 '살아있는 것 중 priority가 가장 낮은(=1순위) 항목'을 무조건 골랐다.
             그래서 1순위 모델이 죽지 않는 한 2순위 이하는 영영 안 쓰였고, 게다가 start를
             자기 자신으로 넘겨받아 같은 항목을 계속 재사용했다(끈적한 선택). 실제 로그에서
             gemini-3.7-flash만 두 키 모두 한도 근처(12/20, 11/20)까지 쓰이고 나머지 7개
             모델은 0~5/20으로 남아 있던 것이 이 조합 때문이다.
          3) RPM/RPD는 429를 맞고 대응하는 대신 장부로 미리 피한다. 분당 한도가 찬
             항목은 후보에서 잠시 빼고, 오늘 한도를 다 쓴 항목은 아예 제외한다.
        쿨다운/할당량 소진으로 죽었던 항목은 revive_at(서버가 알려준 리셋 시각)이 지나면
        자동 부활한다 -> 하위 모델이나 로컬 NPU로 작업 중이어도 1순위 모델이 풀리면 복귀.
        """
        for _ in range(64):  # 안전장치: '대기 후 재평가'를 무한히 반복하지 않는다
            now = time.monotonic()
            for e2 in pool:
                if not e2.alive and e2.revive_at is not None and now >= e2.revive_at:
                    e2.alive = True
                    e2.revive_at = None
                    get_logger().log(f"  [복귀] {e2.label} 대기 시간 경과 -> 다시 사용 대상으로 복귀")
            cloud = [i for i in range(n_keys) if pool[i].alive and not pool[i].is_local]
            local = [i for i in range(n_keys) if pool[i].alive and pool[i].is_local]
            if cloud:
                idx, wait = _pick_cloud(cloud)
                if idx is not None:
                    return idx
                if wait > 0:
                    # 분당 한도(RPM)가 찼을 뿐이다. 로컬로 내려가는 것보다 몇십 초 기다렸다
                    # 클라우드로 계속 가는 편이 대개 더 빠르고 품질도 좋다.
                    if wait <= 75 or not local:
                        get_logger().log(f"  [대기] 모든 클라우드 모델이 분당 한도(RPM)에 도달 "
                                         f"-> {wait:.0f}초 후 재개 "
                                         f"(유료 티어라 한도가 더 높다면 --api-rpm 으로 조정)")
                        if not _sleep_until(time.monotonic() + wait):
                            return None
                        continue
            # 클라우드가 전부 '잠깐' 쿨다운(429/과부하 등) 중일 뿐이라면, 느린 로컬 NPU로
            # 내려가지 말고 그 짧은 시간만 기다렸다가 클라우드로 계속 간다.
            cloud_soon = [e2.revive_at for e2 in pool
                          if not e2.alive and not e2.is_local and e2.revive_at is not None]
            if not cloud and cloud_soon:
                wait = min(cloud_soon) - time.monotonic()
                if 0 < wait <= 90:
                    get_logger().log(f"  [대기] 모든 클라우드 모델이 쿨다운 중 - {wait:.0f}초 후 복귀 예정이라 "
                                     f"대기합니다 (로컬 폴백보다 빠름)")
                    if not _sleep_until(time.monotonic() + wait):
                        return None
                    continue
            break

        local = [i for i in range(n_keys) if pool[i].alive and pool[i].is_local]
        # 클라우드가 전부 죽음 -> 로컬 사용 (필요 시 서버 기동)
        if local:
            if not local_started["done"]:
                had_cloud = any(not e.is_local for e in pool)
                reason = "클라우드 API 전부 소진" if had_cloud else "클라우드 API 키 없음"
                local_label = pool[local[0]].label
                get_logger().log(f"  [폴백] {reason} -> {local_label}(으)로 전환 시도")
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
            get_logger().log(f"  [대기 포기] 가장 빠른 할당량 리셋까지 {wait/60:.0f}분 남음 (10분 초과) -> 중단")
            return None
        if wait > 0:
            get_logger().log(f"  [대기] 번역 수단 없음. 할당량 리셋까지 {wait:.0f}초 대기...")
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

    def _emit_progress(bi_local: int) -> float:
        """
        GUI 진행바/상태 텍스트가 파싱하는 구조화 로그 라인을 찍는다.

        pct는 예전처럼 '배치 번호 / 전체 배치 수'가 아니라 '실제로 처리(번역 성공 또는
        원문 유지로 확정)된 세그먼트 수 / 전체 대상 세그먼트 수'로 계산한다. RPD(일일
        요청 수)를 아끼려고 배치를 일부러 크게 잡은 모델(예: Gemini 표준 Flash)에서는
        배치 하나의 세그먼트 수가 서로 크게 달라서, 배치 번호 기준 pct는 "배치 4개 중
        1개 끝났으니 25%"처럼 실제 작업량과 안 맞는 계단식으로 튀었다. 세그먼트 수
        기준으로 바꾸면 배치 크기와 무관하게 진행률이 실제 작업량에 비례해서 매끄럽게
        올라간다. 또한 이 함수를 배치 하나가 끝날 때뿐 아니라 재요청(누락분 재시도) 등
        배치 도중에도 호출해, 배치 하나가 여러 번 요청을 거치는 동안에도 진행바가
        중간중간 갱신되게 한다(예전엔 배치가 끝나야만 갱신됨 -> 크고 오래 걸리는
        배치일수록 진행바가 오래 멈춰 있다가 한 번에 확 올라가는 것처럼 보였다).
        """
        resolved = sum(1 for s in targets if s.translated is not None)
        pct = 100.0 * resolved / max(len(targets), 1)
        get_logger().log(f"  [진행] batch={bi_local}/{len(batches)} segs={resolved}/{len(targets)} "
              f"pages={len(pages_done)}/{total_pages} pct={pct:.1f}")
        if pbar_callback is not None:
            pbar_callback(bi_local, len(batches), pct)
        return pct

    for bi, batch in enumerate(batches, 1):
        if STOP_EVENT.is_set():
            stopped_by_user = True
            first_left = min(s.page for s in batch) + 1
            get_logger().log(f"  [중단] 사용자 요청 -> {bi}번째 배치({first_left}페이지)부터 원문 유지하고 저장 진행")
            break
        remaining = {s.seg_id: s for s in batch}
        attempt = 0
        rl_retry = 0
        overload_retry = 0
        keys_tried_since_success = 0
        no_progress = 0  # 성공 응답인데 remaining이 줄지 않은 연속 횟수 (모델의 세그먼트 누락 반복 감지)
        batch_t0 = time.monotonic()
        # 하드 실패 허용 횟수: 예전엔 max_attempts(기본 3)를 배치 전체가 공유해서, 서로
        # 다른 모델로 3번 실패하면 남은 모델을 하나도 안 써 보고 배치를 통째로 포기했다
        # (실제 로그의 batch 3: 25개 세그먼트가 그대로 원문 유지). 이제는 최소한 살아있는
        # 경로 수(최대 8개)만큼은 서로 다른 모델로 시도해 본다.
        attempt_cap = max(int(getattr(args, "max_attempts", 3) or 3), min(cloud_paths, 8))
        # 다만 무한정 끌 수는 없으므로 배치당 시간 상한도 둔다 (타임아웃 × 4, 최소 10분).
        batch_time_budget = max(600.0, float(getattr(args, "api_timeout", 180.0) or 180.0) * 4)
        while remaining:
            if STOP_EVENT.is_set():
                stopped_by_user = True
                get_logger().log(f"  [중단] 사용자 요청 -> 현재 배치의 남은 {len(remaining)}개 세그먼트는 "
                      f"원문 유지하고 저장 진행")
                break
            if time.monotonic() - batch_t0 > batch_time_budget:
                get_logger().log(f"  [batch {bi}/{len(batches)}] 이 배치에 "
                      f"{batch_time_budget/60:.0f}분 이상 소요 -> 남은 {len(remaining)}개는 "
                      f"원문 유지하고 다음 배치로")
                break
            idx = next_alive_index(key_idx)
            if idx is None:
                aborted = True
                abort_page = min(s.page for s in remaining.values()) + 1
                get_logger().log(f"  [batch {bi}/{len(batches)}] 사용 가능한 번역 수단이 없음 "
                      f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                break
            key_idx = idx
            entry = pool[key_idx]

            todo = list(remaining.values())
            todo_chars = sum(len(s.text) for s in todo)
            prompt = build_user_prompt(template, args, glossary_text,
                                       render_prev_context(prev_pairs), todo)

            if args.min_interval > 0:
                wait = args.min_interval - (time.monotonic() - last_call_time)
                if wait > 0:
                    time.sleep(wait)

            # 요청을 보내는 시점에 바로 로그를 남긴다 - 응답이 몇십 초~몇 분 걸려도
            # "지금 뭘 하고 있는지"가 화면에 즉시 보이게 하기 위함 (예전엔 성공/실패
            # 결과가 나온 뒤에야 로그가 찍혀서, 그 사이엔 화면이 그대로 멈춰 보였다).
            req_t0 = time.monotonic()
            # 사용량 장부에 '보냈다'는 사실을 먼저 남긴다 - 분당 한도(RPM) 계산은 응답
            # 성공 여부와 무관하게 요청 시점 기준이기 때문이다. 일일 한도(RPD)는 서버가
            # 실제로 처리해 준 요청만 세야 하므로 성공했을 때만 올린다.
            entry.calls += 1
            entry.last_used = time.monotonic()
            if not entry.is_local:
                GLOBAL_LEDGER.note_request(entry.key_id, entry.model)
            get_logger().log(f"  [batch {bi}/{len(batches)}] {entry.label}로 {len(todo)}개 세그먼트 "
                  f"({todo_chars:,}자) 요청 전송...")

            try:
                if entry.is_local:
                    # 로컬 NPU: 양자화 프리셋에 맞춰 작은 청크로 나눠 처리
                    # (소형 모델 컨텍스트/품질 한계 -> 실패 파장 축소, 청크마다 이미
                    # translate_local_chunked 내부에서 진행 로그를 찍으므로 별도 하트비트는
                    # 불필요하다)
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
                    # 클라우드 호출은 배치가 크면(RPD를 아끼려 일부러 크게 잡은 Gemini
                    # 모델 등) 응답에 분 단위가 걸릴 수 있다 - 하트비트로 "아직 대기
                    # 중"임을 주기적으로 알려 화면이 멈춘 것처럼 보이지 않게 한다.
                    with _Heartbeat(lambda: f"  [batch {bi}/{len(batches)}] {entry.label} "
                                     f"응답 대기 중... ({time.monotonic() - req_t0:.0f}초 경과)"):
                        raw = call_llm(entry.provider, entry.client, entry.model,
                                      system_prompt, prompt,
                                      args.max_tokens, args.temperature)
                    mapping = reconcile_translations(parse_model_json(raw), todo,
                                                     getattr(args, "target_lang", ""))
                    GLOBAL_LEDGER.note_success(entry.key_id, entry.model)
                    left = _daily_left(entry)
                    get_logger().log(f"  [batch {bi}/{len(batches)}] {entry.label} 응답 수신 "
                          f"({time.monotonic() - req_t0:.1f}초) -> {len(mapping)}/{len(todo)}개 세그먼트 번역됨"
                          + (f" (오늘 남은 요청 {max(left, 0)}회)" if left is not None else ""))
                last_call_time = time.monotonic()
                keys_tried_since_success = 0
                overload_retry = 0
            except Exception as e:
                last_call_time = time.monotonic()
                if (not entry.is_local and is_server_overload(e)
                        and not is_rate_limit_error(e) and not is_model_not_found(e)):
                    # is_model_not_found를 먼저 걸러낸다: "이 모델은 이 지역에서 unavailable"
                    # 같은 문구는 과부하 키워드에 걸리지만 실제로는 아무리 기다려도 안 풀린다.
                    # 503/500 등 '모델이 지금 붐빈다'는 오류. 요청이 잘못된 게 아니므로
                    # 재시도 횟수를 깎지 말고, 그 모델만 넉넉히 쿨다운시켜 다른 모델/키로
                    # 즉시 내려간다. 예전엔 이것을 일반 오류로 보고 2~15초만 쿨다운시켜서,
                    # 두 키의 1순위 모델 사이만 왕복하다가 배치를 포기했다.
                    overload_retry += 1
                    if overload_retry > max(6, cloud_paths):
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 과부하(503)가 계속됨 "
                              f"({overload_retry}회) -> 일반 오류로 처리")
                    else:
                        delay = extract_retry_delay(e, default=overload_cooldown)
                        entry.alive = False
                        entry.revive_at = time.monotonic() + delay
                        nxt = next_alive_index(key_idx + 1)
                        if nxt is None:
                            aborted = True
                            abort_page = min(s.page for s in remaining.values()) + 1
                            get_logger().log(f"  [batch {bi}/{len(batches)}] 모든 모델이 과부하/대기 중 "
                                  f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                            break
                        get_logger().log(f"  [batch {bi}/{len(batches)}] {entry.label} 서버 과부하(503) "
                              f"-> {delay:.0f}초 쉬게 하고 {pool[nxt].label}(으)로 전환 "
                              f"(재시도 횟수 소모 안 함)")
                        key_idx = nxt
                        continue
                if not entry.is_local and is_model_not_found(e):
                    # 이 계정에 없는 모델(체인에 섞인 미지원 모델) -> 그 모델만 빼고 다음 순위로
                    entry.alive = False
                    entry.revive_at = None
                    get_logger().log(f"  [batch {bi}/{len(batches)}] {entry.label} 사용 불가 모델 "
                          f"-> 체인에서 제외하고 다음 모델로: {str(e)[:150]}")
                    nxt = next_alive_index(key_idx + 1)
                    if nxt is None:
                        aborted = True
                        abort_page = min(s.page for s in remaining.values()) + 1
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 사용 가능한 모델이 남지 않음 "
                              f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                        break
                    key_idx = nxt
                    continue
                if is_permanent_exhaustion(e):
                    # 인증/차단(진짜 영구) vs 할당량 소진(리셋 시간 지나면 부활 가능) 구분
                    entry.alive = False
                    if is_auth_error(e):
                        # 인증/권한/결제 오류는 '키' 자체의 문제라 그 키로 만든 모든 모델
                        # 항목이 똑같이 실패한다. 같은 클라이언트를 공유하는 항목을 한꺼번에
                        # 제외해야 8개 모델을 차례로 다 때려보는 헛수고를 막을 수 있다.
                        killed = 0
                        for e2 in pool:
                            if e2.client is entry.client and e2.alive:
                                e2.alive = False
                                e2.revive_at = None
                                killed += 1
                        entry.revive_at = None
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 키 {entry.label} 영구 오류(인증/권한/결제) "
                              f"-> 이 키의 모델 {killed + 1}개 전부 이번 실행에서 제외: {str(e)[:200]}")
                    else:
                        # 할당량 소진: 서버 제시 리셋 시간(없으면 30분) 후 자동 부활 예약
                        delay = extract_retry_delay(e, default=1800.0)
                        entry.revive_at = time.monotonic() + delay
                        if not entry.is_local and is_quota_exhaustion(e):
                            # 장부를 실제 상태에 맞춰 올려 둔다 -> 다음 실행에서 이 모델을
                            # 다시 1번 타자로 세우지 않는다(오늘 안에 재실행할 때 특히 중요).
                            GLOBAL_LEDGER.mark_daily_exhausted(entry.key_id, entry.model,
                                                               entry.rpd_limit)
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 키 {entry.label} 할당량 소진 "
                              f"-> {delay/60:.0f}분 후 자동 재시도 예약 (그동안 다른 키/NPU 사용)")
                    nxt = next_alive_index(key_idx + 1)
                    if nxt is None:
                        aborted = True
                        abort_page = min(s.page for s in remaining.values()) + 1
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 모든 키 소진 "
                              f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                        break
                    key_idx = nxt
                    continue
                if is_rate_limit_error(e):
                    # 일시적 429(분당 제한 등). 이 항목(키+모델 조합)만 잠깐 쿨다운시키고
                    # 다음 순위로 내려간다 - Gemini의 RPM/RPD는 모델별로 따로 세므로,
                    # 1순위 모델이 분당 한도에 걸렸어도 2순위 모델은 즉시 쓸 수 있다.
                    # 쿨다운이 끝나면 next_alive_index가 알아서 1순위로 되돌린다.
                    rl_retry += 1
                    if args.max_rate_limit_retries and rl_retry > args.max_rate_limit_retries:
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 일시적 할당량 재시도 한도 "
                              f"({args.max_rate_limit_retries}회) 초과 -> 이 배치 포기")
                        break
                    delay = extract_retry_delay(e, default=60.0)
                    entry.alive = False
                    entry.revive_at = time.monotonic() + delay
                    nxt = next_alive_index(key_idx + 1)
                    if nxt is None:
                        # 쓸 수 있는 게 하나도 안 남음 -> _wait_for_revival이 이미 대기까지
                        # 시도한 결과이므로 여기서 중단 (진행분은 원문 유지로 저장됨)
                        aborted = True
                        abort_page = min(s.page for s in remaining.values()) + 1
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 모든 모델/키가 할당량 대기 중 "
                              f"-> {abort_page}페이지부터 번역 중단, 원문 유지")
                        break
                    get_logger().log(f"  [batch {bi}/{len(batches)}] {entry.label} 할당량 초과 "
                          f"({delay:.0f}초 대기 예약) -> {pool[nxt].label}(으)로 전환")
                    key_idx = nxt
                    keys_tried_since_success += 1
                    continue
                attempt += 1
                get_logger().log(f"  [batch {bi}/{len(batches)}] 시도 {attempt}/{attempt_cap} "
                      f"({entry.label}) 실패: {e}")
                if attempt >= attempt_cap:
                    get_logger().log(f"  [batch {bi}/{len(batches)}] 서로 다른 모델로 {attempt}번 실패 "
                          f"-> 남은 {len(remaining)}개는 원문 유지하고 다음 배치로")
                    break
                # 이 항목을 짧게 쿨다운시켜 실제로 '다음 순위' 모델로 넘어가게 한다.
                #
                # 실제 확인된 문제: 예전엔 여기서 next_alive_index(key_idx + 1)만 불렀는데,
                # 그 함수는 살아있는 것 중 priority가 가장 높은(=숫자가 가장 낮은) 항목을
                # 그대로 다시 고른다. entry.alive를 안 건드리면 방금 실패한 바로 그 1순위
                # 모델이 죽지 않은 채로 남아 있어서 next_alive_index가 결국 '같은 모델'을
                # 다시 골라버렸다 - 로그엔 "전환"이라고 찍히지만 실제로는 동일 모델을
                # max_attempts(기본 3)번 연속으로 때리는 것이었다. 특히 응답이 느리게
                # 걸리다 타임아웃되는 경우, 배치 하나가 (api_timeout × max_attempts)만큼
                # 그대로 낭비되어 진행률이 몇 분씩 0%로 멈춘 것처럼 보이는 원인이 됐다
                # (2순위 이하 모델이나 로컬 NPU는 전혀 시도되지도 않았다).
                cooldown = min(2 ** attempt, 15)
                entry.alive = False
                entry.revive_at = time.monotonic() + cooldown
                nxt = next_alive_index(key_idx + 1)
                if nxt is not None:
                    # 다른 모델로 실제로 넘어간다. 여기서 그대로 sleep(cooldown)까지 해버리면
                    # 정확히 cooldown이 지난 시점에 다시 top으로 돌아가 next_alive_index를
                    # 부르게 되고, 그 호출이 '지금 막' 원래 항목을 부활시켜 버려 우선순위
                    # 규칙상 다시 그 항목을 고르는 촌극이 벌어진다(전환 로그만 찍히고 실제
                    # 호출은 한 번도 안 바뀌는 상태였다). 전환에 성공했으면 바로 다음
                    # 요청으로 넘어가고, 시간을 버리는 대기는 정말 갈 곳이 없을 때만 한다.
                    key_idx = nxt
                    get_logger().log(f"  [batch {bi}/{len(batches)}] {entry.label} 응답 실패 "
                          f"-> {pool[key_idx].label}(으)로 전환 (원 항목은 {cooldown:.0f}초 후 복귀 가능)")
                    continue
                # 전환할 다른 수단이 전혀 없으면 쿨다운을 취소하고 같은 항목으로 잠시 대기 후 재시도
                entry.alive = True
                entry.revive_at = None
                time.sleep(cooldown)
                continue

            before_count = len(remaining)
            cache_save_map = {}
            for sid, txt in mapping.items():
                if sid in remaining:
                    remaining[sid].translated = txt
                    cache_save_map[remaining[sid].text] = txt
            if cache_save_map:
                GLOBAL_CACHE.set_batch(cache_save_map, src_lang, tgt_lang, glossary_text)
            remaining = {k: v for k, v in remaining.items() if v.translated is None}
            if remaining:
                if len(remaining) >= before_count:
                    no_progress += 1
                    if no_progress >= 3:
                        get_logger().log(f"  [batch {bi}/{len(batches)}] 3회 연속 진전 없음(모델이 세그먼트를 "
                              f"계속 누락) -> 남은 {len(remaining)}개는 원문 유지하고 다음 배치로")
                        break
                else:
                    no_progress = 0
                get_logger().log(f"  [batch {bi}/{len(batches)}] 누락 {len(remaining)}개 세그먼트 재요청")
                # 배치가 여러 요청 라운드를 거치는 동안에도(누락분 재요청 등) 진행바를
                # 그때그때 갱신 - 배치 하나가 끝날 때까지 기다리지 않는다.
                _emit_progress(bi)

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
        get_logger().log(f"  [batch {bi}/{len(batches)}] 완료 (실제 번역 누적 {done}/{len(targets)} 세그먼트)")
        _emit_progress(bi)

        if aborted:
            break

    # 처리되지 못한 이후 배치들도 원문 유지로 채워둔다 (재구성 단계 안전장치)
    for s in targets:
        if s.translated is None:
            s.translated = s.text
            s.translation_failed = True

    # 어떤 키/모델을 몇 번 썼는지 요약 - 분산이 실제로 되고 있는지 한눈에 확인용
    used_entries = [e for e in pool if e.calls]
    if used_entries:
        get_logger().log("  [사용량] 이번 실행 요청 분포")
        for e in sorted(used_entries, key=lambda x: (-x.calls, x.label)):
            quota = ""
            if not e.is_local and e.rpd_limit:
                quota = (f" / 오늘 누적 {GLOBAL_LEDGER.used_today(e.key_id, e.model)}"
                         f"/{e.rpd_limit}회")
            get_logger().log(f"       - {e.label}: {e.calls}회{quota}")
        GLOBAL_LEDGER.save()

    if stopped_by_user:
        status_word = "사용자 중단(진행분까지 저장)"
    elif aborted:
        status_word = "중단됨"
    else:
        status_word = "완료"
    get_logger().log(f"[3/4] 번역 {status_word}: {len(targets)}개 세그먼트, "
          f"원문 {total_chars_sent:,}자 전송")
    return aborted or stopped_by_user


def mock_translate(segments: list[Segment]) -> None:
    """API 없이 파이프라인(추출/재구성/한글 폰트)을 검증하기 위한 모의 번역."""
    for s in segments:
        if s.needs_translation:
            s.translated = f"[모의 번역] {s.text}"