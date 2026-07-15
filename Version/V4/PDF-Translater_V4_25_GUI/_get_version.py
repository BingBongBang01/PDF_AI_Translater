"""build_exe.bat 전용 헬퍼: translate_pdf.py의 __version__ 값만 안전하게 추출해 표준출력으로 인쇄.
배치파일 안에 복잡한 정규식/따옴표를 직접 넣으면 파싱 오류 위험이 있어 별도 파일로 분리했다."""
import re
import sys
from pathlib import Path

text = Path(__file__).with_name("translate_pdf.py").read_text(encoding="utf-8")
m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
if not m:
    print("ERROR: __version__ not found", file=sys.stderr)
    sys.exit(1)
print(m.group(1))
