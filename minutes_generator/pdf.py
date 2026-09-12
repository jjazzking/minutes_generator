# -*- coding: utf-8 -*-
"""의사록을 PDF로 출력한다.

reportlab 과 한글 글꼴이 필요하다.  pip install reportlab
글꼴은 운영체제 기본값을 자동으로 찾으며, 환경변수로 지정할 수도 있다.
"""

from typing import Any, Dict, List, Optional, Tuple

from . import fonts
from .model import Minutes
from .render import _label, _marker, build_flow

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


_REGISTERED: Dict[str, Tuple[str, str]] = {}


def _register(family: str) -> Tuple[str, str]:
    """(보통 글꼴 이름, 굵은 글꼴 이름)을 돌려준다."""
    if family in _REGISTERED:
        return _REGISTERED[family]

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular = fonts.find_font(family)
    if not regular:
        raise PdfUnavailable(
            "한글 글꼴을 찾지 못했습니다. 나눔고딕 등을 설치하거나 "
            "환경변수 MINUTES_FONT_GOTHIC 에 .ttf 경로를 지정하세요."
        )
    name = f"MG-{family}"
    pdfmetrics.registerFont(TTFont(name, regular[0], subfontIndex=regular[1]))

    bold = fonts.find_bold(family)
    if bold:
        bold_name = f"{name}-Bold"
        pdfmetrics.registerFont(TTFont(bold_name, bold[0], subfontIndex=bold[1]))
    else:
        bold_name = name
    pdfmetrics.registerFontFamily(name, normal=name, bold=bold_name)
    _REGISTERED[family] = (name, bold_name)
    return _REGISTERED[family]


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
    from reportlab.platypus import (
        KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    s = m.style
    regular, bold = _register(s.font_family)
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

    for kind, payload in build_flow(m, seed):
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
            rows = [[Paragraph(_esc(t), cell), Paragraph(_esc(n), cell),
                     Paragraph(_esc(seal), cell)] for t, n, seal in payload]
            w0 = max(width_of(t, fs) for t, _n, _s in payload) + 10 * mm
            w1 = max(width_of(n, fs) for _t, n, _s in payload) + 12 * mm
            w2 = max(width_of(x, fs) for _t, _n, x in payload) + 6 * mm
            tbl = Table(rows, colWidths=[w0, w1, w2], hAlign="CENTER")
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(KeepTogether(tbl))

        elif kind == "attachments":
            story.append(Spacer(1, 8 * mm))
            para("첨부서류", subheading)
            for i, a in enumerate(payload, start=1):
                story.append(Paragraph(f"{i}. {_esc(a)}",
                                       ParagraphStyle("att", parent=body,
                                                      leftIndent=7 * mm,
                                                      spaceAfter=fs * 0.15)))

    def on_page(canvas, doc):
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
