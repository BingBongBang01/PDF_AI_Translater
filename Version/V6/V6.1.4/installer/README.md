# PDF AI 번역기 — 설치 프로그램 (Setup.exe)

포맷 직후, 인터넷만 연결된 Windows 10/11 PC에서 빌드된 앱 EXE를 바로 쓸 수 있게
해 주는 설치 프로그램이다. **Inno Setup 6.3 이상**으로 컴파일한다
(6.1+ 는 내장 다운로더, 6.3+ 는 `x64compatible` 문법 때문).

## 이 설치기가 하는 일 / 하지 않는 일

앱 EXE는 PyInstaller `--onefile` 빌드라 **Python 3.12와 모든 pip 패키지가 이미
내장**되어 있다. 그래서 이 설치기는 Python도 pip도 건드리지 않는다.
(`gui.py`의 "필수 요소 전체 자동 설치" 버튼은 **소스로 실행할 때만** 쓰는 것이다.
EXE 사용자에게는 대상이 다르다.)

실제로 하는 일:

| 항목 | 조건 | 권한 |
|---|---|---|
| 앱 EXE 배치 + 시작메뉴/바탕화면 바로가기 + 제거 프로그램 | 항상 | 사용자 |
| VC++ 2015–2022 x64 재배포 패키지 | 없을 때만 | 관리자 |
| Tesseract OCR | 선택(기본 켬), 없을 때만 | 관리자 |
| OCR 언어팩 kor/jpn/jpn_vert/chi_sim/eng | 선택(기본 켬) | 관리자 |
| `PATH` + `TESSDATA_PREFIX` 설정 | Tesseract가 있을 때 | 해당 범위 |
| Lemonade Server | 선택(**기본 끔**), Ryzen AI 감지 시에만 표시 | 사용자 |
| Defender 프로세스 예외 | 선택(**기본 끔**) | 관리자 |

하지 않는 일: Python/pip 설치, API 키 입력, manga-ocr 설치(아래 "알려진 제약" 참고),
Tesseract·VC++ 재배포의 제거(다른 프로그램과 공유하므로 제거 시 건드리지 않는다).

## 권한 모델

`PrivilegesRequired=lowest` + 단계별 `runas` 승격이다. 설치기 자체는 UAC 없이 시작하고
앱은 `%LOCALAPPDATA%\Programs\PDF-Translater`에 들어간다. 관리자가 꼭 필요한 단계
(VC++ 재배포, Tesseract, 언어팩 복사, Defender 예외)에서만 UAC를 띄우며,
**사용자가 거부해도 설치는 중단되지 않는다** — 해당 항목만 건너뛴 것으로 기록하고
마지막 화면에 목록으로 보여 준다.

## 빌드

```bat
cd Version\V6\V6.1.4\installer
build_setup.bat
```

`build_setup.bat`이 하는 일: ISCC 탐색(없으면 winget으로 설치) → `_get_version.py`로
버전 읽기 → 앱 EXE 없으면 `..\build_exe.bat` 호출 → `certutil`로 앱 EXE의 SHA-256
계산 → ISCC 2회 실행. 결과는 `Output\`에 떨어진다.

- `PDF-Translater-Setup-<ver>-web.exe` — 몇 MB. 실행 시 앱 EXE와 Tesseract를 내려받는다.
- `PDF-Translater-Setup-<ver>-offline.exe` — 앱 EXE와 VC++ 재배포를 내장. **`redist\`를
  먼저 채워야 빌드된다** (비어 있으면 web만 만들고 넘어간다).

```bat
mkdir redist
curl -L -o redist\vc_redist.x64.exe https://aka.ms/vs/17/release/vc_redist.x64.exe
curl -L -o redist\tesseract-ocr-w64-setup-5.5.0.20241111.exe ^
  https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.5.0.20241111.exe
