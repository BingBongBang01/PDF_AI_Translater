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
pip install -r requirements.txt        # pymupdf, anthropic, google-genai
```

## 설치

```bash
pip install -r requirements.txt        # pymupdf, anthropic, google-genai, openai
```

### API 키 — 여러 provider를 한 `api.txt`에 섞어서 사용

`api.txt`에 계정/서비스별 키를 한 줄에 하나씩 넣으면 **provider가 키 형태로 자동 판별**된다.
`--provider`를 지정하지 않으면 파일에 있는 모든 provider의 키를 섞어서 하나의 풀로 순환 사용한다.

```
# api.txt 예시 — Gemini 계정 5개 + OpenAI 1개 + Anthropic 1개
AIza...구글계정1키
AIza...구글계정2키
AIza...구글계정3키
AIza...구글계정4키
AIza...구글계정5키
sk-...OpenAI키
sk-ant-...Anthropic키
```

판별 규칙: `sk-ant-` → Anthropic, `AIza`/`AQ.` → Gemini, `sk-` → OpenAI(Anthropic 접두사가 더 구체적이라 먼저 검사). 모호하면 `gemini:AIza...`처럼 `provider:키` 형식으로 명시할 수 있다. `#`으로 시작하는 줄은 주석.

```bash
# api.txt만 있으면 provider 지정 없이 바로 실행 - 파일에 있는 모든 provider를 자동으로 씀
python translate_pdf.py doc.pdf

# 특정 provider만 쓰고 싶으면 명시 (해당 provider 키만 걸러서 사용)
python translate_pdf.py doc.pdf --provider gemini

# 환경변수 방식(콤마로 여러 개, api.txt가 없을 때만 사용됨)
export ANTHROPIC_API_KEY=키1,키2
export GEMINI_API_KEY=키1,키2,키3,키4,키5
export OPENAI_API_KEY=키1
python translate_pdf.py doc.pdf
```

`api.txt`는 평문 파일이다. 절대 git에 커밋하지 말 것 — 저장소를 쓴다면 `.gitignore`에 `api.txt`를 추가한다. 여러 계정/여러 유료 서비스를 한 문서에 이어붙여 쓰는 것이 각 서비스 약관상 문제없는지는 직접 확인할 것.

### provider별 기본 모델

| provider | 기본 모델 | 비고 |
|---|---|---|
| anthropic | `claude-sonnet-4-6` | 대량은 `claude-haiku-4-5`, 고품질은 `claude-opus-4-8` |
| gemini | `gemini-2.5-flash` | AI Studio 대시보드에서 RPM/TPM/RPD가 실제로 0이 아닌지 먼저 확인 (무료/저티어는 Pro 계열이 막혀 있는 경우가 많음) |
| openai | `gpt-5.4-mini` | OpenAI가 일반 번역 대량 작업에 권장하는 비용/품질 균형 모델(고정밀이 필요하면 `gpt-5.5`) |

`--model-anthropic` / `--model-gemini` / `--model-openai`로 provider별 모델을 각각 override할 수 있다. `--model`은 `--provider`를 단일 provider로 명시했을 때만 유효하다(여러 provider를 섞어 쓰면 어느 provider에 적용할지 모호해지므로 무시됨).

### 여러 계정/여러 provider 순환 + 할당량 소진 시 자동 전환

동작 순서 (api.txt에 적은 순서를 그대로 따름):

1. 첫 번째 키로 계속 요청
2. **분당 제한(RPM) 같은 일시적 429**: 대기 없이 바로 다음 키로 전환. 살아있는 키를 모두 한 바퀴 돌았는데도 막히면 그때 서버가 알려준 대기시간만큼 자고 다시 처음부터
3. **일일 할당량(RPD)·크레딧 소진 같은 영구적 429**: 해당 키를 이번 실행에서 완전히 제외하고 다음 키로 즉시 전환 (일일 한도는 기다려도 곧 안 풀리므로)
4. **모든 키가 영구 소진**되면 그 시점에서 번역을 중단하고, 남은 페이지는 원문 그대로 둔 채 지금까지 번역된 부분만 저장

영구/일시적 판별은 오류 메시지 휴리스틱(`PerDay`, `insufficient_quota`, `credit balance`, `billing` 등)이라 완벽하지 않을 수 있다 — 오탐이 있으면 `api.txt`에서 해당 키를 직접 빼면 된다.

