PDF Translater V3.4 GUI

V3.4 핵심 수정
- gui.py 관리자 권한 자동 재실행 제거
- EXE의 --uac-admin 제거
- Microsoft WindowsApps Python 실행 별칭 문제 회피
- build_exe.bat가 py -3.12로 실제 python.exe 절대 경로를 먼저 확정
- 패키지 설치, import 검사, PyInstaller 빌드를 모두 동일 python.exe로 실행
- run_gui.bat 추가: GUI 직접 테스트도 동일 Python 3.12 사용
- PyMuPDF/pypdf/API SDK collect-all 및 hidden import 유지
- PyMuPDF import 실패 시 fitz 호환 폴백과 상세 진단 유지
- V3.1의 원본 줄 bbox/레이아웃 보존 기능 유지
- PDF 저장 완료 후 GUI 종료코드 오표시 보정 유지

권장 사용 순서
1. 기존 프로젝트의 prompts 폴더가 이 폴더 안에 있는지 확인
2. run_gui.bat 실행 후 GUI 번역 테스트
3. 정상 작동하면 build_exe.bat 실행
4. dist\PDF-Translater-v3.4\PDF-Translater-v3.4.exe 실행

이 PC에서 확인된 정상 Python 경로 예시:
C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe

V3.4는 WindowsApps\python.exe를 직접 사용하지 않습니다.
