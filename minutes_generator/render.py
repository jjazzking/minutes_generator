# -*- coding: utf-8 -*-
"""의사록 객체를 사람이 읽는 텍스트와 정답셋(JSON)으로 변환한다."""

import random
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

Block = Tuple[str, Any]

from .model import Minutes, Officer, Style, Vote, comma

HANGUL_ORDER = ["가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타"]
PAGE_WIDTH = 68


# ---------------------------------------------------------------- 폭 계산

def _w(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _w(text))


def _center(text: str, width: int = PAGE_WIDTH) -> str:
    return " " * max(0, (width - _w(text)) // 2) + text


def _wrap(text: str, width: int = PAGE_WIDTH, indent: str = "") -> List[str]:
    avail = max(10, width - _w(indent))
    out: List[str] = []
    cur = ""
    for token in text.split():
        if not cur:
            cur = token
        elif _w(cur) + 1 + _w(token) <= avail:
            cur += " " + token
        else:
            out.append(indent + cur)
            cur = token
    if cur:
        out.append(indent + cur)
    return out or [indent]


# ---------------------------------------------------------------- 조사 교정

_JOSA_RE = re.compile(
    r"(은\(는\)|는\(은\)|이\(가\)|가\(이\)|을\(를\)|를\(을\)"
    r"|와\(과\)|과\(와\)|\(으\)로|으로\(로\))")

_JOSA_PAIRS = {
    "은(는)": ("은", "는"), "는(은)": ("은", "는"),
    "이(가)": ("이", "가"), "가(이)": ("이", "가"),
    "을(를)": ("을", "를"), "를(을)": ("을", "를"),
    "와(과)": ("과", "와"), "과(와)": ("과", "와"),
    "(으)로": ("으로", "로"), "으로(로)": ("으로", "로"),
}

_DIGIT_JONG = {"0": 21, "1": 8, "2": 0, "3": 16, "4": 0,
               "5": 0, "6": 1, "7": 8, "8": 8, "9": 0}

# 로마자는 한국어 음독의 말음을 기준으로 한다. L(엘)·M(엠)·N(엔)·R(알)만 받침이 있다.
_LATIN_JONG = {"L": 8, "M": 16, "N": 4, "R": 8}


def _jongseong(ch: str):
    """받침 코드. 판단할 수 없으면 None."""
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28
    if ch.isdigit():
        return _DIGIT_JONG[ch]
    if ch.isalpha() and ch.isascii():
        return _LATIN_JONG.get(ch.upper(), 0)
    return None


def _anchor_char(text: str, start: int) -> str:
    """조사 바로 앞의 실질 음절. 괄호 주석은 건너뛴다."""
    j = start - 1
    while j >= 0 and text[j] in " \u00a0":
        j -= 1
    if j >= 0 and text[j] == ")":
        depth, j = 1, j - 1
        while j >= 0 and depth:
            if text[j] == ")":
                depth += 1
            elif text[j] == "(":
                depth -= 1
            j -= 1
        while j >= 0 and text[j] == " ":
            j -= 1
    return text[j] if j >= 0 else ""


def fix_josa(text: str) -> str:
    """'김철수은(는)' 형태의 병기 조사를 실제 받침에 맞게 하나로 확정한다."""

    def sub(match):
        token = match.group(1)
        with_jong, without_jong = _JOSA_PAIRS[token]
        jong = _jongseong(_anchor_char(text, match.start()))
        if jong is None:
            return token
        if token in ("(으)로", "으로(로)"):
            return "로" if jong in (0, 8) else "으로"
        return with_jong if jong else without_jong

    return _JOSA_RE.sub(sub, text)


def _marker(style: Style, i: int, scheme: str = None) -> str:
    if (scheme or style.numbering) == "arabic":
        return f"{i}."
    return f"{HANGUL_ORDER[(i - 1) % len(HANGUL_ORDER)]}."


def _report_scheme(style: Style) -> str:
    """의안 번호가 '1.' 형식이면 보고사항은 가·나·다로 구분한다."""
    return "hangul" if style.agenda_label == "num" else style.numbering


def _label(style: Style, text: str, width: int = 8) -> str:
    """spaced_labels가 켜지면 '일    시'처럼 글자 사이를 벌린다."""
    if style.spaced_labels and len(text) <= 4:
        pad = max(0, width - _w(text))
        gaps = len(text) - 1
        if gaps > 0:
            each, extra = divmod(pad, gaps)
            chars = []
            for i, c in enumerate(text):
                chars.append(c)
                if i < gaps:
                    chars.append(" " * (each + (1 if i < extra else 0)))
            return "".join(chars)
    return _pad(text, width)


# ---------------------------------------------------------------- 블록 렌더

def _render_blocks(blocks: List[Block], style: Style, indent: str = "   ") -> List[str]:
    lines: List[str] = []
    for kind, payload in blocks:
        if kind == "para":
            lines += _wrap(payload, PAGE_WIDTH, indent)
            lines.append("")
        elif kind == "kv":
            width = max(_w(k) for k, _ in payload) + 2
            for k, v in payload:
                head = f"{indent}- {_pad(k, width)}: "
                wrapped = _wrap(str(v), PAGE_WIDTH - _w(head), "")
                lines.append(head + wrapped[0])
                for cont in wrapped[1:]:
                    lines.append(" " * _w(head) + cont)
            lines.append("")
        elif kind == "list":
            for i, item in enumerate(payload, start=1):
                text = item if item[:1].isdigit() else f"{i}) {item}"
                wrapped = _wrap(text, PAGE_WIDTH - len(indent) - 3)
                lines.append(f"{indent}   {wrapped[0]}")
                for cont in wrapped[1:]:
                    lines.append(f"{indent}      {cont}")
            lines.append("")
        elif kind == "table":
            header, rows = payload
            widths = [max(_w(str(header[i])), *(_w(str(r[i])) for r in rows)) if rows
                      else _w(str(header[i])) for i in range(len(header))]
            bar = indent + "+" + "+".join("-" * (w + 2) for w in widths) + "+"
            lines.append(bar)
            lines.append(indent + "| " + " | ".join(_pad(str(header[i]), widths[i])
                                                    for i in range(len(header))) + " |")
            lines.append(bar)
            for r in rows:
                lines.append(indent + "| " + " | ".join(_pad(str(r[i]), widths[i])
                                                        for i in range(len(r))) + " |")
            lines.append(bar)
            lines.append("")
    return lines


# ---------------------------------------------------------------- 문장 풀

def _opening(m: Minutes, rng: random.Random) -> str:
    s = m.style
    t = s.fmt_time(m.start_time)
    chair = f"{m.chair.title} {m.chair.display(s)}"
    return rng.choice([
        f"의장인 {chair}은(는) 위와 같이 법령 및 정관에 정한 이사회의 성원수가 출석하여 "
        f"본 이사회가 적법하게 성립되었음을 알리고, {t} 개회를 {s.sent('선언하')}",
        f"의장 {m.chair.display(s)}은(는) 정관 제{rng.randint(36, 44)}조에 따른 이사회 성립 정족수가 "
        f"충족되었음을 확인한 후 {t} 개회를 {s.sent('선언하')}",
        f"위와 같이 재적이사 과반수가 출석하여 이사회가 적법하게 성립되었으므로, 의장은 {t} "
        f"개회를 선언하고 다음의 의안을 {s.sent('부의하')}",
        f"의장은 본 이사회가 상법 및 정관이 정한 요건을 갖추어 유효하게 성립하였음을 선언하고 "
        f"{t}부터 의사를 {s.sent('진행하')}",
    ])


def _vote_sentence(v: Vote, item, style: Style, rng: random.Random) -> str:
    s = style
    excl = ""
    if v.excluded:
        excl = (f"상법 제398조에 따라 특별이해관계인인 {v.excluded} 이사를 의결에서 제외한 후, ")
    if v.result == "부결":
        return (f"{excl}의장이 위 의안의 가부를 물은 결과 출석이사 {v.present}명 중 찬성 {v.favor}명, "
                f"반대 {v.against}명, 기권 {v.abstain}명으로 의결정족수에 미달하여 이를 "
                f"{s.sent('부결하')}")
    if v.result == "수정가결":
        return (f"{excl}심의 과정에서 일부 수정 의견이 제시되어 이를 반영한 수정안에 대하여 표결한 결과, "
                f"출석이사 {v.present}명 전원의 찬성으로 위 의안을 {s.sent('수정 가결하')}")
    if v.unanimous:
        base = rng.choice([
            f"{excl}의장이 위 의안에 관하여 그 가부를 물으니 출석이사 전원이 찬성하여 원안대로 "
            f"{s.sent('가결하')}",
            f"{excl}출석이사 {v.present}명 전원의 찬성으로 위 의안을 원안대로 {s.sent('가결하')}",
            f"{excl}의장이 위 의안의 승인 여부를 물은 결과 출석이사 {v.present}명 전원이 찬성하여 "
            f"이를 {s.sent('가결하')}",
        ])
        if item.special_majority:
            base = base.rstrip(".") + f" (재적이사 {v.eligible + 1}명의 3분의 2 이상 찬성)."
        return base
    return (f"{excl}의장이 위 의안에 대한 가부를 물으니 출석이사 {v.present}명 중 찬성 {v.favor}명, "
            f"반대 {v.against}명, 기권 {v.abstain}명으로 출석이사 과반수의 찬성을 얻어 원안대로 "
            f"{s.sent('가결하')}")


def _closing(m: Minutes, rng: random.Random) -> str:
    s = m.style
    t = s.fmt_time(m.end_time)
    return rng.choice([
        f"의장은 이상으로써 회의 목적사항인 의안 전부의 심의를 종료하였으므로 {t} 폐회를 {s.sent('선언하')}",
        f"더 이상 논의할 사항이 없으므로 의장은 {t} 폐회를 {s.sent('선언하')}",
        f"의장은 위 의안의 심의 및 의결을 모두 마쳤음을 확인하고 {t} 이사회의 폐회를 {s.sent('선언하')}",
    ])


def _certification(m: Minutes, rng: random.Random) -> str:
    s = m.style
    has_auditor = any(o.role == "감사" for o in m.signers)
    who = "의장과 출석한 이사 및 감사" if has_auditor else "의장과 출석한 이사 전원"
    return rng.choice([
        f"위 결의를 명확히 하기 위하여 이 의사록을 작성하고 {who}이(가) 다음과 같이 "
        f"{s.sent('기명날인하')}",
        f"위 의사의 경과와 그 결과를 명확히 하기 위하여 본 의사록을 작성하고 {who}이(가) "
        f"{s.sent('기명날인하')}",
        f"이상의 의사 경과 요령과 결과를 명확히 하기 위하여 이 의사록을 작성하여 {who}이(가) "
        f"{s.sent('서명 또는 기명날인하')}",
    ])


# ---------------------------------------------------------------- 문서 흐름

def build_flow(m: Minutes, seed: int = 0) -> List[Block]:
    """렌더러가 공유하는 의미 단위 목록을 만든다.

    텍스트·HTML·PDF 출력이 같은 흐름을 소비하므로 서로 내용이 어긋나지 않는다.
    """
    rng = random.Random(seed ^ 0x5EED)
    s = m.style
    F: List[Block] = [("title", fix_josa(s.doc_title))]

    header: List[Dict[str, Any]] = [
        {"label": "상호", "value": m.company.full_name(s)},
        {"label": "일시", "value": f"{s.fmt_date(m.meeting_date)} {s.fmt_time(m.start_time)}"},
        {"label": "장소", "value": m.place},
    ]

    n_dir, p_dir = len(m.directors), m.present_directors
    n_aud = len(m.auditors)
    p_aud = sum(1 for a in m.auditors if a.present)
    att: Dict[str, Any] = {"label": "출석현황", "value": "", "lines": [], "roster": []}
    if s.attendance_layout in ("inline", "both"):
        att["lines"].append(f"이사 총수: {n_dir}명     출석 이사 수: {p_dir}명")
        if n_aud:
            att["lines"].append(f"감사 총수: {n_aud}명     출석 감사 수: {p_aud}명")
        if s.attendance_layout == "inline":
            for o in [d for d in m.directors if not d.present] + \
                     [a for a in m.auditors if not a.present]:
                att["lines"].append(f"불참: {o.title} {o.display(s)}({o.absence_reason})")
    if s.attendance_layout in ("roster", "both"):
        for d in m.directors:
            mark = "출석" if d.attend_mode == "출석" else (
                "원격출석(화상회의)" if d.attend_mode == "원격" else f"불참({d.absence_reason})")
            att["roster"].append((d.title, d.display(s), mark))
        for a in m.auditors:
            mark = "출석" if a.present else f"불참({a.absence_reason})"
            att["roster"].append((a.title, a.display(s), mark))
    header.append(att)
    header.append({"label": "의장", "value": f"{m.chair.title} {m.chair.display(s)}"})
    if m.secretary:
        header.append({"label": "간사",
                       "value": f"{m.secretary.title} {m.secretary.display(s)}"})
    F.append(("header", header))

    if m.notice_note:
        F.append(("para", fix_josa(m.notice_note)))
    if m.chair_note:
        F.append(("para", fix_josa(m.chair_note + ".")))
    F.append(("para", fix_josa(_opening(m, rng))))

    if m.reports:
        F.append(("section", "보고사항"))
        for i, r in enumerate(m.reports, start=1):
            F.append(("item_heading",
                      f"{_marker(s, i, _report_scheme(s))} {fix_josa(r.title)}"))
            for kind, payload in r.blocks:
                F.append(("indent_para" if kind == "para" else kind,
                          _clean_block(kind, payload)))

    for i, (item, vote) in enumerate(m.agenda, start=1):
        F.append(("agenda_heading", fix_josa(s.agenda_heading(i, item.title))))
        for kind, payload in item.blocks:
            F.append(("indent_para" if kind == "para" else kind,
                      _clean_block(kind, payload)))
        F.append(("resolution", fix_josa(_vote_sentence(vote, item, s, rng))))

    if m.discussion:
        F.append(("section", "기타 토의사항"))
        F.append(("indent_para", fix_josa(m.discussion)))

    F.append(("para", fix_josa(_closing(m, rng))))
    F.append(("para", fix_josa(_certification(m, rng))))
    F.append(("date", s.fmt_date(m.meeting_date)))
    F.append(("company", m.company.full_name(s)))
    F.append(("signs", [(o.title, o.display(s), s.seal_mark) for o in m.signers]))
    if m.attachments:
        F.append(("attachments", list(m.attachments)))
    return F


def _clean_block(kind: str, payload):
    if kind == "para":
        return fix_josa(payload)
    if kind == "kv":
        return [(fix_josa(str(k)), fix_josa(str(v))) for k, v in payload]
    if kind == "list":
        return [fix_josa(str(x)) for x in payload]
    if kind == "table":
        header, rows = payload
        return ([fix_josa(str(h)) for h in header],
                [[fix_josa(str(c)) for c in r] for r in rows])
    return payload


# ---------------------------------------------------------------- 텍스트 출력

def render_text(m: Minutes, seed: int = 0) -> str:
    s = m.style
    L: List[str] = []
    body_indent = "   "

    for kind, payload in build_flow(m, seed):
        if kind == "title":
            L += [_center(payload), "", ""]
        elif kind == "header":
            for i, entry in enumerate(payload, start=1):
                label = f"{_marker(s, i)} {_label(s, entry['label'])}"
                L.append(f"{label}: {entry['value']}".rstrip())
                for line in entry.get("lines", []):
                    L.append("     " + line)
                for title, name, mark in entry.get("roster", []):
                    L.append(f"     {_pad(title, 14)}{_pad(name, 16)}{mark}")
            L.append("")
        elif kind == "para":
            L += _wrap(payload) + [""]
        elif kind == "section":
            L += [f"[{payload}]", ""]
        elif kind in ("item_heading", "agenda_heading"):
            L += _wrap(payload) + [""]
        elif kind == "indent_para":
            L += _wrap(payload, indent=body_indent) + [""]
        elif kind == "resolution":
            L += _wrap(payload, indent=body_indent) + [""]
        elif kind in ("kv", "table", "list"):
            L += _render_blocks([(kind, payload)], s, body_indent)
        elif kind == "date":
            L += ["", _center(payload), ""]
        elif kind == "company":
            L += [_center(payload), ""]
        elif kind == "signs":
            for title, name, seal in payload:
                L.append(_center(f"{_pad(title, 14)}{_pad(name, 16)}{seal}"))
            L.append("")
        elif kind == "attachments":
            L.append("첨부서류")
            for i, a in enumerate(payload, start=1):
                L.append(f"   {i}. {a}")
            L.append("")

    return "\n".join(L).rstrip() + "\n"


# ---------------------------------------------------------------- 정답셋


def ground_truth(m: Minutes) -> Dict[str, Any]:
    s = m.style
    return {
        "company": {
            "name": m.company.full_name(s),
            "plain_name": m.company.name,
            "address": m.company.address,
            "par_value": m.company.par_value,
            "shares_issued": m.company.shares_issued,
            "capital": m.company.capital,
            "authorized_shares": m.company.authorized_shares,
            "business": m.company.business,
        },
        "meeting": {
            "title": s.doc_title,
            "kind": m.meeting_kind,
            "date": m.meeting_date.isoformat(),
            "start_time": m.start_time.strftime("%H:%M"),
            "end_time": m.end_time.strftime("%H:%M"),
            "place": m.place,
            "chair": {"name": m.chair.name, "title": m.chair.title},
            "secretary": m.secretary.name if m.secretary else None,
            "total_directors": len(m.directors),
            "present_directors": m.present_directors,
            "total_auditors": len(m.auditors),
            "present_auditors": sum(1 for a in m.auditors if a.present),
            "notice_note": m.notice_note,
        },
        "directors": [
            {"name": d.name, "hanja": d.hanja, "role": d.role, "title": d.title,
             "present": d.present, "mode": d.attend_mode, "absence_reason": d.absence_reason}
            for d in m.directors
        ],
        "auditors": [
            {"name": a.name, "role": a.role, "title": a.title, "present": a.present}
            for a in m.auditors
        ],
        "reports": [r.title for r in m.reports],
        "agenda": [
            {
                "index": i,
                "kind": item.kind,
                "title": item.title,
                "facts": item.facts,
                "vote": {
                    "eligible": v.eligible, "present": v.present, "favor": v.favor,
                    "against": v.against, "abstain": v.abstain, "result": v.result,
                    "unanimous": v.unanimous, "excluded_director": v.excluded,
                },
            }
            for i, (item, v) in enumerate(m.agenda, start=1)
        ],
        "signers": [{"name": o.name, "title": o.title} for o in m.signers],
        "attachments": m.attachments,
        "style": {
            "ending": s.ending, "date_format": s.date_format, "money_format": s.money_format,
            "agenda_label": s.agenda_label, "attendance_layout": s.attendance_layout,
            "company_suffix": s.company_suffix, "seal_mark": s.seal_mark,
            "use_hanja_names": s.use_hanja_names, "use_hanja_title": s.use_hanja_title,
            "time_format": s.time_format, "numbering": s.numbering,
        },
    }
