PDF Translater v2.92 GUI

1. 기존 v2.91 프로젝트의 prompts 폴더를 이 폴더에 복사합니다.
2. gui.py를 Python으로 실행해 GUI를 먼저 테스트합니다.
3. build_exe.bat를 더블클릭하면 Windows EXE를 빌드합니다.
4. 결과: dist\PDF-Translater-v2.92\PDF-Translater-v2.92.exe

주의:
- Lemonade NPU를 쓸 경우 Lemonade Server가 설치/실행 가능해야 합니다.
- API 키는 실행 중 임시 txt에 기록되고 종료 시 삭제됩니다.
- GUI는 최신 translate_pdf.py를 별도 프로세스로 호출하므로 CLI 엔진을 유지합니다.
