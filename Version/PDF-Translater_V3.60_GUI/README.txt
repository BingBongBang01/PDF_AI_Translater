PDF Translater V3.6 GUI

수정 핵심
1. 번역문을 원본 줄 수에 강제로 분배하던 V3.1 방식 제거
2. 원본 블록의 가로 폭과 위치는 유지
3. 번역문은 원본 bbox 안에서 자연스럽게 자동 줄바꿈
4. 공간 부족 시 아래쪽만 제한적으로 확장
5. 폰트 자동 축소 하한을 원본 크기의 72%로 제한
6. 4pt까지 억지 축소하던 동작 제거
7. 병합 블록 사이에 강제 개행을 넣지 않고 공백으로 연결
8. GUI.PY 더블클릭이 WindowsApps Python을 타면 실제 Python 3.12로 새 프로세스 재실행
9. 더 확실한 더블클릭 실행용 PDF-Translater_GUI.cmd 추가
10. 요구사항 설치 버튼 유지

권장 실행
- 가장 확실함: PDF-Translater_GUI.cmd 더블클릭
- Python: py -3.12 gui.py
- EXE 생성: build_exe.bat
