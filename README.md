# PDF-AI-Translator

A tool that translates PDF documents using AI (Claude / Gemini / GPT / local NPU) while preserving the original layout.
It keeps the original font size, position, tables, color, and boldness as close as possible, replacing only the text — making it easy to compare against the source.

Both a CLI (command-line) version and a GUI (Windows desktop app) version are provided.

---

## Key Features

- **Layout-preserving translation**: Keeps the original PDF's text position, size, color, and boldness while replacing only the text
- **Multiple AI providers at once**: Register Anthropic Claude / Google Gemini / OpenAI GPT keys simultaneously — when one key's quota is exhausted, it automatically switches to the next key/provider and keeps going
- **Local NPU fallback**: Using AMD Ryzen AI (XDNA NPU) + Lemonade Server, translation can continue on the local NPU even after all cloud API quotas are exhausted (can complete a full document without internet/API keys)
- **Table/multi-column layout protection**: Automatically detects tables or multi-column text where different pieces of text sit close together, and places each piece back at its own original position so cells don't break
- **Resume translation**: If translation is interrupted or only partially completed, simply feed the output file back in — it automatically detects the untranslated ranges and continues from there
- **Glossary support**: Force specific translations for organization/project-specific terminology
- **GUI included**: A desktop app with API key management, progress display (remaining time / page progress), stop/resume, and automatic source-language detection

---

## Requirements