```

### web 변형의 전제 — 순서를 지켜야 한다

web 설치기는 앱 EXE를 GitHub Release에서 받는다. 받는 주소는

```
https://github.com/BingBongBang01/PDF_AI_Translater/releases/download/<ReleaseTag>/PDF-Translater-v<ver>.exe
```

**`<ReleaseTag>`는 버전 문자열이 아니라 실제 태그 이름이다.** 현재 저장소의 V6.1.4
릴리스는 태그가 `Release`라서 `setup.iss`의 기본값도 `Release`로 두었다. 버전별 태그로
옮기면 빌드할 때 덮어쓴다:

```bat
set RELEASE_TAG=v6.1.4
build_setup.bat
```

**해시 고정 때문에 순서가 중요하다.** 설치기는 내려받은 EXE의 SHA-256을 고정값과
대조한다. 그런데 PyInstaller 빌드는 재현되지 않아서, 같은 소스를 다시 빌드해도 해시가
달라진다. 즉 **릴리스에 올린 그 파일의 해시**를 박아야 하며, 재빌드한 다른 파일의
해시를 박으면 설치기가 멀쩡한 다운로드를 거부한다. 올바른 순서:

```
build_exe.bat  →  dist\*.exe 를 릴리스에 업로드  →  (재빌드 없이) build_setup.bat
```

이미 올라가 있는 파일의 해시를 알고 있다면(릴리스 자산의 `digest` 필드에서 읽을 수
있다) 계산을 건너뛰고 그대로 쓸 수 있다:

```bat
set APPEXE_SHA256=<64자리 hex>
build_setup.bat
```

참고 — 2026-08-18 기준 `Release` 태그에 올라가 있는 `PDF-Translater-v6.1.4.exe`
(114,879,209바이트)의 SHA-256:

```
bb14d07c97a8430050f8653b48d8a5e959f379f7ed340bea32fd2e4b386d639c
```

### 다운로드 무결성 — 지금은 일부 꺼져 있다

`checksums.iss.inc`의 SHA-256 값이 비어 있으면 그 파일은 HTTPS 신뢰에만 의존해
받는다. 인터넷이 되는 PC에서 한 번 채워 두어야 한다.

```bat
python tools\update_checksums.py          :: 비어 있는 항목만 채움
python tools\update_checksums.py --force  :: 버전 올릴 때 전부 재계산
```

`build_setup.bat`은 미고정 항목이 남아 있으면 컴파일 직전에 경고를 출력한다(중단하지는
않는다). VC++ 재배포만은 `aka.ms` 영구 링크라 내용이 계속 바뀌어 **고정이 불가능**하다 —
이 한 건은 검증이 약하다.

## 무인 설치

```bat
PDF-Translater-Setup-6.1.4-web.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART ^
  /LOG="%TEMP%\pdft-setup.log" /TASKS="desktopicon,tesseract,tesslangs"
```

무인 **제거**에서는 `%APPDATA%\PDFTranslaterGUI`(API 키, 번역 캐시)를 묻지 않고
**보존**한다. 대화형 제거에서만 삭제 여부를 묻는다.

---

## ⚠ 빌드 전에 실측 검증이 필요한 2가지

이 저장소는 리눅스 환경에서 작성되었다. 아래 두 가지는 **Windows에서 직접 확인해야
하고**, 결과에 따라 코드를 손봐야 한다. 확인 결과는 이 파일 아래 "검증 기록"에 남긴다.

### 1. VC++ 재배포 패키지가 정말 필요한가

PyInstaller는 빌드 머신의 `vcruntime140.dll` / `msvcp140.dll`을 번들에 넣는 경우가
많아서, 이 단계가 불필요할 수도 있다. **재배포 패키지가 없는 깨끗한 Windows**에서
앱 EXE를 그냥 실행해 보고 결과를 기록할 것.

- 잘 실행됨 → 이 단계는 보험으로 남겨 두면 된다(감지 후 없을 때만 설치하므로 비용 없음).
- DLL 없다는 오류 → 어떤 DLL인지 기록. 이 단계가 필수임이 확정된다.

### 2. UB Mannheim Tesseract 인스톨러의 무인 설치 스위치

`prereqs.iss.inc`의 `EnsureTesseract`는 지금 `/SILENT /NORESTART /SUPPRESSMSGBOXES`를
넘긴다. Inno Setup 기반이라는 전제인데, 확인이 필요하다.

```bat
tesseract-ocr-w64-setup-5.5.0.20241111.exe /?
```

- Inno 기반이 맞고 `/COMPONENTS=`를 받는다면 → 언어팩을 인스톨러에 맡기는 편이
  더 깔끔하다. `EnsureTesseract`에 `/COMPONENTS="!tesseract,langdata/kor,..."` 추가 검토.
- NSIS 기반이면 `/S`로 바꿔야 한다.
- 어느 쪽이든 **언어팩 직접 다운로드 경로(`InstallTessLanguages`)는 폴백으로 남겨 둔다.**

---

## 테스트

### 리눅스/CI에서 가능한 것

```bash
python -m pytest installer/tests/ -q
```

ISCC는 Windows 전용이라 컴파일 검증은 못 하지만, 존재하지 않는 파일 참조, `http://`
URL, 정의되지 않은 `#define`, 시스템 영향 항목이 기본 켜짐으로 바뀐 것, PATH 레지스트리
항목의 `preservestringtype` 누락은 여기서 잡힌다.

URL 생존 확인은 네트워크가 필요해 기본 skip이다. 릴리스 전에 한 번 돌릴 것:

```bash
PDFT_CHECK_URLS=1 python -m pytest installer/tests/ -q
```

(이 프로젝트는 이미 URL 소멸 사고를 겪었다 — Python 3.12.11이 source-only 릴리스가
되면서 `.exe` URL이 404가 됐다. `gui.py`의 `PYTHON312_INSTALLER_URL` 주석 참고.)

### Windows VM 테스트 매트릭스

