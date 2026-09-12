# -*- coding: utf-8 -*-
"""의사록을 PDF로 출력한다.

reportlab 과 한글 글꼴이 필요하다.  pip install reportlab
글꼴은 운영체제 기본값을 자동으로 찾으며, 환경변수로 지정할 수도 있다.
"""

import random
from typing import Any, Dict, List, Optional, Tuple

from . import fonts
from .model import Minutes, Seal
from .render import _label, _marker, build_flow


def _seal_image(seal: Optional[Seal], rng: random.Random):
    """인영 PIL 이미지를 만든다. Pillow 나 글꼴이 없으면 None."""
    if seal is None:
        return None
    try:
        from .seal import make_seal
        return make_seal(seal.text, rng, size=300, shape=seal.shape)
    except Exception:                       # noqa: BLE001
        return None


def _stamp_image(text: Optional[str], rng: random.Random):
    if not text:
        return None
    try:
        from .seal import make_stamp
        return make_stamp(text, rng)
    except Exception:                       # noqa: BLE001
        return None

A4_WIDTH_MM = 210.0


class PdfUnavailable(RuntimeError):
    """reportlab 이 없거나 한글 글꼴을 찾지 못했을 때."""


def _require_reportlab():
    try:
        import reportlab  # noqa: F401
    except ImportError as exc:
        raise PdfUnavailable(
            "PDF 출력에는 reportlab 이 필요합니다.  pip install reportlab"
        ) from exc


_REGISTERED: Dict[Tuple[str, int], str] = {}


def _register_file(path: str, index: int) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    key = (path, index)
    if key not in _REGISTERED:
        name = f"MG{len(_REGISTERED)}"
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
        _REGISTERED[key] = name
    return _REGISTERED[key]


def _register(family: str, required: str = "") -> Tuple[str, str]:
    """(보통 글꼴 이름, 굵은 글꼴 이름)을 돌려준다.

    required 에 문서에서 쓰는 글자를 넘기면 그 글자를 모두 담은 글꼴을 고른다.
    나눔명조처럼 한자가 없는 글꼴로 한자 문서를 찍어 네모가 나오는 것을 막는다.
    """
    from reportlab.pdfbase import pdfmetrics

    regular = fonts.find_font_for(family, required)
    if not regular:
        raise PdfUnavailable(
            "한글 글꼴을 찾지 못했습니다. 나눔고딕 등을 설치하거나 "
            "환경변수 MINUTES_FONT_GOTHIC 에 .ttf 경로를 지정하세요."
        )
    name = _register_file(*regular)

    bold = fonts.find_bold_for(family, required)
    bold_name = _register_file(*bold) if bold else name
    pdfmetrics.registerFontFamily(name, normal=name, bold=bold_name)
    return name, bold_name


