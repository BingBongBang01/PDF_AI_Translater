{ =====================================================================
  요구사항 감지 / 다운로드 / 설치 루틴  (setup.iss 의 [Code] 에 include 됨)

  단계 구분이 중요하다. Inno 의 실행 순서는
      NextButtonClick(wpReady)  ->  PrepareToInstall  ->  [Files] 설치  ->  ssPostInstall
  이므로

    · 다운로드는 NextButtonClick(wpReady) 에서 한다.
      TDownloadWizardPage 는 마법사 페이지라 이 시점에만 정상적으로 뜬다.
    · 타사 설치 프로그램 실행/파일 복사는 PrepareToInstall 에서 한다.
      [Registry] 의 Check: 가 그 결과(gTesseractDir)를 읽으므로 반드시 그 앞이어야 한다.
    · offline 변형의 내장 바이너리는 Flags: dontcopy + ExtractTemporaryFile 로 꺼낸다.
      [Files] 설치는 PrepareToInstall 보다 뒤라서, DestDir: {tmp} 방식은 이 시점에
      아직 파일이 없다.

  원칙
   1. 감지 경로는 앱이 실제로 뒤지는 경로와 정확히 일치시킨다
      (pdf_engine/preprocess/extractor.py 의 find_tessdata_dir).
      여기가 어긋나면 "설치는 됐는데 앱이 못 찾는" 조용한 실패가 난다.
   2. 필수는 앱 EXE 하나뿐이다. 나머지는 실패해도 설치를 중단하지 않고
      건너뛴 항목으로 기록한 뒤 마지막 화면에서 사용자에게 알린다.
   3. 다운로드가 막히는 상황(사내 방화벽, URL 소멸)을 정상 경로로 취급한다.
      이 프로젝트는 이미 URL 소멸 사고를 겪었다 - Python 3.12.11 이 source-only
      릴리스가 되면서 .exe URL 이 404 가 됐다(gui.py 의 PYTHON312_INSTALLER_URL 주석).
  ===================================================================== }

const
  { UAC 대화상자에서 사용자가 '아니오'를 눌렀을 때 }
  ERROR_CANCELLED_UAC = 1223;
  { VC++ 재배포가 재부팅을 요구할 때. 실패가 아니라 성공으로 취급한다. }
  ERROR_SUCCESS_REBOOT_REQUIRED = 3010;

  TESS_LANG_COUNT = 5;

var
  DownloadPage  : TDownloadWizardPage;
  gTesseractDir : String;   { tesseract.exe 가 있는 폴더. 없으면 '' }
  gTessdataDir  : String;   { 위 폴더의 tessdata. 없으면 '' }
  gSkipped      : String;   { 건너뛴 항목(줄바꿈 구분) - 마지막 화면에 표시 }
  gVcRedistReady: Boolean;  { {tmp} 에 vc_redist.x64.exe 가 준비됨 }
  gTessSetupReady: Boolean; { {tmp} 에 Tesseract 인스톨러가 준비됨 }
  gLemonadeReady: Boolean;  { {tmp} 에 Lemonade 인스톨러가 준비됨 }
  gTessLangReady: String;   { 내려받기에 성공한 언어 목록 ';kor;jpn;' 형태 }

procedure NoteSkipped(const Item, Reason: String);
begin
  gSkipped := gSkipped + '  · ' + Item + ' — ' + Reason + #13#10;
  Log('[skipped] ' + Item + ': ' + Reason);
end;

{ ------------------------------------------------------------------ }
{  공통: 프로세스 실행 (필요할 때만 UAC 승격)                          }
{ ------------------------------------------------------------------ }
function RunProc(const FileName, Params: String; const Elevate: Boolean;
                 const ShowCmd: Integer; var ResultCode: Integer): Boolean;
var
  Verb: String;
