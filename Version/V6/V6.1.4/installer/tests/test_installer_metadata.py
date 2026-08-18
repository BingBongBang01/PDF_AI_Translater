"""설치 프로그램 스크립트의 정합성 검사.

Inno Setup 컴파일러(ISCC)는 Windows 전용이라 리눅스 CI 에서 .iss 를 컴파일해
볼 수는 없다. 대신 컴파일하지 않고도 잡을 수 있는 실수 - 존재하지 않는 파일
참조, http:// URL, 정의되지 않은 #define, 시스템에 영향을 주는 항목이 기본
선택으로 켜져 있는 것 - 를 여기서 막는다.

네트워크가 필요한 검사(URL 생존 확인)는 기본적으로 건너뛰고,
PDFT_CHECK_URLS=1 일 때만 돈다. 이 프로젝트는 이미 URL 소멸 사고를 겪었다
(Python 3.12.11 이 source-only 릴리스가 되면서 .exe URL 이 404).
"""
from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

import pytest

INSTALLER_DIR = Path(__file__).resolve().parent.parent
SETUP_ISS = INSTALLER_DIR / "setup.iss"
PREREQS_INC = INSTALLER_DIR / "prereqs.iss.inc"
CHECKSUMS_INC = INSTALLER_DIR / "checksums.iss.inc"

ISS_SOURCES = [SETUP_ISS, PREREQS_INC, CHECKSUMS_INC]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def all_text() -> str:
    return "\n".join(read(p) for p in ISS_SOURCES)


# --------------------------------------------------------------------
# 파일 존재
# --------------------------------------------------------------------
def test_installer_sources_exist():
    for p in ISS_SOURCES:
        assert p.is_file(), f"누락: {p}"
    assert (INSTALLER_DIR / "build_setup.bat").is_file()


def test_setup_iss_includes_both_fragments():
    text = read(SETUP_ISS)
    assert '#include "checksums.iss.inc"' in text
    assert '#include "prereqs.iss.inc"' in text


# --------------------------------------------------------------------
# [Files] 가 참조하는 상대 경로가 실제로 존재하는지
# --------------------------------------------------------------------
_SOURCE_RE = re.compile(r'^\s*Source:\s*"([^"]+)"', re.MULTILINE)


def test_file_sources_resolve():
    """Source: 로 참조하는 파일 중 Inno 상수나 와일드카드가 없는 것은 실제로 있어야 한다.

    {tmp} 등 런타임 상수로 시작하는 항목은 external 다운로드분이라 제외하고,
    dist\\*.exe 와 redist\\* 는 빌드/스테이징 산출물이라 제외한다.
    """
    missing = []
    for raw in _SOURCE_RE.findall(read(SETUP_ISS)):
        if raw.startswith("{") or "*" in raw:
            continue
        if raw.startswith("..\\dist\\") or raw.startswith("redist\\"):
            continue  # build_exe.bat 산출물 / 오프라인용 스테이징 파일(둘 다 gitignore)
        target = (INSTALLER_DIR / raw.replace("\\", "/")).resolve()
        if not target.exists():
            missing.append(raw)
    assert not missing, f"[Files] 가 참조하는 파일이 없습니다: {missing}"


# --------------------------------------------------------------------
# #define 정합성
# --------------------------------------------------------------------
_DEFINE_RE = re.compile(r"^#define\s+(\w+)", re.MULTILINE)
_USE_RE = re.compile(r"\{#(\w+)\}")

# Inno/ISPP 가 스스로 제공하거나 build_setup.bat 이 /D 로 주입하는 이름들
INJECTED = {"AppVersion", "AppExeSha256", "OFFLINE"}


def test_every_referenced_define_is_defined():
    text = all_text()
    defined = set(_DEFINE_RE.findall(text)) | INJECTED
    used = set(_USE_RE.findall(text))
    undefined = sorted(used - defined)
    assert not undefined, f"정의되지 않은 #define 참조: {undefined}"


def test_app_id_is_set():
    m = re.search(r"^AppId=\{\{([0-9A-Fa-f-]+)\}", read(SETUP_ISS), re.MULTILINE)
    assert m, "AppId 가 없습니다. 업그레이드/제거 식별에 반드시 필요합니다."
    assert len(m.group(1)) == 36, f"AppId GUID 형식이 이상합니다: {m.group(1)}"


# --------------------------------------------------------------------
# 보안 / 안전 관련 회귀 방지
# --------------------------------------------------------------------
_URL_RE = re.compile(r"https?://[^\s\"'+)]+")


def test_all_urls_are_https():
    bad = [u for u in _URL_RE.findall(all_text()) if u.startswith("http://")]
    assert not bad, f"평문 http URL: {bad}"