def _document_charset(flow) -> str:
    """문서에 실제로 등장하는 글자를 모아 글꼴 선택에 쓴다."""
    seen = set()

    def eat(value):
        if isinstance(value, str):
            seen.update(value)
        elif isinstance(value, dict):
            for v in value.values():
                eat(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                eat(v)

    for kind, payload in flow:
        eat(payload)
    return "".join(sorted(seen))


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_pdf(m: Minutes, target, seed: int = 0) -> None:
    """target 은 파일 경로 또는 바이너리 스트림."""
    _require_reportlab()

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    class SignBlock(Flowable):
        """직함·성명·날인 표시를 그리고, 그 위에 인영을 겹쳐 찍는다."""

        def __init__(self, rows, font_name, font_size, doc_seed):
            Flowable.__init__(self)
            self.rows = rows
            self.font = font_name
            self.size = font_size
            self.hAlign = "CENTER"
            self.gap = font_size * 2.4
            widths = lambda key: max(                       # noqa: E731
                pdfmetrics.stringWidth(r[key], font_name, font_size) for r in rows)
            self.w_title = widths("title")
            self.w_name = widths("name")
            self.w_mark = widths("mark")
            self.sealed = any(r.get("seal") for r in rows)
            self.row_h = font_size * (3.9 if self.sealed else 2.4)
            self.width = self.w_title + self.gap + self.w_name + self.gap + self.w_mark
            self.height = self.row_h * len(rows)
            self.seals = []
            for i, row in enumerate(rows):
                rng = random.Random(doc_seed * 977 + i)
                image = _seal_image(row.get("seal"), rng)
                if image is None:
                    self.seals.append(None)
                    continue
                side = font_size * rng.uniform(3.3, 3.9)
                name_w = pdfmetrics.stringWidth(row["name"], font_name, font_size)
                # 성명 끝자락에 걸치도록 놓는다. 이름 전체를 덮으면 정답을 확인할 수 없다.
                cx = self.w_title + self.gap + name_w + side * rng.uniform(0.02, 0.18)
                cy = font_size * rng.uniform(0.25, 0.48)
                self.seals.append((ImageReader(image), side, cx, cy))

        def wrap(self, availWidth, availHeight):
            return self.width, self.height

        def draw(self):
            c = self.canv
            name_x = self.w_title + self.gap
            mark_x = name_x + self.w_name + self.gap
            for i, row in enumerate(self.rows):
                baseline = self.height - (i + 1) * self.row_h + self.row_h * 0.35
                c.setFont(self.font, self.size)
                c.drawString(0, baseline, row["title"])
                c.drawString(name_x, baseline, row["name"])
                c.drawString(mark_x, baseline, row["mark"])
                spec = self.seals[i]
                if spec:
                    reader, side, cx, cy = spec
                    c.drawImage(reader, cx - side / 2, baseline + cy - side / 2,
                                side, side, mask="auto")

    s = m.style
    flow = build_flow(m, seed)
    regular, bold = _register(s.font_family, _document_charset(flow))
    fs = s.font_size
    leading = fs * s.leading_ratio

    margin_x, margin_y = 20 * mm, 20 * mm
    content_w = A4[0] - 2 * margin_x

    align = TA_LEFT if s.text_align == "left" else TA_JUSTIFY
    body = ParagraphStyle("body", fontName=regular, fontSize=fs, leading=leading,
                          alignment=align, spaceAfter=fs * 0.35)
    indented = ParagraphStyle("indented", parent=body, leftIndent=7 * mm)
    title_style = ParagraphStyle(
        "title", fontName=bold, fontSize=fs * 1.7, leading=fs * 2.3,
        alignment=TA_CENTER, spaceAfter=10 * mm)
    heading = ParagraphStyle("heading", fontName=bold, fontSize=fs, leading=leading,
                             spaceBefore=fs * 0.7, spaceAfter=fs * 0.3)
    subheading = ParagraphStyle("subheading", parent=heading, spaceBefore=fs * 0.4)
    centered = ParagraphStyle("centered", fontName=regular, fontSize=fs,
                              leading=leading, alignment=TA_CENTER)
    centered_bold = ParagraphStyle("centered_bold", parent=centered, fontName=bold)
    meta = ParagraphStyle("meta", fontName=regular, fontSize=fs, leading=leading * 0.95)
    cell = ParagraphStyle("cell", fontName=regular, fontSize=fs * 0.95,
                          leading=fs * 1.3)
    cell_head = ParagraphStyle("cell_head", parent=cell, fontName=bold)

    story: List[Any] = []

    def para(text: str, style=body):
        story.append(Paragraph(_esc(text), style))

    def width_of(text: str, size: float) -> float:
        return pdfmetrics.stringWidth(str(text), regular, size)

    for kind, payload in flow:
        if kind == "title":
            story.append(Paragraph(_esc(payload), title_style))

        elif kind == "header":
            rows, spans = [], []
            for i, entry in enumerate(payload, start=1):
                label = f"{_marker(s, i)} {_label(s, entry['label'])}:"
                rows.append([Paragraph(_esc(label), meta),
                             Paragraph(_esc(entry["value"]), meta)])
                for line in entry.get("lines", []):
                    rows.append(["", Paragraph(_esc(line), meta)])
                for t, n, mark in entry.get("roster", []):
                    rows.append(["", Paragraph(
                        f"{_esc(t)}&nbsp;&nbsp;&nbsp;{_esc(n)}&nbsp;&nbsp;&nbsp;{_esc(mark)}",
                        meta)])
            label_w = max(width_of(f"{_marker(s, i)} {_label(s, e['label'])}:", fs) + 10
                          for i, e in enumerate(payload, start=1))
            tbl = Table(rows, colWidths=[label_w, content_w - label_w])
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (1, 0), (1, -1), 4),
            ] + spans))
            story.append(tbl)
            story.append(Spacer(1, 6 * mm))

        elif kind == "para":
            para(payload)
        elif kind in ("indent_para", "resolution"):
            para(payload, indented)
        elif kind == "section":
            para(f"[{payload}]", heading)
        elif kind == "item_heading":
            para(payload, subheading)
        elif kind == "agenda_heading":
            para(payload, heading)

        elif kind == "kv":
            label_w = min(content_w * 0.46,
                          max(width_of("- " + k, fs) for k, _ in payload) + 9 * mm)
            rows = [[Paragraph("- " + _esc(k), cell), Paragraph(_esc(v), cell)]
                    for k, v in payload]
            tbl = Table(rows, colWidths=[label_w, content_w - 7 * mm - label_w],
                        hAlign="LEFT")
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, -1), 7 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 3 * mm))

        elif kind == "list":
            for i, it in enumerate(payload, start=1):
                text = it if it[:1].isdigit() else f"{i}) {it}"
                story.append(Paragraph(_esc(text),
                                       ParagraphStyle("li", parent=body,
                                                      leftIndent=12 * mm,
                                                      spaceAfter=fs * 0.15)))
            story.append(Spacer(1, 2.5 * mm))

        elif kind == "table":
            header, rows = payload
            natural = [max([width_of(header[i], fs * 0.95)]
                           + [width_of(r[i], fs * 0.95) for r in rows]) + 8 * mm
                       for i in range(len(header))]
            avail = content_w - 7 * mm
            scale = avail / sum(natural) if sum(natural) > avail else 1.0
            widths = [w * scale for w in natural]
            data = [[Paragraph(_esc(h), cell_head) for h in header]]
            data += [[Paragraph(_esc(c), cell) for c in r] for r in rows]
            tbl = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
            tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#333333")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(Table([[tbl]], colWidths=[content_w],
                               style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 7 * mm),
                                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                                 ("TOPPADDING", (0, 0), (-1, -1), 0),
                                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 0)])))
            story.append(Spacer(1, 3.5 * mm))

        elif kind == "date":
            story.append(Spacer(1, 10 * mm))
            story.append(Paragraph(_esc(payload), centered))
            story.append(Spacer(1, 5 * mm))
        elif kind == "company":
            story.append(Paragraph(_esc(payload), centered_bold))
            story.append(Spacer(1, 7 * mm))

        elif kind == "signs":
            story.append(KeepTogether(SignBlock(payload, regular, fs, seed)))

        elif kind == "attachments":
            story.append(Spacer(1, 8 * mm))
            para("첨부서류", subheading)
            for i, a in enumerate(payload, start=1):
                story.append(Paragraph(f"{i}. {_esc(a)}",
                                       ParagraphStyle("att", parent=body,
                                                      leftIndent=7 * mm,
                                                      spaceAfter=fs * 0.15)))

    stamp_rng = random.Random(seed * 31 + 7)
    stamp = _stamp_image(m.corner_stamp, stamp_rng)
    paging = _seal_image(m.paging_seal, random.Random(seed * 131 + 3))

    def on_page(canvas, doc):
        if paging is not None:
            side = 17 * mm
            canvas.drawImage(ImageReader(paging), A4[0] - side * 0.45,
                             A4[1] * 0.58, side, side, mask="auto")
        if stamp is not None and doc.page == 1:
            width_pt = 42 * mm
            height_pt = width_pt * stamp.height / stamp.width
            canvas.drawImage(ImageReader(stamp), A4[0] - margin_x - width_pt * 0.85,
                             A4[1] - margin_y - height_pt * 0.6,
                             width_pt, height_pt, mask="auto")
        if s.page_border:
            canvas.saveState()
            canvas.setStrokeColorRGB(0.15, 0.15, 0.15)
            canvas.setLineWidth(0.8)
            canvas.rect(margin_x - 6 * mm, margin_y - 6 * mm,
                        content_w + 12 * mm, A4[1] - 2 * margin_y + 12 * mm)
            canvas.restoreState()
        canvas.saveState()
        canvas.setFont(regular, fs * 0.8)
        canvas.drawCentredString(A4[0] / 2, margin_y * 0.45, f"- {doc.page} -")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        target, pagesize=A4,
        leftMargin=margin_x, rightMargin=margin_x,
        topMargin=margin_y, bottomMargin=margin_y,
        title=f"{m.company.full_name(s)} 이사회 의사록",
        author=m.company.full_name(s),
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


def pdf_bytes(m: Minutes, seed: int = 0) -> bytes:
    import io
    buf = io.BytesIO()
    render_pdf(m, buf, seed)
    return buf.getvalue()