begin
  { 이미 관리자로 실행 중이면 runas 를 쓸 필요가 없다(불필요한 UAC 방지). }
  if Elevate and (not IsAdminInstallMode) then
    Verb := 'runas'
  else
    Verb := 'open';

  ResultCode := 0;
  Result := ShellExec(Verb, FileName, Params, '', ShowCmd, ewWaitUntilTerminated, ResultCode);
  if not Result then
    Log(Format('[exec] 실행 실패: %s %s (code=%d)', [FileName, Params, ResultCode]));
end;

function WasUacDeclined(const Ok: Boolean; const ResultCode: Integer): Boolean;
begin
  Result := (not Ok) and (ResultCode = ERROR_CANCELLED_UAC);
end;

{ ------------------------------------------------------------------ }
{  공통: 파일 1건 확보 (offline=내장분 추출 / web=다운로드)             }
{ ------------------------------------------------------------------ }
function OnDownloadProgress(const Url, FileName: String;
                            const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

function TryDownloadOne(const Url, BaseName, Sha256: String): Boolean;
begin
  DownloadPage.Clear;
  DownloadPage.Add(Url, BaseName, Sha256);
  try
    DownloadPage.Download;
    Result := True;
    Log('[download] ok: ' + Url);
  except
    Result := False;
    Log('[download] 실패: ' + Url + ' -> ' + GetExceptionMessage);
  end;
end;

function TryExtractEmbedded(const BaseName: String): Boolean;
begin
  { offline 변형에서 Flags: dontcopy 로 넣어 둔 파일을 {tmp} 로 꺼낸다. }
  try
    ExtractTemporaryFile(BaseName);
    Result := FileExists(ExpandConstant('{tmp}\') + BaseName);
    Log('[embedded] 추출: ' + BaseName);
  except
    Result := False;
    Log('[embedded] 추출 실패: ' + BaseName + ' -> ' + GetExceptionMessage);
  end;
end;

{ ------------------------------------------------------------------ }
{  하드웨어 감지: AMD Ryzen AI (XDNA NPU)                              }
{ ------------------------------------------------------------------ }
function HasAmdRyzenAiNpu: Boolean;
var
  Cpu: String;
begin
  Result := False;
  { HARDWARE 하이브는 WOW64 리다이렉션 대상이 아니라 HKLM 을 그대로 읽으면 된다. }
  if RegQueryStringValue(HKLM,
       'HARDWARE\DESCRIPTION\System\CentralProcessor\0', 'ProcessorNameString', Cpu) then
    Result := Pos('ryzen ai', Lowercase(Cpu)) > 0;
end;

{ ------------------------------------------------------------------ }
{  VC++ 2015-2022 x64 재배포 패키지                                    }
{ ------------------------------------------------------------------ }
function IsVcRedist14Installed: Boolean;
var
  Installed: Cardinal;
begin
  { 설치기는 32비트 프로세스라 HKLM 을 그냥 쓰면 WOW6432Node 로 리다이렉트된다.
    x64 재배포 패키지는 64비트 뷰에 기록되므로 HKLM64 를 명시해야 한다. }
  Result := RegQueryDWordValue(HKLM64,
              'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64',
              'Installed', Installed) and (Installed = 1);
end;

{ ------------------------------------------------------------------ }
{  Tesseract OCR 감지                                                  }
{ ------------------------------------------------------------------ }
function TryTesseractRegDir(const RootKey: Integer; var Dir: String): Boolean;
var
  P: String;
begin
  Result := False;
  if RegQueryStringValue(RootKey, 'SOFTWARE\Tesseract-OCR', 'Path', P) and (P <> '') then
    if FileExists(AddBackslash(P) + 'tesseract.exe') then
    begin
      Dir := RemoveBackslashUnlessRoot(P);
      Result := True;
    end;
end;

function ProbeTesseractDir: String;
var
  P: String;
begin
  Result := '';

  { 1) UB Mannheim 인스톨러가 남기는 레지스트리 항목.
       64비트/32비트 뷰와 사용자 설치를 모두 본다. }
  if TryTesseractRegDir(HKLM64, P) then begin Result := P; Exit; end;
  if TryTesseractRegDir(HKLM32, P) then begin Result := P; Exit; end;
  if TryTesseractRegDir(HKCU,   P) then begin Result := P; Exit; end;

  { 2) 파일 직접 확인 - 앱의 find_tessdata_dir() 가 뒤지는 경로와 같게 유지할 것.
       설치기는 32비트 프로세스라 %ProgramFiles% 가 x86 쪽으로 리다이렉트된다.
       64비트 경로는 %ProgramW6432% 로 명시해야 한다. }
  P := GetEnv('ProgramW6432');
  if (P <> '') and FileExists(P + '\Tesseract-OCR\tesseract.exe') then
  begin
    Result := P + '\Tesseract-OCR';
    Exit;
  end;

  P := GetEnv('ProgramFiles(x86)');
  if (P <> '') and FileExists(P + '\Tesseract-OCR\tesseract.exe') then
  begin
    Result := P + '\Tesseract-OCR';
    Exit;
  end;

  P := ExpandConstant('{localappdata}\Programs\Tesseract-OCR');
  if FileExists(P + '\tesseract.exe') then begin Result := P; Exit; end;
end;

procedure RefreshTesseractPaths;
begin
  gTesseractDir := ProbeTesseractDir;
  if gTesseractDir <> '' then
    gTessdataDir := gTesseractDir + '\tessdata'
  else
    gTessdataDir := '';
  Log('[tesseract] dir="' + gTesseractDir + '" tessdata="' + gTessdataDir + '"');
end;

{ [Registry] 의 Check: / {code:} 에서 부르는 얇은 래퍼들 }
function TessdataDirFound: Boolean;
begin
  Result := (gTessdataDir <> '') and DirExists(gTessdataDir);
end;

function CM_TessdataDir(Param: String): String;
begin
  Result := gTessdataDir;
end;

function EnvRootKey: Integer;
begin
  if IsAdminInstallMode then Result := HKLM else Result := HKCU;
end;

function EnvSubKey: String;
begin
  if IsAdminInstallMode then
    Result := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
  else
    Result := 'Environment';
end;

function PathContainsDir(const Dir: String): Boolean;
var
  Cur: String;
begin
  if not RegQueryStringValue(EnvRootKey, EnvSubKey, 'Path', Cur) then
  begin
    Result := False;
    Exit;
  end;
  { 앞뒤에 ';' 를 붙여 부분 문자열 오탐(C:\Foo 가 C:\FooBar 에 매칭)을 막는다. }
  Result := Pos(';' + Lowercase(Dir) + ';', ';' + Lowercase(Cur) + ';') > 0;
end;

function NeedsAddTesseractPath: Boolean;
begin
  Result := (gTesseractDir <> '') and (not PathContainsDir(gTesseractDir));
end;

procedure AddTesseractToPath;
var
  Cur: String;
begin
  if not NeedsAddTesseractPath then Exit;

  { RegQueryStringValue 가 실패하면 Path 값 자체가 없는 것이다(사용자 프로필에서 흔함).
    그때는 구분자 없이 값 하나만 쓴다 - 앞에 ';' 가 붙은 잘못된 PATH 를 만들지 않는다. }
  if not RegQueryStringValue(EnvRootKey, EnvSubKey, 'Path', Cur) then
    Cur := ''
  else if (Cur <> '') and (Cur[Length(Cur)] = ';') then
    Cur := Copy(Cur, 1, Length(Cur) - 1);

  if Cur = '' then
    Cur := gTesseractDir
  else
    Cur := Cur + ';' + gTesseractDir;

  { 반드시 REG_EXPAND_SZ 로 쓴다. REG_SZ 로 덮으면 %SystemRoot% 같은 기존 항목이 깨진다. }
  if RegWriteExpandStringValue(EnvRootKey, EnvSubKey, 'Path', Cur) then
    Log('[path] 추가: ' + gTesseractDir)
  else
    NoteSkipped('PATH 등록', 'PATH 에 Tesseract 폴더를 추가하지 못했습니다');
end;

{ ------------------------------------------------------------------ }
{  OCR 언어 데이터 목록                                                }
{ ------------------------------------------------------------------ }
function TessLangName(I: Integer): String;
begin
  case I of
    0: Result := 'kor';
    1: Result := 'jpn';
    2: Result := 'jpn_vert';   { 일본어 세로쓰기 - 만화 번역에 필수 }
    3: Result := 'chi_sim';
    4: Result := 'eng';
  else
    Result := '';
  end;
end;

function TessLangSha256(I: Integer): String;
begin
  case I of
    0: Result := '{#TessSha_kor}';
    1: Result := '{#TessSha_jpn}';
    2: Result := '{#TessSha_jpn_vert}';
    3: Result := '{#TessSha_chi_sim}';
    4: Result := '{#TessSha_eng}';
  else
    Result := '';
  end;
end;

{ =================================================================== }
{  1단계: 다운로드  (NextButtonClick / wpReady)                        }
{ =================================================================== }
function AcquireAppExe: Boolean;
begin
#ifdef OFFLINE
  Result := True;   { 앱 EXE 는 [Files] 로 그대로 설치된다 }
#else
  { 유일한 필수 항목. SHA-256 은 build_setup.bat 이 실제 빌드 산출물에서 계산해 넣는다. }
  Result := TryDownloadOne('{#AppExeUrl}', '{#AppExeName}', '{#AppExeSha256}');
#endif
end;

procedure AcquireVcRedist;
begin
  gVcRedistReady := False;
  if IsVcRedist14Installed then
  begin
    Log('[vcredist] 이미 설치됨 - 건너뜀');
    Exit;
  end;
#ifdef OFFLINE
  gVcRedistReady := TryExtractEmbedded('vc_redist.x64.exe');
#else
  { aka.ms 영구 링크는 Visual Studio 업데이트마다 내용이 바뀌어 SHA-256 을 고정할 수
    없다. 이 한 건만 HTTPS + Microsoft 도메인 신뢰에 의존한다. }
  gVcRedistReady := TryDownloadOne('https://aka.ms/vs/17/release/vc_redist.x64.exe',
                                   'vc_redist.x64.exe', '');
#endif
  if not gVcRedistReady then
    NoteSkipped('VC++ 재배포 패키지', '설치 파일을 준비하지 못함 (네트워크/방화벽 확인)');
end;

procedure AcquireTesseract;
begin
  gTessSetupReady := False;
  RefreshTesseractPaths;
  if gTesseractDir <> '' then
  begin
    Log('[tesseract] 이미 설치됨 - 건너뜀');
    Exit;
  end;
#ifdef OFFLINE
  gTessSetupReady := TryExtractEmbedded('{#TesseractFile}');
#else
  gTessSetupReady := TryDownloadOne('{#TesseractUrl}', '{#TesseractFile}', '{#TesseractSha256}');
#endif
  if not gTessSetupReady then
    NoteSkipped('Tesseract OCR', '설치 파일을 준비하지 못함 — OCR 기능만 비활성화됩니다');
end;

procedure AcquireTessLanguages;
var
  I: Integer;
  Lang: String;
begin
  gTessLangReady := ';';
  { 언어팩은 offline 변형에서도 내려받는다(용량 대비 가치가 낮아 번들하지 않음). }
  for I := 0 to TESS_LANG_COUNT - 1 do
  begin
    Lang := TessLangName(I);
    if TryDownloadOne('{#TessdataBaseUrl}' + Lang + '.traineddata',
                      Lang + '.traineddata', TessLangSha256(I)) then
      gTessLangReady := gTessLangReady + Lang + ';'
    else
      NoteSkipped('OCR 언어팩 (' + Lang + ')', '다운로드 실패');
  end;
end;

procedure AcquireLemonade;
var
  Code: Integer;
begin
  gLemonadeReady := False;
  if FileExists(ExpandConstant('{localappdata}\lemonade_server\bin\LemonadeServer.exe')) then
  begin
    Log('[lemonade] 이미 설치됨 - 건너뜀');
    Exit;
  end;
  { 자산 이름은 릴리스마다 바뀔 수 있다. 자동 다운로드가 실패하면 조용히 넘어가지 말고
    릴리스 페이지를 열어 사용자가 직접 받게 한다. }
  gLemonadeReady := TryDownloadOne('{#LemonadeUrl}', '{#LemonadeFile}', '');
  if not gLemonadeReady then
  begin
    NoteSkipped('Lemonade Server',
      '자동 다운로드 실패 — 릴리스 페이지를 열었습니다. 앱의 [설치 & 환경] 탭에서도 다시 시도할 수 있습니다');
    ShellExec('open', '{#LemonadeReleases}', '', '', SW_SHOWNORMAL, ewNoWait, Code);
  end;
end;

{ =================================================================== }
{  2단계: 설치  (PrepareToInstall)                                     }
{ =================================================================== }
procedure InstallVcRedist;
var
  Ok: Boolean;
  Code: Integer;
begin
  if not gVcRedistReady then Exit;

  Ok := RunProc(ExpandConstant('{tmp}\vc_redist.x64.exe'),
                '/install /quiet /norestart', True, SW_HIDE, Code);
  if WasUacDeclined(Ok, Code) then
  begin
    NoteSkipped('VC++ 재배포 패키지', '관리자 권한 요청이 거부됨');
    Exit;
  end;
  { 3010 = 재부팅 필요. 설치 자체는 성공한 것이므로 성공으로 본다. }
  if Ok and ((Code = 0) or (Code = ERROR_SUCCESS_REBOOT_REQUIRED)) then
    Log('[vcredist] 설치 완료 (code=' + IntToStr(Code) + ')')
  else
    NoteSkipped('VC++ 재배포 패키지', '설치 실패 (코드 ' + IntToStr(Code) + ')');
end;

procedure InstallTesseract;
var
  Ok: Boolean;
  Code: Integer;
begin
  if not gTessSetupReady then Exit;

  { UB Mannheim 배포본은 Inno Setup 으로 만들어져 /SILENT 계열 스위치를 받는다.
    빌드 전에 `tesseract-ocr-w64-setup-*.exe /?` 로 실제 스위치를 확인할 것
    (installer/README.md 의 '실측 검증' 항목). }
  Ok := RunProc(ExpandConstant('{tmp}\{#TesseractFile}'),
                '/SILENT /NORESTART /SUPPRESSMSGBOXES', True, SW_SHOW, Code);
  if WasUacDeclined(Ok, Code) then
  begin
    NoteSkipped('Tesseract OCR', '관리자 권한 요청이 거부됨 — OCR 기능만 비활성화됩니다');
    Exit;
  end;

  RefreshTesseractPaths;
  if gTesseractDir <> '' then
    Log('[tesseract] 설치 완료: ' + gTesseractDir)
  else
    NoteSkipped('Tesseract OCR',
                '설치 후에도 실행 파일을 찾지 못함 (코드 ' + IntToStr(Code) + ')');
end;

procedure InstallTessLanguages;
var
  I, Code, Queued: Integer;
  Lang, Script, ScriptPath: String;
  Ok: Boolean;
begin
  if gTessLangReady = '' then Exit;

  RefreshTesseractPaths;
  if gTessdataDir = '' then
  begin
    NoteSkipped('OCR 언어팩', 'Tesseract 가 없어 설치할 위치를 찾지 못함');
    Exit;
  end;

  Queued := 0;
  Script := '@echo off' + #13#10;

  for I := 0 to TESS_LANG_COUNT - 1 do
  begin
    Lang := TessLangName(I);
    if Pos(';' + Lang + ';', gTessLangReady) = 0 then
      Continue;                                  { 다운로드 실패분 }
    if FileExists(gTessdataDir + '\' + Lang + '.traineddata') then
    begin
      Log('[tessdata] ' + Lang + ' 이미 있음 - 건너뜀');
      Continue;
    end;
    { tessdata 가 Program Files 아래면 쓰기에 관리자 권한이 필요하다. 파일마다 UAC 를
      띄우지 않도록 복사 명령을 한 배치로 모아 한 번만 승격한다. }
    Script := Script + 'copy /Y "' + ExpandConstant('{tmp}\') + Lang + '.traineddata" "'
              + gTessdataDir + '\" >nul || exit /b 1' + #13#10;
    Queued := Queued + 1;
  end;

  if Queued = 0 then Exit;
  Script := Script + 'exit /b 0' + #13#10;

  ScriptPath := ExpandConstant('{tmp}\install_tessdata.cmd');
  if not SaveStringToFile(ScriptPath, Script, False) then
  begin
    NoteSkipped('OCR 언어팩', '임시 스크립트 생성 실패');
    Exit;
  end;

  Ok := RunProc(ExpandConstant('{cmd}'), '/C "' + ScriptPath + '"', True, SW_HIDE, Code);
  if WasUacDeclined(Ok, Code) then
    NoteSkipped('OCR 언어팩', '관리자 권한 요청이 거부됨')
  else if not (Ok and (Code = 0)) then
    NoteSkipped('OCR 언어팩', '복사 실패 (코드 ' + IntToStr(Code) + ')')
  else
    Log('[tessdata] ' + IntToStr(Queued) + '개 설치 완료');
end;

procedure InstallLemonade;
var
  Ok: Boolean;
  Code: Integer;
begin
  if not gLemonadeReady then Exit;
  { Lemonade 인스톨러의 무인 설치 스위치는 확인되지 않았다. 조용히 실패하는 것보다
    대화형으로 띄우고 사용자가 마치도록 안내하는 편이 정직하다
    (gui.py 의 _install_lemonade_worker 도 같은 이유로 완료를 단정하지 않는다). }
  Ok := RunProc(ExpandConstant('{tmp}\{#LemonadeFile}'), '', False, SW_SHOWNORMAL, Code);
  if not Ok then
    NoteSkipped('Lemonade Server', '설치 프로그램 실행 실패')
  else
    Log('[lemonade] 설치 프로그램 종료 (code=' + IntToStr(Code) + ')');
end;

procedure ApplyDefenderExclusion;
var
  Ok: Boolean;
  Code: Integer;
begin
  { 중요: %TEMP% 전체를 제외하지 않는다.
    onefile EXE 가 매번 %TEMP%\_MEIxxxxx 로 풀리기 때문에 임시 폴더 전체를 빼고 싶은
    유혹이 있지만, 그건 사용자 시스템을 실질적으로 위험하게 만든다.
    프로세스 이름 하나만 제외한다. }
  Ok := RunProc('powershell.exe',
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
    '"Add-MpPreference -ExclusionProcess ''{#AppExeName}''"', True, SW_HIDE, Code);
  if WasUacDeclined(Ok, Code) then
    NoteSkipped('Defender 예외', '관리자 권한 요청이 거부됨')
  else if not (Ok and (Code = 0)) then
    NoteSkipped('Defender 예외', '적용 실패 (코드 ' + IntToStr(Code) + ')');
end;

{ =================================================================== }
{  마법사 훅                                                           }
{ =================================================================== }
procedure InitializeWizard;
begin
  gSkipped := '';
  gTessLangReady := '';
  gVcRedistReady := False;
  gTessSetupReady := False;
  gLemonadeReady := False;
  DownloadPage := CreateDownloadPage(
    SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
  RefreshTesseractPaths;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  if CurPageID <> wpReady then
  begin
    Result := True;
    Exit;
  end;

  Result := True;
  DownloadPage.Show;
  try
    if not AcquireAppExe then
    begin
      { 앱 본체만 유일한 필수 항목이다. 여기서만 진행을 막고, 사용자가 네트워크를
        고친 뒤 [다음] 을 다시 누를 수 있도록 페이지에 머무른다. }
      Result := False;
      SuppressibleMsgBox(
        '프로그램 본체를 내려받지 못했습니다.' + #13#10#13#10 +
        '인터넷 연결(또는 사내 방화벽/프록시)을 확인한 뒤 [다음] 을 다시 눌러 주세요.' + #13#10#13#10 +
        '계속 실패하면 아래 주소에서 직접 내려받을 수 있습니다:' + #13#10 +
        '{#AppUrl}/releases',
        mbCriticalError, MB_OK, IDOK);
      Exit;
    end;

    { 아래는 전부 '실패해도 계속' 항목이다. }
    AcquireVcRedist;
    if WizardIsTaskSelected('tesseract') then AcquireTesseract;
    if WizardIsTaskSelected('tesslangs')  then AcquireTessLanguages;
    if WizardIsTaskSelected('lemonade')   then AcquireLemonade;
  finally
    DownloadPage.Hide;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';   { 여기서 중단시킬 만한 치명적 실패는 없다 }

  InstallVcRedist;
  InstallTesseract;
  InstallTessLanguages;
  InstallLemonade;

  { [Registry] 의 TESSDATA_PREFIX Check: 가 아래 값을 읽는다. 반드시 여기서 최신화할 것. }
  RefreshTesseractPaths;
  AddTesseractToPath;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('defender') then
    ApplyDefenderExclusion;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Extra: String;
begin
  if CurPageID <> wpFinished then
    Exit;

  Extra := '';
  if gSkipped <> '' then
    Extra := #13#10#13#10 + '건너뛴 항목:' + #13#10 + gSkipped +
             #13#10 + '앱을 실행한 뒤 [설치 & 환경] 탭에서 다시 시도할 수 있습니다.';

  if gTesseractDir <> '' then
    Extra := Extra + #13#10#13#10 +
      'OCR 이 인식되지 않으면 한 번 로그아웃하거나 재부팅하세요 ' +
      '(환경 변수 PATH / TESSDATA_PREFIX 반영).';

  if Extra <> '' then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + Extra;
end;

{ =================================================================== }
{  제거                                                                }
{ =================================================================== }
procedure RemoveTesseractFromPath;
var
  Cur, Needle, Lowered: String;
  P: Integer;
begin
  if gTesseractDir = '' then
    RefreshTesseractPaths;
  if gTesseractDir = '' then
    Exit;
  if not RegQueryStringValue(EnvRootKey, EnvSubKey, 'Path', Cur) then
    Exit;

  Needle  := ';' + Lowercase(gTesseractDir);
  Lowered := ';' + Lowercase(Cur);

  P := Pos(Needle + ';', Lowered);
  if P = 0 then
  begin
    { 맨 끝에 붙어 있는 경우 }
    if (Length(Lowered) >= Length(Needle)) and
       (Copy(Lowered, Length(Lowered) - Length(Needle) + 1, Length(Needle)) = Needle) then
      P := Length(Lowered) - Length(Needle) + 1
    else
      Exit;
  end;

  { Lowered 는 앞에 ';' 를 하나 더 붙였으므로 Cur 기준 인덱스는 P-1 이다. }
  Delete(Cur, P - 1, Length(Needle));
  RegWriteExpandStringValue(EnvRootKey, EnvSubKey, 'Path', Cur);
  Log('[uninstall] PATH 에서 제거: ' + gTesseractDir);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  RemoveTesseractFromPath;

  { 사용자 데이터는 묻고 나서만 지운다.
      config.json  - API 키
      cache\*.db   - 누적 번역 캐시(재번역 비용을 아껴 주는 자산)
    무인 제거(/VERYSILENT)에서는 SuppressibleMsgBox 가 기본값 IDNO 를 돌려주므로
    자동으로 '보존'이 선택된다. }
  DataDir := ExpandConstant('{userappdata}\PDFTranslaterGUI');
  if not DirExists(DataDir) then
    Exit;

  if SuppressibleMsgBox(
       '저장된 API 키와 번역 캐시도 함께 삭제할까요?' + #13#10#13#10 +
       DataDir + #13#10#13#10 +
       '[아니오] 를 선택하면 그대로 남겨 둡니다 (다시 설치할 때 그대로 쓸 수 있습니다).',
       mbConfirmation, MB_YESNO, IDNO) = IDYES then
  begin
    DelTree(DataDir, True, True, True);
    Log('[uninstall] 사용자 데이터 삭제: ' + DataDir);
  end;
end;
