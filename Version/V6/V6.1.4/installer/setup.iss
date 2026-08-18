; =====================================================================
;  PDF AI 번역기 - 설치 프로그램
;  필요 버전: Inno Setup 6.3 이상
;    - 6.1+ : CreateDownloadPage / DownloadTemporaryFile (내장 다운로더)
;    - 6.3+ : ArchitecturesAllowed=x64compatible 문법
; =====================================================================
;  빌드는 build_setup.bat 으로 한다. 직접 ISCC를 부를 때 필요한 정의:
;
;    ISCC /DAppVersion=6.1.4 /DAppExeSha256=<64자리 hex> setup.iss      (web)
;    ISCC /DOFFLINE /DAppVersion=6.1.4 setup.iss                        (offline)
;
;  설계 요지
;   - 앱 EXE는 PyInstaller onefile 이라 Python/pip 패키지가 이미 들어 있다.
;     따라서 이 설치기는 Python도 pip도 건드리지 않는다.
;   - 기본은 사용자 권한(UAC 없음)으로 설치하고, 관리자 권한이 반드시 필요한
;     단계(VC++ 재배포, Tesseract 전체 설치, Defender 예외)에서만 승격한다.
;     승격을 거부해도 설치는 중단되지 않고 그 항목만 건너뛴다.
; =====================================================================

#ifndef AppVersion
  #error AppVersion 이 정의되지 않았습니다. build_setup.bat 을 사용하세요.
#endif

#ifndef AppExeSha256
  #define AppExeSha256 ""
#endif

#include "checksums.iss.inc"

#define AppName        "PDF AI 번역기"
#define AppNameEn      "PDF AI Translater"
#define AppPublisher   "BingBongBang01"
#define AppUrl         "https://github.com/BingBongBang01/PDF_AI_Translater"
#define AppExeName     "PDF-Translater-v" + AppVersion + ".exe"
; 앱 EXE 가 실제로 올라가 있는 릴리스의 "태그 이름". 버전 문자열과 다를 수 있다
; (현재 저장소의 V6.1.4 릴리스는 태그가 'Release' 다).
; 버전별 태그로 옮기면 빌드할 때 /DReleaseTag=v6.1.4 로 덮어쓰면 된다.
#ifndef ReleaseTag
  #define ReleaseTag "Release"
#endif
#define AppExeUrl      AppUrl + "/releases/download/" + ReleaseTag + "/" + AppExeName

[Setup]
; AppId 는 업그레이드/제거 식별자다. 버전이 올라가도 절대 바꾸지 말 것.
AppId={{7A6F1C42-3E9B-4D58-9A21-5C0B8E7D4F16}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppNameEn} Setup

DefaultDirName={autopf}\PDF-Translater
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
LicenseFile=assets\LICENSE-ko.txt

; x64 전용: 앱 EXE가 64비트 PyInstaller 빌드이고 VC++ 재배포도 x64를 쓴다.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; --- 권한 모델: 기본 비승격, 필요한 단계에서만 runas ---
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

; 환경변수(PATH, TESSDATA_PREFIX)를 바꾸므로 WM_SETTINGCHANGE 브로드캐스트가 필요하다.
ChangesEnvironment=yes

