PDF Translater v3.1 GUI - Layout Fix

수정 사항
- 원본 PDF의 각 텍스트 줄 bbox를 저장
- 병합된 문단도 원본 줄/블록 경계를 유지
- 번역문을 PDF에 넣기 직전에 원본 줄 폭 비율에 맞춰 재배치
- 원본 문단 bbox 밖으로 확장하지 않고 내부에서만 자동 축소
- 원본 줄 간격을 계산해 번역문의 line-height에 반영
- [4/4] PDF 저장 완료 후 비핵심 후처리 종료코드 1이 GUI에 오류로 표시되는 문제 보정
- 기존 API/NPU/모델/배치/세그먼트/max_tokens GUI 유지

사용
1. 기존 v2.91 프로젝트의 prompts 폴더를 이 폴더에 복사
2. python gui.py 로 테스트
3. build_exe.bat 실행
4. dist\PDF-Translater-v3.1\PDF-Translater-v3.1.exe 실행