## 이어서 번역 (출력 파일명 규칙)

출력 파일명에 번역 완료/미완료 페이지 범위가 자동으로 붙는다.

- 전체 완료: `<원본이름>_translated_001-033.pdf`
- 중간에 중단(할당량 전부 소진): `<원본이름>_translated_001-019_untranslated_020-033.pdf`
- 파일명이 너무 길면 자동으로 축약: `_translated`→`_T`, `_untranslated`→`_unT`

할당량이 회복된 뒤, **이 출력 파일을 그대로 다시 입력으로 넣으면** 파일명에서 미번역 구간(`020-033`)을 자동으로 읽어 그 페이지만 이어서 번역하고, 완료되면 파일명이 갱신된다(`_untranslated`가 없어지면 완전히 끝난 것).

```bash
# 1차 실행 -> 중간에 할당량 소진 -> doc_translated_001-019_untranslated_020-033.pdf 생성됨
python translate_pdf.py doc.pdf

# 다음 날 그대로 재실행만 하면 자동으로 020-033만 이어서 번역
python translate_pdf.py doc_translated_001-019_untranslated_020-033.pdf
```

이미 번역된 001-019페이지는 다시 추출/재번역하지 않는다(파일명으로 `--pages`가 자동 설정되어 해당 구간만 건드림). `-o`로 출력 파일명을 직접 지정하면 이 자동 이름 생성은 건너뛴다.

Gemini/OpenAI 사용 시 주의: 번역 엔진 프롬프트(`prompts/`)는 원래 Anthropic Messages API의 `system`/`user` 2단 구조로 작성됐다. Gemini는 `system_instruction`/`contents`, OpenAI는 `system`/`user` role 메시지로 매핑하고 둘 다 JSON 출력 강제(`response_mime_type`/`response_format`)를 걸어뒀지만, 실제 키로 배치 1개 정도는 직접 돌려 출력 스키마가 어긋나지 않는지 확인할 것 — 이 환경에는 세 provider 모두 실제 키가 없어 mock 및 시뮬레이션 테스트까지만 검증했다.

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
| `--provider` | (자동/전체) | `anthropic`/`gemini`/`openai` 중 하나로 제한. 미지정 시 api.txt의 모든 provider 혼합 |
| `--api-key-file` | ./api.txt 자동탐색 | 여러 provider 키를 한 줄씩. 형태로 자동판별, `provider:키`로 명시도 가능 |
| `--model` | — | 단일 provider일 때만 유효한 모델 오버라이드 |
| `--model-anthropic` / `--model-gemini` / `--model-openai` | provider별 기본값 | 각 provider에 쓸 모델 개별 지정 |
| `--doc-type`, `--style`, `--domain`, `--title`, `--instructions` | — | 프롬프트의 문서 메타데이터 치환 |
| `--glossary` | — | `.json`(`{"src":"dst"}`) 또는 `.csv`/`.txt`(`src,dst` 혹은 `src => dst`) |
| `--pages` | 전체 | `"1-3,7"` 형식. 나머지 페이지는 원문 유지 |
| `--batch-chars` / `--batch-segs` | 3500 / 25 | 배치 크기. 실패가 잦으면 줄일 것 |
| `--max-attempts` | 3 | 일반 오류(429 제외) 재시도 횟수 |
| `--min-interval` | 0 | 요청 사이 최소 간격(초). 분당 요청 제한(RPM) 예방용 (예: `--min-interval 8`) |
| `--max-rate-limit-retries` | 0(무제한) | 429(할당량 초과) 전용 재시도 상한. 서버가 알려준 대기시간만큼 자동으로 자고 재시도 |
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

## 다른 API 제공자 추가/교체

이미 Anthropic/Gemini/OpenAI 세 곳을 지원한다. 네 번째 provider를 추가하려면:
`build_client()`(클라이언트 생성), `call_llm()`이 분기하는 `call_<provider>()`(호출), `DEFAULT_MODELS`(기본 모델),
`detect_provider()`(키 형태 판별 prefix)만 건드리면 된다. 프롬프트 파일과 JSON 스키마는 provider 무관하게 공용이다.
