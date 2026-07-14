PDF Translater v3.1 GUI

핵심 수정:
- EXE에서 sys.executable로 translate_pdf.py를 재실행하던 구조 제거
- translate_pdf 모듈을 EXE 내부 프로세스에서 직접 실행
- PyMuPDF/pypdf/API SDK를 PyInstaller collect-all로 포함
- stdout/stderr를 GUI 로그창으로 전달해 Windows 콘솔 인코딩 깨짐 방지
- API 키 임시 파일은 종료 후 삭제

사용:
1. v2.91 프로젝트의 prompts 폴더를 이 폴더에 복사
2. python gui.py 로 먼저 테스트
3. build_exe.bat 실행
4. dist\PDF-Translater-v3.1\PDF-Translater-v3.1.exe 실행
