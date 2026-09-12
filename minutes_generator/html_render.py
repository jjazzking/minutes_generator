# -*- coding: utf-8 -*-
"""의사록을 HTML로 출력한다. 화면 미리보기와 브라우저 인쇄(PDF)에 쓴다."""

from html import escape
from typing import List

from .model import Minutes
from .render import _label, _marker, build_flow

FONT_STACKS = {
    "gothic": "'맑은 고딕', 'Malgun Gothic', 'Apple SD Gothic Neo', "
              "'NanumGothic', 'Noto Sans KR', sans-serif",
    "myeongjo": "'바탕', Batang, 'AppleMyungjo', 'NanumMyeongjo', "
                "'Noto Serif KR', serif",
}

PAGE_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
.doc {
  --fs: 10.5pt;
  --lh: 1.6;
  background: #fff;
  color: #111;
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  padding: 22mm 20mm;
  font-family: var(--ff);
  font-size: var(--fs);
  line-height: var(--lh);
  letter-spacing: var(--ls, 0);
}
.doc.bordered > .inner { border: 1px solid #222; padding: 10mm; min-height: 250mm; }
.doc h1 {
  text-align: center;
  font-size: calc(var(--fs) * 1.7);
  font-weight: 700;
  letter-spacing: 0.35em;
  margin: 0 0 14mm 0;
}
.doc h1.underline { text-decoration: underline; text-underline-offset: 6px; }
.doc .meta { margin-bottom: 8mm; }
.doc .meta .row { display: flex; gap: 6px; margin: 1.5mm 0; }
.doc .meta .lbl { white-space: pre; flex: 0 0 auto; }
.doc .meta .sub { margin-left: 7.5mm; }
.doc .meta .roster { display: flex; gap: 4mm; margin-left: 7.5mm; }
.doc .meta .roster .t { flex: 0 0 26mm; }
.doc .meta .roster .n { flex: 0 0 30mm; }
.doc p { margin: 0 0 3mm 0; text-align: var(--ta, justify); }
.doc p.indent { margin-left: 7mm; }
.doc h2.section { font-size: var(--fs); font-weight: 700; margin: 6mm 0 3mm 0; }
.doc h3.agenda {
  font-size: var(--fs); font-weight: 700; margin: 7mm 0 3mm 0;
}
.doc h3.item { font-size: var(--fs); font-weight: 700; margin: 4mm 0 2mm 0; }
.doc dl.kv { margin: 0 0 4mm 7mm; }
.doc dl.kv .row { display: flex; margin: 1.2mm 0; }
.doc dl.kv dt { flex: 0 0 50mm; }
.doc dl.kv dt::before { content: "- "; }
.doc dl.kv dd { margin: 0; flex: 1 1 auto; }
.doc ol.items { margin: 0 0 4mm 12mm; padding: 0; list-style: none; }
.doc ol.items li { margin: 1mm 0; }
.doc table { border-collapse: collapse; margin: 0 0 4mm 7mm; width: calc(100% - 7mm); }
.doc th, .doc td {
  border: 0.6pt solid #333; padding: 1.6mm 2.4mm; font-size: calc(var(--fs) * 0.95);
  text-align: left; vertical-align: top;
}
.doc th { font-weight: 700; background: #f3f3f3; }
.doc .closing { margin-top: 8mm; }
.doc .datestamp { text-align: center; margin: 12mm 0 6mm 0; }
.doc .corp { text-align: center; font-weight: 700; margin-bottom: 8mm; }
.doc .signs { width: auto; margin: 0 auto; border: none; }
.doc .signs td { border: none; padding: 2mm 3mm; white-space: nowrap; }
.doc .attach { margin-top: 10mm; }
.doc .attach ol { margin: 2mm 0 0 6mm; padding: 0; }
@media print {
  body { background: #fff; margin: 0; }
  .doc { width: auto; min-height: 0; margin: 0; padding: 18mm 16mm; }
  .doc h3.agenda { break-before: auto; break-after: avoid; }
  .doc table, .doc dl.kv { break-inside: avoid; }
}
"""


def render_html(m: Minutes, seed: int = 0, full_page: bool = True) -> str:
    """full_page=False 이면 <article> 조각만 돌려준다 (미리보기용)."""
    s = m.style
    parts: List[str] = []
    cls = "doc bordered" if s.page_border else "doc"
    style_attr = (f"--ff: {FONT_STACKS.get(s.font_family, FONT_STACKS['gothic'])};"
                  f" --fs: {s.font_size}pt; --lh: {s.leading_ratio};"
                  f" --ta: {s.text_align};")
    parts.append(f'<article class="{cls}" style="{escape(style_attr, quote=True)}">')
    parts.append('<div class="inner">')

    for kind, payload in build_flow(m, seed):
        if kind == "title":
            klass = "underline" if s.title_underline else ""
            parts.append(f'<h1 class="{klass}">{escape(payload)}</h1>')
        elif kind == "header":
            parts.append('<div class="meta">')
            for i, entry in enumerate(payload, start=1):
                lbl = escape(f"{_marker(s, i)} {_label(s, entry['label'])}:")
                val = escape(entry["value"])
                parts.append(f'<div class="row"><span class="lbl">{lbl}</span>'
                             f'<span class="val">{val}</span></div>')
                for line in entry.get("lines", []):
                    parts.append(f'<div class="sub">{escape(line)}</div>')
                for title, name, mark in entry.get("roster", []):
                    parts.append(
                        f'<div class="roster"><span class="t">{escape(title)}</span>'
                        f'<span class="n">{escape(name)}</span>'
                        f'<span class="m">{escape(mark)}</span></div>')
            parts.append("</div>")
        elif kind == "para":
            parts.append(f"<p>{escape(payload)}</p>")
        elif kind in ("indent_para", "resolution"):
            parts.append(f'<p class="indent">{escape(payload)}</p>')
        elif kind == "section":
            parts.append(f'<h2 class="section">[{escape(payload)}]</h2>')
        elif kind == "item_heading":
            parts.append(f'<h3 class="item">{escape(payload)}</h3>')
        elif kind == "agenda_heading":
            parts.append(f'<h3 class="agenda">{escape(payload)}</h3>')
        elif kind == "kv":
            parts.append('<dl class="kv">')
            for k, v in payload:
                parts.append(f'<div class="row"><dt>{escape(k)}</dt>'
                             f'<dd>{escape(v)}</dd></div>')
            parts.append("</dl>")
        elif kind == "list":
            parts.append('<ol class="items">')
            for i, it in enumerate(payload, start=1):
                text = it if it[:1].isdigit() else f"{i}) {it}"
                parts.append(f"<li>{escape(text)}</li>")
            parts.append("</ol>")
        elif kind == "table":
            header, rows = payload
            parts.append("<table><thead><tr>")
            parts += [f"<th>{escape(h)}</th>" for h in header]
            parts.append("</tr></thead><tbody>")
            for r in rows:
                parts.append("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>")
            parts.append("</tbody></table>")
        elif kind == "date":
            parts.append(f'<div class="datestamp">{escape(payload)}</div>')
        elif kind == "company":
            parts.append(f'<div class="corp">{escape(payload)}</div>')
        elif kind == "signs":
            parts.append('<table class="signs"><tbody>')
            for title, name, seal in payload:
                parts.append(f"<tr><td>{escape(title)}</td><td>{escape(name)}</td>"
                             f"<td>{escape(seal)}</td></tr>")
            parts.append("</tbody></table>")
        elif kind == "attachments":
            parts.append('<div class="attach">첨부서류<ol>')
            parts += [f"<li>{escape(a)}</li>" for a in payload]
            parts.append("</ol></div>")

    parts.append("</div></article>")
    body = "\n".join(parts)

    if not full_page:
        return body

    title = escape(m.company.full_name(s) + " 이사회 의사록")
    return (f"<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{title}</title>"
            f"<style>body{{margin:0;background:#e9eaec;padding:16px 0}}{PAGE_CSS}</style>"
            f"</head><body>{body}</body></html>\n")