@pytest.mark.parametrize("task", ["lemonade", "defender"])
def test_system_impacting_tasks_default_off(task):
    """시스템에 영향을 주는 선택 항목은 기본 해제여야 한다.

    특히 Defender 예외는 사용자가 명시적으로 켰을 때만 적용되어야 한다.
    """
    line = next(
        (ln for ln in read(SETUP_ISS).splitlines()
         if ln.strip().startswith(f'Name: "{task}"')),
        None,
    )
    assert line is not None, f"[Tasks] 에 {task} 항목이 없습니다"
    assert "Flags: unchecked" in line, f"{task} 는 반드시 Flags: unchecked 여야 합니다"


def test_defender_exclusion_never_covers_temp():
    """%TEMP% 전체를 검사에서 제외하지 않는지 확인.

    onefile EXE 가 매번 %TEMP%\\_MEIxxxxx 로 풀리기 때문에 임시 폴더 전체를
    제외하고 싶은 유혹이 있지만, 그건 사용자 시스템을 실질적으로 위험하게 만든다.
    프로세스 단위 예외만 허용한다.
    """
    text = read(PREREQS_INC)
    assert "Add-MpPreference" in text, "Defender 예외 코드가 사라졌습니다"
    assert "ExclusionPath" not in text, "ExclusionPath(경로 단위 제외)는 쓰지 않습니다"
    assert "ExclusionProcess" in text


def test_path_is_written_as_expand_string():
    """PATH 를 REG_SZ 로 덮어쓰면 %SystemRoot% 같은 기존 항목이 전부 깨진다.

    PATH 갱신은 [Code] 의 AddTesseractToPath 가 담당하며 반드시
    RegWriteExpandStringValue(REG_EXPAND_SZ) 를 써야 한다.
    """
    text = read(PREREQS_INC)
    assert "procedure AddTesseractToPath" in text
    assert "RegWriteExpandStringValue(EnvRootKey, EnvSubKey, 'Path'" in text
    assert "RegWriteStringValue(EnvRootKey, EnvSubKey, 'Path'" not in text, \
        "PATH 를 REG_SZ 로 쓰고 있습니다 - 기존 PATH 항목이 깨집니다"


def test_no_path_registry_section_entry():
    """[Registry] 의 '{olddata};...' 방식은 쓰지 않는다.

    HKCU\\Environment 에 Path 값이 없는 프로필에서 선행 세미콜론이 붙은
    잘못된 PATH 가 만들어진다.
    """
    assert 'ValueName: "Path"' not in read(SETUP_ISS)


# Windows 파일명에 쓸 수 없는 문자. 바로가기 이름은 .lnk 파일명이 된다.
_BAD_NAME_CHARS = set('/:*?"<>|')


def test_shortcut_names_are_valid_filenames():
    for raw in re.findall(r'^\s*Name:\s*"([^"]+)"', read(SETUP_ISS), re.MULTILINE):
        if not raw.startswith("{"):
            continue  # [Tasks] 의 태스크 이름은 파일명이 아니다
        leaf = raw.split("\\")[-1]
        # {cm:...} / {#...} 같은 상수 안의 콜론은 Inno 문법이므로 제외한다.
        leaf = re.sub(r"\{[^}]*\}", "", leaf)
        bad = _BAD_NAME_CHARS & set(leaf)
        assert not bad, f"바로가기 이름에 파일명 금지 문자 {sorted(bad)}: {raw}"


# --------------------------------------------------------------------
# 체크섬 고정 상태
# --------------------------------------------------------------------
def _empty_checksums() -> list[str]:
    return re.findall(r'^#define\s+(\w*Sha\w*)\s+""\s*$', read(CHECKSUMS_INC), re.MULTILINE)


def test_checksums_pinned():
    empty = _empty_checksums()
    if empty:
        pytest.skip(
            "체크섬이 비어 있어 다운로드 무결성 검증이 꺼져 있습니다: "
            + ", ".join(empty)
            + " — 인터넷이 되는 PC에서 `python tools/update_checksums.py` 를 실행해 채우세요."
        )


# --------------------------------------------------------------------
# URL 생존 확인 (네트워크 필요, 기본 skip)
# --------------------------------------------------------------------
@pytest.mark.skipif(os.environ.get("PDFT_CHECK_URLS") != "1",
                    reason="PDFT_CHECK_URLS=1 일 때만 실행 (네트워크 필요)")
def test_pinned_urls_are_alive():
    import sys

    sys.path.insert(0, str(INSTALLER_DIR / "tools"))
    import update_checksums as uc  # type: ignore[import-not-found]

    defines = uc.parse_defines(read(CHECKSUMS_INC))
    urls = [url for _, url in uc.build_plan(defines)]
    urls.append(uc.expand(defines, "LemonadeReleases"))

    dead = []
    for url in urls:
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                if r.status >= 400:
                    dead.append(f"{url} -> {r.status}")
        except Exception as e:  # noqa: BLE001
            dead.append(f"{url} -> {e}")
    assert not dead, "죽은 다운로드 URL:\n" + "\n".join(dead)