- Python 3.12 (3.13/3.14 may not be supported by some dependencies yet)
- Windows 10/11 (the GUI/EXE is Windows-only; the CLI works on Windows/Linux/macOS)
- At least one of the following:
  - An Anthropic / Google Gemini / OpenAI API key
  - An AMD Ryzen AI 300-series chip (XDNA NPU) + [Lemonade Server](https://github.com/lemonade-sdk/lemonade)

---

## Installation

```bash
git clone https://github.com/<your-id>/PDF-AI-Translator.git
cd PDF-AI-Translator
pip install -r requirements.txt
```

### Running the GUI on Windows

```
run_gui.bat
```

Or to build a standalone executable:

```
build_exe.bat
```

Once the build finishes, a single file `dist\PDF-Translater-vX.X.exe` is created. This one file can be run without any separate installation.

---

## CLI Usage

### 1. Set up API keys

Create an `api.txt` file in the project folder with one key per line. The provider is automatically detected from the key format.

```
AIzaSy...          # Gemini (auto-detected)
sk-ant-...         # Anthropic (auto-detected)
sk-...             # OpenAI (auto-detected)
gemini:AIzaSy...   # explicitly specify the provider
```

Or use environment variables instead:

```bash
export GEMINI_API_KEY=...
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
```

### 2. Run the translation

```bash
python translate_pdf.py document.pdf --source-lang English --target-lang Korean
```

By default, the output is saved in the same folder as `document_translated_...pdf`.

### 3. Commonly used options

| Option | Description |
|---|---|
| `--pages 1-10,20-25` | Translate only specific page ranges |
| `--source-lang` / `--target-lang` | Source/target language (`auto` for automatic detection) |
| `--glossary glossary.json` | Specify a glossary file |
| `-o output.pdf` | Specify the output filename directly |
| `--local-npu` | Automatically fall back to the local NPU once all cloud APIs are exhausted |
| `--model-local` | Specify the local NPU model (default: gemma4-it-e2b-FLM) |
| `--batch-chars` / `--batch-segs` | Max characters / segments per batch |
| `--dry-run` | Check extraction results only, without translating |
| `--mock` | Test the pipeline without making any API calls |

Run `python translate_pdf.py --help` for the full list of options.

### 4. Resuming translation

If only part of the document was translated before being interrupted, the untranslated ranges are automatically recorded in the filename.

```
document_translated_001-050_untranslated_010-020.pdf
```

Simply feed this file back in as input, and only the untranslated ranges will be translated.

```bash
python translate_pdf.py "document_translated_001-050_untranslated_010-020.pdf"
```

If there are many untranslated ranges, the filename is abbreviated using a `-MULTIn` suffix, and the exact page list is saved in a `.progress.json` file in the same folder. When resuming, this JSON file must be kept alongside the PDF.

---

## Local NPU (AMD Ryzen AI) Usage

You can use the local NPU without any cloud API, or as a fallback once your API quota is exhausted.

1. Install [Lemonade Server](https://github.com/lemonade-sdk/lemonade/releases/latest)
2. Download a model of your choice (e.g. `gemma4-it-e2b-FLM`)
3. Run with the following option

```bash
python translate_pdf.py document.pdf --local-npu
```

Translation works with `--local-npu` alone, even without any API keys. If the Lemonade server isn't already running, it will be started automatically in the background.

---

## GUI Usage

1. Run `run_gui.bat` (or the built EXE)
2. Select the input PDF
3. Enter the API key(s) you want to use (automatically saved and reloaded on the next run)
4. Choose the source/target language (automatic detection available)
5. Enable the local NPU checkbox if needed
6. Click **Start Translation**

While translating, you can check the progress percentage, estimated time remaining, and the page currently being processed. Clicking **Stop** finishes translating the current portion and saves the rest of the document untranslated (so you can resume later).

Clicking **Install Prerequisites** automatically checks/installs Python 3.12, Lemonade Server, and any required packages.

---

## Known Limitations

- Scanned (image-only) PDFs are not supported. You'll need to add a text layer via OCR first.
- Small local NPU models may produce lower translation quality (especially terminology consistency) than large cloud models.
- Very complex layouts (multi-column magazines, rotated text, etc.) may have slightly misaligned text placement.

---

## Contributing

Bug reports and suggestions are welcome via Issues. Pull requests are also welcome.

---

## License

This project is licensed under the [CC BY-NC 4.0](LICENSE) license.
Commercial use of this software is strictly prohibited.


---

# PDF-AI-Translator

AI(Claude / Gemini / GPT / 로컬 NPU)를 이용해 PDF 문서의 레이아웃을 그대로 유지하면서 번역하는 프로그램입니다.
원본의 글자 크기, 위치, 표, 색상, 굵기를 최대한 보존한 채로 텍스트만 번역해 원본과 나란히 비교하기 쉽습니다.

CLI(명령줄) 버전과 GUI(윈도우 프로그램) 버전을 모두 제공합니다.

---

## 주요 기능

- **레이아웃 보존 번역**: 원본 PDF의 텍스트 위치·크기·색상·굵기를 그대로 유지한 채 텍스트만 교체
- **여러 AI 제공자 동시 사용**: Anthropic Claude / Google Gemini / OpenAI GPT 키를 동시에 등록해두면, 하나의 할당량이 소진되어도 자동으로 다음 키/제공자로 전환하며 계속 번역
- **로컬 NPU 폴백**: AMD Ryzen AI(XDNA NPU) + Lemonade Server를 이용해, 클라우드 API가 전부 소진되어도 로컬 NPU로 이어서 번역 (인터넷/API 키 없이도 완주 가능)
- **표/다단 레이아웃 보호**: 표나 여러 컬럼처럼 서로 다른 텍스트가 근접한 경우, 셀/컬럼이 깨지지 않도록 자동 인식해 개별 위치에 맞춰 배치
- **이어서 번역**: 중간에 중단되거나 일부만 번역해도, 결과 파일을 다시 입력하면 미번역 구간만 자동으로 감지해 이어서 진행
- **용어집(Glossary) 지원**: 프로젝트/조직에서 쓰는 고유 용어를 지정한 번역으로 강제 가능
- **GUI 제공**: API 키 관리, 진행률 표시(남은 시간/페이지 진행 상황), 중단/재개, 언어 자동 인식 등을 지원하는 데스크톱 프로그램

---

## 요구 사항

- Python 3.12 (3.13/3.14는 일부 의존 패키지 미지원 가능성 있음)
- Windows 10/11 (GUI/EXE는 Windows 전용, CLI는 Windows/Linux/macOS에서 동작)
- 아래 중 최소 하나:
  - Anthropic / Google Gemini / OpenAI API 키
  - AMD Ryzen AI 300 시리즈(XDNA NPU) + [Lemonade Server](https://github.com/lemonade-sdk/lemonade)

---

## 설치

```bash
git clone https://github.com/<your-id>/PDF-AI-Translator.git
cd PDF-AI-Translator
pip install -r requirements.txt
```

### Windows용 GUI 실행

```
run_gui.bat
```

또는 실행 파일로 빌드하려면:

```
build_exe.bat
```

빌드가 끝나면 `dist\PDF-Translater-vX.X.exe` 파일 하나만 생성됩니다. 이 파일만 있으면 별도 설치 없이 실행할 수 있습니다.

---

## 사용법 (CLI)

### 1. API 키 준비

프로젝트 폴더에 `api.txt` 파일을 만들고 한 줄에 키를 하나씩 넣습니다. 키 형태로 provider가 자동 판별됩니다.

```
AIzaSy...          # Gemini (자동 판별)
sk-ant-...         # Anthropic (자동 판별)
sk-...             # OpenAI (자동 판별)
gemini:AIzaSy...   # provider를 직접 명시하고 싶을 때
```

또는 환경 변수로도 지정할 수 있습니다.

```bash
export GEMINI_API_KEY=...
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
```

### 2. 번역 실행

```bash
python translate_pdf.py 문서.pdf --source-lang English --target-lang Korean
```

기본적으로 원본과 같은 폴더에 `문서_translated_...pdf` 형태로 결과가 저장됩니다.

### 3. 자주 쓰는 옵션

| 옵션 | 설명 |
|---|---|
| `--pages 1-10,20-25` | 특정 페이지 범위만 번역 |
| `--source-lang` / `--target-lang` | 원문/번역 언어 (자동 인식은 `auto`) |
| `--glossary glossary.json` | 용어집 파일 지정 |
| `-o output.pdf` | 출력 파일명 직접 지정 |
| `--local-npu` | 클라우드 API 전부 소진 시 로컬 NPU로 자동 전환 |
| `--model-local` | 로컬 NPU 모델 지정 (기본: gemma4-it-e2b-FLM) |
| `--batch-chars` / `--batch-segs` | 배치당 최대 글자 수 / 세그먼트 수 |
| `--dry-run` | 실제 번역 없이 추출 결과만 확인 |
| `--mock` | API 호출 없이 파이프라인만 테스트 |

전체 옵션은 `python translate_pdf.py --help`로 확인할 수 있습니다.

### 4. 이어서 번역

일부만 번역되고 중단된 경우, 파일명에 미번역 구간이 자동으로 기록됩니다.

```
문서_translated_001-050_untranslated_010-020.pdf
```

이 파일을 그대로 다시 입력하면 미번역 구간만 자동으로 이어서 번역합니다.

```bash
python translate_pdf.py "문서_translated_001-050_untranslated_010-020.pdf"
```

미번역 구간이 많아지면 파일명이 `-MULTIn` 형태로 축약되고, 정확한 페이지 목록은 같은 폴더의 `.progress.json` 파일에 저장됩니다. 이어서 번역할 때는 이 JSON 파일도 PDF와 같은 폴더에 있어야 합니다.

---

## 로컬 NPU (AMD Ryzen AI) 사용법

클라우드 API 없이, 또는 API 소진 시 폴백으로 로컬 NPU를 사용할 수 있습니다.

1. [Lemonade Server](https://github.com/lemonade-sdk/lemonade/releases/latest) 설치
2. 원하는 모델 다운로드 (예: `gemma4-it-e2b-FLM`)
3. 아래 옵션으로 실행

```bash
python translate_pdf.py 문서.pdf --local-npu
```

API 키가 없어도 `--local-npu`만으로 번역이 가능합니다. Lemonade 서버가 켜져 있지 않으면 자동으로 백그라운드에서 실행합니다.

---

## GUI 사용법

1. `run_gui.bat` 실행 (또는 빌드한 EXE 실행)
2. 입력 PDF 선택
3. 사용할 API 키 입력 (다음 실행 시 자동으로 저장되어 불러와짐)
4. 원문/번역 언어 선택 (자동 인식 가능)
5. 필요 시 로컬 NPU 체크박스 활성화
6. **번역 시작** 클릭

번역 중 진행률, 예상 남은 시간, 현재 처리 중인 페이지를 확인할 수 있으며, **중단** 버튼을 누르면 현재 처리 중인 부분까지만 번역하고 나머지는 원문 그대로 저장합니다(이어서 번역 가능).

**필수사항 설치** 버튼을 누르면 Python 3.12, Lemonade Server, 필요한 패키지를 자동으로 확인/설치합니다.

---

## 알려진 제한 사항

- 스캔본(이미지) PDF는 지원하지 않습니다. OCR로 텍스트 레이어를 먼저 추가해야 합니다.
- 로컬 NPU 소형 모델은 클라우드 대형 모델보다 번역 품질(특히 전문 용어 일관성)이 낮을 수 있습니다.
- 매우 복잡한 레이아웃(다단 잡지, 회전된 텍스트 등)은 위치가 다소 어긋날 수 있습니다.

---

## 기여

버그 제보나 개선 제안은 이슈로 남겨주세요. Pull Request도 환영합니다.

---

## License

This project is licensed under the [CC BY-NC 4.0](LICENSE) license.
Commercial use of this software is strictly prohibited.

이 프로젝트는 CC BY-NC 4.0 라이선스를 따릅니다. **상업적 용도로의 사용을 금지합니다.**
