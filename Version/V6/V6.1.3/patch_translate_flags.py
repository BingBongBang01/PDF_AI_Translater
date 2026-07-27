import os

with open('translate_pdf.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add args
args_old = 'ap.add_argument("--glossary-profile", default="auto", help="용어집 프로필 (기본: auto - 문서 문맥 자동 분석)")'
args_new = '''ap.add_argument("--glossary-profile", default="auto", help="용어집 프로필 (기본: auto - 문서 문맥 자동 분석)")
    ap.add_argument("--disable-glossary", action="store_true", help="용어집 비활성화")
    ap.add_argument("--disable-validation", action="store_true", help="엄격한 구문 검증 비활성화")
    ap.add_argument("--disable-placeholder", action="store_true", help="플레이스홀더 보호 비활성화")
    ap.add_argument("--disable-context-detection", action="store_true", help="문맥 자동 감지 비활성화")
    ap.add_argument("--disable-style-fix", action="store_true", help="포스트프로세싱 텍스트 정규화 비활성화")'''

if '--disable-glossary' not in content:
    content = content.replace(args_old, args_new)

with open('translate_pdf.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched translate_pdf.py for feature flags')
