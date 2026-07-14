# pdf-translator

Anthropic Claude API 기반 **레이아웃 보존 PDF 번역기**.
원문 PDF의 텍스트를 추출해 Claude로 번역한 뒤, 원래 좌표(bbox)에 번역문을 다시 삽입한다.
기본 설정은 English → Korean이며 `--source-lang` / `--target-lang`으로 임의 언어 지정이 가능하다.

번역 엔진의 동작 규칙은 `prompts/system_prompt.txt`(시스템 프롬프트)와
`prompts/user_template.txt`(요청 템플릿)에 정의되어 있다. 두 파일을 수정하면 코드 변경 없이
번역 정책을 바꿀 수 있다.

## 동작 원리

PDF는 리플로우(reflow) 문서가 아니라 좌표 기반 포맷이므로, 문서를 재조판하는 대신
"같은 좌표에 덮어쓰기" 전략을 쓴다.

```
input.pdf
 → [1] 추출   PyMuPDF get_text("dict") — 블록별 텍스트 + bbox + 폰트크기/색/굵기
 → [2] 배치   segment_id(page_001_block_003) 부여, 기본 3,500자 단위 배치
 → [3] 번역   프롬프트 템플릿 치환 → Messages API → JSON 파싱 → 누락분 자동 재요청
 → [4] 재구성 원문 redaction 제거(이미지·배경·선 보존) → 같은 bbox에 insert_htmlbox 삽입
              (한글 등 CJK는 폰트 폴백으로 처리, 번역문이 길면 자동 축소)
 → output.pdf
```

숫자·기호만 있는 블록(표 수치, 페이지 번호 등)은 API로 보내지 않고 원문을 그대로 유지한다
(`--translate-all`로 비활성화 가능). 배치마다 직전 번역 쌍을 PREVIOUS CONTEXT로 전달해
용어 일관성을 유지한다.

## 설치

```bash
pip install -r requirements.txt        # pymupdf, anthropic
export ANTHROPIC_API_KEY=sk-ant-...    # https://platform.claude.com 에서 발급
```

## 사용법

```bash
# 0) API 비용 없이 파이프라인/폰트/레이아웃 먼저 검증 (권장)
python translate_pdf.py doc.pdf -o doc_mock.pdf --mock

# 1) 기본: 영어 → 한국어
python translate_pdf.py doc.pdf -o doc_ko.pdf

# 2) 다른 언어 조합
python translate_pdf.py doc.pdf --source-lang Japanese --target-lang Korean
python translate_pdf.py doc.pdf --source-lang Korean  --target-lang English

# 3) 큰 문서: 일부 페이지로 먼저 품질 확인 후 전체 실행
python translate_pdf.py doc.pdf --pages "1-3" -o test.pdf

# 4) 번역 결과를 JSON으로 저장해 두면, 레이아웃만 다시 조정할 때 API 재호출 불필요
python translate_pdf.py doc.pdf --export-json trans.json -o v1.pdf
python translate_pdf.py doc.pdf --import-json trans.json --font-scale 0.9 -o v2.pdf

# 5) 용어집 강제 적용
python translate_pdf.py doc.pdf --glossary examples/glossary.example.json
```

## 주요 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--source-lang` / `--target-lang` | English / Korean | 언어는 자유 텍스트(프롬프트로 전달) |
| `--model` | claude-sonnet-4-6 | 대량 문서는 `claude-haiku-4-5`(저비용), 고품질은 `claude-opus-4-8` |
| `--doc-type`, `--style`, `--domain`, `--title`, `--instructions` | — | 프롬프트의 문서 메타데이터 치환 |
| `--glossary` | — | `.json`(`{"src":"dst"}`) 또는 `.csv`/`.txt`(`src,dst` 혹은 `src => dst`) |
| `--pages` | 전체 | `"1-3,7"` 형식. 나머지 페이지는 원문 유지 |
| `--batch-chars` / `--batch-segs` | 3500 / 25 | 배치 크기. 실패가 잦으면 줄일 것 |
| `--font-scale` | 1.0 | 번역문이 자주 잘리면 0.9~0.95 권장 |
| `--temperature` | 0.0 | 샘플링 파라미터 미지원 모델이면 자동 제거 후 재시도 |
| `--mock` / `--dry-run` | — | API 없이 검증 / 추출 목록만 출력 |
| `--export-json` / `--import-json` | — | 번역 캐시 저장 / 재사용 |

## 검증 방법

```bash
python examples/make_sample_pdf.py                       # 영문 샘플 생성
python translate_pdf.py examples/sample_en.pdf --mock -o out.pdf
```

정상 기준:
1. 로그에 `추출: 1페이지, 텍스트 블록 8개 (번역 대상 6, 원문 유지 2)` 출력
2. `[4/4] 재구성 완료` 출력, out.pdf에서 각 블록 앞에 `[모의 번역]` 접두어가 원래 위치·크기·색으로 표시
3. 숫자 라인 `4789 24 16777216`과 페이지 번호는 변경 없음

실제 API 경로는 키 설정 후 동일 명령에서 `--mock`만 제거하면 된다.
`--export-json`으로 저장한 JSON에서 원문↔번역문 대응을 직접 검수할 수 있다.

## 한계 (사실)

- **텍스트 레이어가 없는 스캔 PDF는 번역 불가.** OCR(예: ocrmypdf)로 텍스트 레이어를 먼저 입힌 뒤 사용.
- 이미지 안에 그려진 글자(다이어그램 라벨 등)는 추출되지 않으므로 번역되지 않는다.
- 번역문이 원문보다 길면 해당 블록 글자 크기가 자동 축소된다(최소 원래 크기의 15%). 한국어는 보통 영어보다 짧아 문제가 드물다.
- 세로쓰기, 회전된 텍스트, 복잡한 다단 레이아웃은 배치 순서와 배치 위치가 어긋날 수 있다.
- 원본 폰트가 아닌 폴백 폰트(sans-serif 계열)로 재삽입되므로 서체 자체는 바뀐다.

## 비용 주의

비용은 (원문 토큰 + 번역 토큰 + 배치마다 반복 전송되는 프롬프트) × 모델 단가에 비례한다.
큰 문서는 반드시 `--pages`로 1~3페이지 먼저 돌려 품질과 비용을 확인할 것.
정확한 단가는 https://platform.claude.com/docs 의 Pricing 문서를 확인.

## 다른 API 제공자로 교체

API 의존부는 `translate_pdf.py`의 `get_client()`와 `call_claude()` 두 함수뿐이다.
OpenAI 등으로 바꾸려면 이 두 함수만 해당 SDK 호출로 교체하면 된다
(프롬프트 파일과 JSON 스키마는 제공자 무관).
