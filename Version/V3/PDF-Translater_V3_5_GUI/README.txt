PDF Translater V3.5 GUI

원인 분석:
오류 로그의 sys.executable이 WindowsApps의 Microsoft Store 실행 별칭이었습니다.
PyMuPDF는 Local\Programs\Python\Python312에 설치되어 있으므로 관리자 권한과 무관합니다.

V3.5 수정:
- GUI 시작 시 WindowsApps Python인지 검사
- WindowsApps로 실행되면 실제 Python 3.12 후보를 찾음
- 후보마다 PyMuPDF import를 실제 검사
- PyMuPDF가 설치된 실제 Python으로 GUI 자동 재실행
- run_gui.bat는 py -3.12로 절대 경로를 얻고, 실패 시 LocalAppData 경로 사용
- GUI에 '요구사항 설치' 버튼 추가
- 요구사항 설치도 WindowsApps가 아닌 실제 Python으로 실행
- build_exe.bat 역시 동일 Python으로 설치/검사/빌드
- requirements.txt를 EXE 배포 폴더에 포함
- 기존 레이아웃 보존, PDF 저장, API/NPU 기능 유지

권장:
1. run_gui.bat 실행
2. 필요하면 GUI의 '요구사항 설치' 클릭
3. 번역 테스트
4. build_exe.bat 실행