Windows 설치 **직후 상태에서 체크포인트를 뜨고**, 매 시나리오마다 롤백한다.
Python·VC++ 재배포·Tesseract가 하나도 없어야 의미가 있다.

| # | 시나리오 | 기대 결과 |
|---|---|---|
| 1 | 관리자 계정, 전체 선택 | 모두 설치, 앱 실행, OCR 동작 |
| 2 | 일반 사용자, UAC 승인 | 앱은 `%LOCALAPPDATA%`, Tesseract는 승격 후 설치 |
| 3 | 일반 사용자, **UAC 거부** | 앱 설치·실행 성공, Tesseract만 건너뜀 + 마지막 화면에 안내 |
| 4 | 다운로드 중 네트워크 차단 | 해당 항목만 건너뜀, 설치 자체는 완료 |
| 5 | 시스템 프록시 설정 환경 | Inno 내장 다운로더(WinHTTP)가 프록시 경유 성공 |
| 6 | Tesseract가 이미 있는 PC | 감지 후 건너뜀, 언어팩만 보강 |
| 7 | offline 변형, 네트워크 완전 차단 | 언어팩 외 전부 성공 |
| 8 | `/VERYSILENT` 무인 설치 | 프롬프트 없이 완료 |
| 9 | 같은 버전 재설치 / 상위 버전 업그레이드 | `AppId` 기준 교체, 중복 항목 없음 |
| 10 | 제거 | 앱·바로가기·환경변수 제거, 사용자 데이터는 확인 후에만 |

### 설치 후 확인

```bat
where tesseract
tesseract --list-langs      :: kor, jpn, jpn_vert, chi_sim, eng 포함되어야 함
reg query "HKCU\Environment" /v TESSDATA_PREFIX
```

그다음 앱을 실행해 **[설치 & 환경] 탭**을 본다(`gui.py`의 진단 화면).

### 종단 기능 확인

1. `..\input.pdf` 번역 — OCR 없이 되는 기본 경로
2. 스캔된 일본어 PDF 번역 — `--tessdata-dir` 없이도 되어야 한다
   (= `TESSDATA_PREFIX`가 실제로 먹혔다는 증거)
3. 결과 PDF를 **Tesseract가 없는 다른 PC**의 뷰어에서 열어 한글이 보이는지 확인
   (V5.4에서 실제로 터졌던 폰트 임베딩 버그의 회귀 검사)

---

## 알려진 제약 / 후속 과제

1. **manga-ocr은 EXE에서 동작하지 않는다.** `gui.py`의 "manga-ocr 설치" 버튼은 외부
   시스템 Python에 `pip install manga-ocr`을 하는데, `pdf_engine/preprocess/ocr.py`는
   frozen 프로세스 안에서 `import manga_ocr`을 한다. 내장 인터프리터는 외부 Python의
   site-packages를 볼 수 없으므로, 설치가 성공해도 항상 Tesseract로 조용히 폴백한다.
   그래서 이 설치기는 manga-ocr을 제안하지 않는다.
   → 최소 조치: `getattr(sys, "frozen", False)`일 때 그 버튼을 비활성화하고 이유를 표시.

2. **EXE가 미서명이라 SmartScreen 경고가 뜬다.** Defender 예외로는 해결되지 않는다.
   근본 해법은 코드 서명 인증서(OV/EV)뿐이다. 당장은 "추가 정보 → 실행" 안내로 대응한다.

3. **`--onefile` → `--onedir` 전환 검토.** 제대로 된 설치기가 생긴 지금 onefile의
   이점(단일 파일 배포)은 사라졌다. onedir로 바꾸면 매 실행 시 100MB+ 압축 해제가
   없어져 시작이 훨씬 빨라지고, `%TEMP%\_MEIxxxxx` 패턴이 사라져 백신 마찰도 크게
   준다. 그러면 Defender 예외 옵션 자체가 대부분 불필요해진다.
   중간 단계로 `--runtime-tmpdir`만 앱 소유 폴더로 고정하는 방법도 있다.

4. **`LICENSE.md`의 저작권 표기가 비어 있다** (`<YEAR> <YOUR NAME OR ORGANIZATION>`).
   설치기가 이 라이선스를 사용자에게 보여 주므로 채워 넣는 것이 좋다.

5. **오프라인 변형은 타사 바이너리를 실제로 재배포**한다. `third_party_licenses/`의
   안내대로 Tesseract(Apache-2.0) 등의 고지문을 채워야 한다. web 변형은 해당 없음.

---

## 검증 기록

> Windows에서 확인한 결과를 여기에 남길 것.

- [ ] VC++ 재배포 없이 앱 EXE 실행 결과:
- [ ] `tesseract-ocr-w64-setup-*.exe /?` 출력(무인 스위치):
- [ ] ISCC 컴파일 성공 여부(web / offline):
- [ ] VM 매트릭스 1–10:
