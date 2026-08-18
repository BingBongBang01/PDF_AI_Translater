#!/usr/bin/env python3
"""checksums.iss.inc 의 SHA-256 값을 실제 파일 해시로 채운다.

설치 프로그램은 내려받은 파일의 해시를 고정값과 대조해 변조되거나 절단된
다운로드를 거부한다. 해시가 비어 있으면 그 검증이 통째로 꺼지므로, 인터넷이
되는 PC에서 이 스크립트를 한 번 돌려 값을 채워 두어야 한다.

    python tools/update_checksums.py            # 비어 있는 항목만 채움
    python tools/update_checksums.py --force    # 전부 다시 계산 (버전 올릴 때)
    python tools/update_checksums.py --check    # 대조만 하고 쓰지 않음 (CI용)
    python tools/update_checksums.py --list-empty   # 네트워크 없이 미고정 항목만 출력

대상에서 제외한 것
  · VC++ 재배포 패키지 - aka.ms 영구 링크라 내용이 계속 바뀌어 고정 불가
  · Lemonade Server    - 릴리스마다 자산이 바뀜
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

INC_PATH = Path(__file__).resolve().parent.parent / "checksums.iss.inc"
TESS_LANGS = ["kor", "jpn", "jpn_vert", "chi_sim", "eng"]

_DEFINE_RE = re.compile(r"^#define\s+(\w+)\s+(.*?)\s*$", re.MULTILINE)


def parse_defines(text: str) -> dict[str, str]:
    """#define 이름 -> 우변 식(문자열 그대로)."""
    return {m.group(1): m.group(2) for m in _DEFINE_RE.finditer(text)}


def expand(defines: dict[str, str], name: str, _depth: int = 0) -> str:
    """ISPP 의 문자열 연결(`"a" + Name + "b"`)을 펼쳐 실제 값을 만든다."""
    if _depth > 10:
        raise ValueError(f"#define 참조가 순환합니다: {name}")
    parts = []
    for token in (p.strip() for p in defines[name].split("+")):
        if token.startswith('"') and token.endswith('"'):
            parts.append(token[1:-1])
        else:
            parts.append(expand(defines, token, _depth + 1))
    return "".join(parts)


def sha256_of_url(url: str) -> str:
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=180) as r:  # noqa: S310 - 고정된 https URL
        while chunk := r.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def build_plan(defines: dict[str, str]) -> list[tuple[str, str]]:
    """(#define 이름, 그 파일의 URL) 목록."""
    base = expand(defines, "TessdataBaseUrl")
    plan = [("TesseractSha256", expand(defines, "TesseractUrl"))]
    plan += [(f"TessSha_{lang}", f"{base}{lang}.traineddata") for lang in TESS_LANGS]
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="이미 값이 있어도 다시 계산")
    ap.add_argument("--check", action="store_true", help="대조만 하고 파일을 고치지 않음")
    ap.add_argument("--list-empty", action="store_true",
                    help="네트워크 없이, 비어 있는 체크섬 이름만 출력 (빌드 경고용)")
    args = ap.parse_args()

    if args.list_empty:
        text = INC_PATH.read_text(encoding="utf-8")
        empty = [n for n, v in parse_defines(text).items()
                 if "Sha" in n and v.strip() == '""']
        print(" ".join(empty))
        return 0

    text = INC_PATH.read_text(encoding="utf-8")
    defines = parse_defines(text)
    failures: list[str] = []
    updated = 0

    for name, url in build_plan(defines):
        current = defines[name].strip('"')
        if current and not (args.force or args.check):
            print(f"  skip  {name} (이미 설정됨)")
            continue

        print(f"  fetch {name}  <- {url}")
        try:
            digest = sha256_of_url(url)
        except Exception as e:  # noqa: BLE001 - 어떤 실패든 사람이 읽을 형태로 보고한다
            failures.append(f"{name}: {url} -> {e}")
            print(f"        실패: {e}", file=sys.stderr)
            continue

        if args.check:
            if not current:
                failures.append(f"{name}: 체크섬이 비어 있음 (실제값 {digest})")
            elif current != digest:
                failures.append(f"{name}: 고정값 {current} != 실제 {digest}")
            else:
                print("        일치")
            continue

        text = re.sub(
            rf'^(#define\s+{re.escape(name)}\s+)"[^"]*"',
            lambda m: f'{m.group(1)}"{digest}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        updated += 1
        print(f"        {digest}")

    if updated:
        INC_PATH.write_text(text, encoding="utf-8")
        print(f"\n{INC_PATH.name} 갱신됨 ({updated}개)")

    if failures:
        print("\n문제:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\n이상 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
