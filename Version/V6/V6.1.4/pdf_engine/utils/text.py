import re

def _clean_pua_characters(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\ufffd", "-").replace("\u2022", "-").replace("•", "-").replace("\x00", "")
    res = []
    for ch in text:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF:
            res.append("-")
        elif cp < 32 and ch not in ("\n", "\r", "\t"):
            continue
        else:
            res.append(ch)
    cleaned = "".join(res)
    cleaned = re.sub(r"[-+\s]*-[-+\s]*", " - ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()
