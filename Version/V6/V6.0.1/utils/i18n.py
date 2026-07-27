_translations = {
    "Korean": {
        "Home": "홈",
        "Dashboard": "대시보드",
        "PDF": "PDF 관리",
        "PDF Management": "PDF 관리",
        "Translate": "번역",
        "Translation": "번역",
        "OCR": "OCR",
        "OCR settings": "OCR 설정",
        "Export": "내보내기",
        "Export outputs": "내보내기",
        "History": "히스토리",
        "Settings": "설정",
        "About": "정보",
        "Logs": "로그",
        "General": "일반",
        "Appearance": "화면 표시",
        "Performance": "성능",
        "Network": "네트워크",
        "Storage": "저장소",
        "Updates": "업데이트",
        "Advanced": "고급"
    }
}

def tr(text: str) -> str:
    try:
        from models.settings import SettingsManager
        lang = SettingsManager().settings.ui_language
        if lang in _translations:
            return _translations[lang].get(text, text)
    except Exception:
        pass
    return text