OutputDir=Output
#ifdef OFFLINE
OutputBaseFilename=PDF-Translater-Setup-{#AppVersion}-offline
#else
OutputBaseFilename=PDF-Translater-Setup-{#AppVersion}-web
#endif
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes

[Languages]
Name: "korean";  MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
korean.TaskDesktopIcon=바탕화면에 바로가기 만들기
korean.TaskTesseract=Tesseract OCR 설치 (스캔된 PDF·만화 번역에 필요)
korean.TaskTessLangs=한국어/일본어/중국어 OCR 언어팩 추가
korean.TaskLemonade=Lemonade Server 설치 (AMD Ryzen AI NPU 로컬 번역)
korean.TaskDefender=Windows Defender 실시간 검사에서 이 프로그램만 제외 (첫 실행 속도 개선)
korean.GroupOcr=OCR (스캔 문서 / 이미지 속 글자)
korean.GroupOptional=선택 기능
korean.LaunchApp={#AppName} 실행
english.TaskDesktopIcon=Create a desktop shortcut
english.TaskTesseract=Install Tesseract OCR (required for scanned PDFs)
english.TaskTessLangs=Add Korean/Japanese/Chinese OCR language data
english.TaskLemonade=Install Lemonade Server (AMD Ryzen AI NPU local translation)
english.TaskDefender=Exclude only this program from Windows Defender real-time scanning
english.GroupOcr=OCR (scanned documents / text in images)
english.GroupOptional=Optional features
english.LaunchApp=Launch {#AppName}

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktopIcon}"
Name: "tesseract";   Description: "{cm:TaskTesseract}";  GroupDescription: "{cm:GroupOcr}"
Name: "tesslangs";   Description: "{cm:TaskTessLangs}";  GroupDescription: "{cm:GroupOcr}"
; 아래 둘은 시스템에 영향을 주므로 반드시 기본 해제 상태로 둔다.
Name: "lemonade";    Description: "{cm:TaskLemonade}";   GroupDescription: "{cm:GroupOptional}"; Flags: unchecked; Check: HasAmdRyzenAiNpu
Name: "defender";    Description: "{cm:TaskDefender}";   GroupDescription: "{cm:GroupOptional}"; Flags: unchecked

[Files]
#ifdef OFFLINE
; offline 변형: 앱 EXE와 VC++ 재배포를 설치기 안에 넣는다.
Source: "..\dist\{#AppExeName}";      DestDir: "{app}"; Flags: ignoreversion
; dontcopy: 설치기 안에 넣되 설치하지는 않는다. [Code] 가 ExtractTemporaryFile 로 꺼내 쓴다.
; DestDir: {tmp} 로 하면 안 된다 - [Files] 설치는 PrepareToInstall 보다 뒤라서
; 타사 인스톨러를 실행할 시점에 아직 파일이 없다.
Source: "redist\vc_redist.x64.exe";   Flags: dontcopy
Source: "redist\{#TesseractFile}";    Flags: dontcopy
Source: "third_party_licenses\*";     DestDir: "{app}\licenses"; Flags: ignoreversion
#else
; web 변형: NextButtonClick(wpReady) 에서 {tmp} 로 내려받은 파일을 external 로 설치한다.
Source: "{tmp}\{#AppExeName}";        DestDir: "{app}"; Flags: external ignoreversion
#endif
Source: "..\icon.ico";                DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.txt";              DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "assets\LICENSE-ko.txt";      DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";                          Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\변경 이력 및 사용 안내";                Filename: "{app}\README.txt"
Name: "{group}\{cm:UninstallProgram,{#AppName}}";    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";                    Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Registry]
; --- TESSDATA_PREFIX : 앱의 find_tessdata_dir() 가 2순위로 읽는 환경변수 ---
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
  ValueType: expandsz; ValueName: "TESSDATA_PREFIX"; ValueData: "{code:CM_TessdataDir}"; \
  Flags: preservestringtype uninsdeletevalue; Check: TessdataDirFound and IsAdminInstallMode
Root: HKCU; Subkey: "Environment"; \
  ValueType: expandsz; ValueName: "TESSDATA_PREFIX"; ValueData: "{code:CM_TessdataDir}"; \
  Flags: preservestringtype uninsdeletevalue; Check: TessdataDirFound and (not IsAdminInstallMode)

; PATH 추가/제거는 [Code] 의 AddTesseractToPath / RemoveTesseractFromPath 가 담당한다.
; [Registry] 의 "{olddata};..." 방식을 쓰지 않는 이유: HKCU\Environment 에 Path 값이
; 아예 없는 사용자 프로필이 흔한데, 그러면 {olddata} 가 빈 문자열이 되어 앞에 세미콜론이
; 붙은 잘못된 값이 써진다. 제거 로직과 대칭을 맞추기에도 코드 쪽이 낫다.

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchApp}"; \
  Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\licenses"

[Code]
#include "prereqs.iss.inc"
