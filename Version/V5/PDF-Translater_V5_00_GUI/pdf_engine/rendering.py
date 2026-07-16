"""
번역문을 PDF에 다시 삽입한다: redaction(원문 지우기), 세로쓰기 전용 수동 렌더러,
자동 축소 삽입, OCR 세그먼트의 배경색 추정/안전성 검사(만화 등 복잡한 그림 보호)를 담당.
"""
from __future__ import annotations

import math
import html as html_mod
import re
from collections import defaultdict

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

from .segment import Segment

def hex_to_rgb01(hx: str) -> tuple:
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def apply_redactions_safe(page) -> None:
    """텍스트만 제거하고 이미지/벡터 그래픽은 보존. 구버전 시그니처 폴백 포함."""
    try:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    except (TypeError, AttributeError):
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)


def _normalize_translation_text(text: str) -> str:
    """모델이 만든 불필요한 공백만 정리하고 명시적 줄바꿈은 보존한다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _insert_vertical_text_manual(page, rect, text: str, seg: Segment, font_scale: float) -> bool:
    """
    세로쓰기(일본어/한국어 종서) 전용 렌더러.

    insert_htmlbox의 rotate=90 파라미터는 텍스트 줄 전체를 하나의 강체로 90도
    돌려버려서 글자 자체가 옆으로 누운 채 나온다(고개를 기울여야 읽히고, 읽는
    방향도 위->아래가 아니라 회전된 좌->우가 됨) - 진짜 세로쓰기가 아니다.
    CSS 'writing-mode: vertical-rl'도 mupdf Story가 지원하지 않는 것으로 확인됐다.
    그래서 글자를 하나씩 직접 배치해 각 글자는 똑바로 세운 채 위->아래로 쌓는다
    (실제 세로쓰기와 동일한 방식). 한 컬럼(세로줄)에 다 안 들어가면 오른쪽에서
    왼쪽으로 새 컬럼을 만들어 이어간다(전통적 세로쓰기 진행 방향과 동일 - 원본도
    이 순서로 배치돼 있었다). 원래 bbox의 상단에 딱 붙여 시작해 원본과 같은
    위치를 유지한다.
    """
    plain = _normalize_translation_text(text).replace("\n", "")
    # 세로쓰기에서는 공백이 별도 칸을 차지하지 않아야 한다 - 공백마다 한 칸씩 비우면
    # (원래 코드가 그랬음) 번역문에 있는 여러 개의 공백(한국어는 띄어쓰기가 잦음)만큼
    # 예상보다 훨씬 많은 세로 공간이 필요해져서, 텍스트가 여러 조각으로 쪼개진 것처럼
    # 큰 간격이 생기거나(원래 bbox 상단에 붙어야 할 텍스트가 아래로 밀려 보임의 원인),
    # 그 공간을 맞추려다 폰트가 불필요하게 축소되는 문제가 있었다. 완전히 제거한다.
    plain = plain.replace(" ", "").replace("\u3000", "")
    if not plain:
        return True

    rect = pymupdf.Rect(rect)
    color = hex_to_rgb01(seg.color)
    base_fs = max(4.0, seg.font_size * font_scale)
    min_fs = max(3.5, base_fs * 0.4)

    size = base_fs
    while size >= min_fs:
        row_h = size * 1.15   # 글자 하나가 차지하는 세로 칸 높이
        col_w = size * 1.15   # 컬럼(세로줄) 하나의 가로 폭
        rows_per_col = max(1, int(rect.height // row_h))
        n_cols = math.ceil(len(plain) / rows_per_col)
        needed_w = n_cols * col_w
        if needed_w <= rect.width + 0.5:
            try:
                idx = 0
                for c_i in range(n_cols):
                    # 오른쪽 끝 컬럼부터 시작해 왼쪽으로 진행 (세로쓰기 전통적 읽기 순서)
                    x = rect.x1 - col_w * (c_i + 1) + col_w * 0.1
                    y = rect.y0 + size  # 첫 글자의 baseline (bbox 상단에 붙임)
                    for _ in range(rows_per_col):
                        if idx >= len(plain):
                            break
                        ch = plain[idx]
                        page.insert_text((x, y), ch, fontsize=size,
                                         fontname="korea", color=color)
                        y += row_h
                        idx += 1
                    if idx >= len(plain):
                        break
                return True
            except Exception:
                pass
        size *= 0.92
    return False


def _insert_text_in_rect(page, rect, text, seg: Segment, font_scale: float) -> bool:
    """
    V3.8: 원래 bbox 밖으로 확장하지 않는다.
    확장은 인접 목차 항목/다단 텍스트를 침범해 겹침을 만들기 때문이다.
    원본 블록의 위치/폭/높이를 고정하고 글꼴 크기만 단계적으로 줄인다.
    """
    text = _normalize_translation_text(text)
    if not text:
        return True

    rect = pymupdf.Rect(rect)
    base_fs = max(4.0, seg.font_size * font_scale)
    min_fs = max(3.5, base_fs * 0.45)
    color = hex_to_rgb01(seg.color)
    weight = "bold" if seg.bold else "normal"

    # 세로쓰기는 전용 수동 렌더러를 최우선 사용 (아래 rotate=90 방식은 글자가
    # 통째로 누워버리는 문제가 있어 폴백으로만 남겨둠).
    if seg.vertical:
        if _insert_vertical_text_manual(page, rect, text, seg, font_scale):
            return True

    # HTML 삽입: CJK 폰트 폴백과 자동 맞춤을 우선 사용.
    if hasattr(page, "insert_htmlbox"):
        body = html_mod.escape(text).replace("\n", "<br>")
        # pt를 사용해 PDF 원본 font_size와 단위를 맞춘다 (기존 px 사용은 크기 왜곡 원인).
        css = ("* {margin:0;padding:0;font-family:sans-serif;"
               f"font-size:{base_fs:.2f}pt;color:{seg.color};font-weight:{weight};"
               "line-height:1.08;}")
        # 주의: CSS 'writing-mode: vertical-rl'는 mupdf Story가 지원하지 않는다(CSS2 수준까지만
        # 지원 확인됨). rotate=90은 줄 전체를 강체로 돌려 글자가 누운 채 나오므로
        # (실사용 테스트에서 확인) 세로쓰기의 정식 방법이 아니다 - 위 수동 렌더러 실패시의
        # 최후 폴백으로만 사용한다.
        rotate = 90 if seg.vertical else 0
        try:
            spare, scale = page.insert_htmlbox(
                rect, f"<div>{body}</div>", css=css, scale_low=0.45, rotate=rotate
            )
            if spare is None or spare >= 0:
                return True
        except Exception:
            pass

    # 폴백: bbox 안에 들어갈 때까지 점진 축소.
    size = base_fs
    while size >= min_fs:
        try:
            rc = page.insert_textbox(
                rect, text, fontsize=size, fontname="korea",
                color=color, lineheight=1.08
            )
            if rc >= 0:
                return True
        except Exception:
            pass
        size *= 0.92
    return False


def insert_translated_text(page, seg: Segment, font_scale: float) -> bool:
    # V3.8에서는 물리 블록 병합을 하지 않으므로 항상 원래 bbox 하나에 삽입한다.
    text = (seg.translated or "").replace("|||SUB_SEPARATOR|||", "\n").strip()
    return _insert_text_in_rect(page, seg.bbox, text, seg, font_scale)


def _analyze_ocr_background(page, bbox) -> tuple[bool, tuple, float]:
    """OCR 삽입 안전성 검사: 만화에서는 밝고 균일한 말풍선/여백만 수정 허용."""
    try:
        rect=pymupdf.Rect(bbox)
        pix=page.get_pixmap(clip=rect,dpi=96,alpha=False)
        n=max(1,pix.n); raw=pix.samples; vals=[]; colors=[]
        pixels=max(1,len(raw)//n); stride=max(1,pixels//3000)
        for px in range(0,pixels,stride):
            i=px*n
            if i+2>=len(raw): break
            rgb=(raw[i],raw[i+1],raw[i+2])
            vals.append(sum(rgb)/3)
            colors.append(tuple((v//32)*32 for v in rgb))
        if len(vals)<12:return False,(1,1,1),0.0
        mean=sum(vals)/len(vals)
        bright=sum(v>=210 for v in vals)/len(vals)
        # OCR bbox에는 검은 글자 픽셀이 있으므로 dominant color만으로 판정하지 않는다.
        # 평균 밝기와 밝은 픽셀 비율을 함께 사용해 그림 영역을 차단한다.
        safe=mean>=185 and bright>=0.58
        return safe,(1,1,1),bright
    except Exception:
        return False,(1,1,1),0.0



def rebuild_pdf(doc, segments: list[Segment], font_scale: float) -> int:
    by_page: dict[int, list[Segment]] = defaultdict(list)
    for s in segments:
        if s.needs_translation and s.translated:
            by_page[s.page].append(s)

    truncated = 0
    for pno in sorted(by_page):
        page = doc[pno]
        # OCR로 얻은 세그먼트는 원본에 텍스트 레이어가 없다(이미지 위의 픽셀일 뿐이라
        # redact로 지울 대상 자체가 없음). 대신 배경색으로 그 영역을 덮어 원문 픽셀을
        # 가린 뒤 번역문을 얹는다 - 안 그러면 원어 글자가 번역문과 겹쳐 보인다.
        ocr_segs = [s for s in by_page[pno] if s.is_ocr]
        redactable = [s for s in by_page[pno] if not s.is_ocr]
        for s in redactable:
            page.add_redact_annot(pymupdf.Rect(s.bbox), fill=False)
        if redactable:
            apply_redactions_safe(page)
        safe_ocr_ids=set()
        for s in ocr_segs:
            safe,bg,uniformity=_analyze_ocr_background(page,s.bbox)
            if not safe:
                print(f"  [OCR 안전장치] {s.seg_id}: 복잡한 이미지 영역 "
                      f"(단색도={uniformity:.2f}) -> 원본 보호를 위해 덮기/번역문 삽입 생략")
                continue
            pad=max(0.5,min(1.5,s.font_size*0.08))
            cover_rect=pymupdf.Rect(s.bbox)+(-pad,-pad,pad,pad)
            page.draw_rect(cover_rect,color=None,fill=bg,overlay=True)
            safe_ocr_ids.add(s.seg_id)
        for s in by_page[pno]:
            if s.is_ocr and s.seg_id not in safe_ocr_ids:
                continue
            if not insert_translated_text(page, s, font_scale):
                truncated += 1
                print(f"  [경고] {s.seg_id}: 번역문이 원래 영역보다 길어 최대 축소로도 넘칠 수 있음")
    return truncated