; =====================================================================
;  고정 다운로드 URL 과 SHA-256 체크섬
; =====================================================================
;  ★ 체크섬이 "" 이면 무결성 검증 없이 다운로드한다(HTTPS 신뢰에만 의존).
;    tools/update_checksums.py 를 인터넷이 되는 PC에서 한 번 돌리면
;    이 파일의 값이 실제 파일 해시로 채워진다.
;
;    python tools\update_checksums.py
;
;  URL 이 사라지는 사고는 이 프로젝트에서 이미 한 번 났다
;  (Python 3.12.11 이 source-only 릴리스가 되어 .exe URL 이 404).
;  그래서 tests/test_installer_metadata.py 가 URL 생존 여부를 점검한다.
; =====================================================================

; --- Tesseract OCR (UB Mannheim 배포본) ------------------------------
; 새 버전으로 올릴 때는 파일명·URL·체크섬 세 줄을 함께 바꿀 것.
#define TesseractVersion  "5.5.0.20241111"
#define TesseractFile     "tesseract-ocr-w64-setup-" + TesseractVersion + ".exe"
#define TesseractUrl      "https://digi.bib.uni-mannheim.de/tesseract/" + TesseractFile
#define TesseractSha256   ""

; --- OCR 언어 데이터 --------------------------------------------------
; tessdata(레거시+LSTM) = UB Mannheim 배포본과 같은 계열. 정확도 우선.
; 더 작고 빠른 것을 원하면 tessdata_fast, 더 정확한 것은 tessdata_best 로 교체.
#define TessdataBaseUrl   "https://github.com/tesseract-ocr/tessdata/raw/main/"
#define TessSha_kor       ""
#define TessSha_jpn       ""
#define TessSha_jpn_vert  ""
#define TessSha_chi_sim   ""
#define TessSha_eng       ""

; --- Lemonade Server (선택, AMD Ryzen AI NPU) -------------------------
; 자산 이름이 릴리스마다 바뀔 수 있어 체크섬을 고정하지 않는다.
; 다운로드에 실패하면 설치기가 릴리스 페이지를 브라우저로 열어 준다.
#define LemonadeFile      "Lemonade_Server_Installer.exe"
#define LemonadeUrl       "https://github.com/lemonade-sdk/lemonade/releases/latest/download/" + LemonadeFile
#define LemonadeReleases  "https://github.com/lemonade-sdk/lemonade/releases/latest"
