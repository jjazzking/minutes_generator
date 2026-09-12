# -*- coding: utf-8 -*-
"""의사록 도메인 모델과 표기 스타일."""

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 수 표기

_SINO_DIGITS = "영일이삼사오육칠팔구"
_SMALL_UNITS = ["", "십", "백", "천"]
_BIG_UNITS = ["", "만", "억", "조", "경"]

_HANJA_DIGITS = "零一二三四五六七八九"


def sino_korean(n: int) -> str:
    """1234 -> '일천이백삼십사'. 금액 한글 병기에 쓴다."""
    if n == 0:
        return "영"
    groups: List[int] = []
    while n > 0:
        groups.append(n % 10000)
        n //= 10000
    parts: List[str] = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        chunk = ""
        for pos in range(3, -1, -1):
            d = (g // (10 ** pos)) % 10
            if d == 0:
                continue
            chunk += _SINO_DIGITS[d] + _SMALL_UNITS[pos]
        parts.append(chunk + _BIG_UNITS[idx])
    return "".join(parts)


def hanja_number(n: int) -> str:
    """2025 -> '二〇二五'. 연·월·일 한자 표기에 쓴다."""
    out = []
    for ch in str(n):
        out.append("〇" if ch == "0" else _HANJA_DIGITS[int(ch)])
    return "".join(out)


def comma(n: int) -> str:
    return f"{n:,}"


# ---------------------------------------------------------------- 스타일

@dataclass
class Style:
    """한 건의 의사록 전체에 일관되게 적용되는 표기 규칙."""

    ending: str = "da"            # da: ~하다 / yeoss: ~하였다 / ham: ~함
    date_format: str = "korean"   # korean / dotted / dotted_pad / hanja
    money_format: str = "plain"   # plain / geum / hangul_paren / paren_hangul
    agenda_label: str = "ho"      # ho: 제1호 의안 / uian: 제1의안 / num: 1.
    use_hanja_title: bool = False
    use_hanja_names: bool = False
    seal_mark: str = "(인)"       # (인) / (印) / (서명)
    show_seconds_in_time: bool = False
    time_format: str = "korean"   # korean: 오후 2시 30분 / colon: 14:30
    company_suffix: str = "주식회사"  # 주식회사 / (주) / 株式會社
    doc_title: str = "이 사 회 의 사 록"
    attendance_layout: str = "inline"   # inline / roster / both
    spaced_labels: bool = True          # "일    시" 처럼 라벨 안에 공백을 넣는지
    numbering: str = "hangul"           # hangul: 가. 나. / arabic: 1. 2.
    font_family: str = "gothic"         # gothic: 고딕 계열 / myeongjo: 명조·바탕 계열
    font_size: float = 10.5             # 본문 글자 크기(pt)
    leading_ratio: float = 1.6          # 행간 배수
    page_border: bool = False           # 본문 외곽 테두리
    title_underline: bool = False       # 제목 밑줄
    text_align: str = "justify"         # justify: 양쪽 정렬 / left: 왼쪽 정렬
    seal_images: bool = False           # 서명란에 실제 인영 이미지를 찍는지

    # ----- 포맷터 -----

    def fmt_date(self, d: date) -> str:
        if self.date_format == "dotted":
            return f"{d.year}. {d.month}. {d.day}."
        if self.date_format == "dotted_pad":
            return f"{d.year}. {d.month:02d}. {d.day:02d}."
        if self.date_format == "hanja":
            return (
                f"{hanja_number(d.year)}年 {hanja_number(d.month)}月 "
                f"{hanja_number(d.day)}日"
            )
        return f"{d.year}년 {d.month}월 {d.day}일"

    def fmt_time(self, t: time) -> str:
        if self.time_format == "colon":
            if self.show_seconds_in_time:
                return f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}"
            return f"{t.hour:02d}:{t.minute:02d}"
        ampm = "오전" if t.hour < 12 else "오후"
        h12 = t.hour if t.hour <= 12 else t.hour - 12
        if t.minute == 0:
            return f"{ampm} {h12}시"
        return f"{ampm} {h12}시 {t.minute}분"

    def fmt_money(self, n: int) -> str:
        if self.money_format == "geum":
            return f"금 {comma(n)}원"
        if self.money_format == "hangul_paren":
            return f"금 {sino_korean(n)}원(￦{comma(n)})"
        if self.money_format == "paren_hangul":
            return f"{comma(n)}원(금 {sino_korean(n)}원)"
        return f"{comma(n)}원"

    def fmt_count(self, n: int, unit: str) -> str:
        return f"{comma(n)}{unit}"

    def agenda_heading(self, idx: int, title: str) -> str:
        if self.agenda_label == "uian":
            label = f"제{idx}의안"
        elif self.agenda_label == "num":
            label = f"{idx}."
        else:
            label = f"제{idx}호 의안"
        if self.use_hanja_title and self.agenda_label != "num":
            label = label.replace("제", "第").replace("호", "號")
        return f"{label} {title}"

    def sent(self, stem: str) -> str:
        """'선언하' 같은 어간을 문체에 맞는 종결형으로 바꾼다."""
        if self.ending == "yeoss":
            return stem + "였다."
        if self.ending == "ham":
            return stem + "였음."
        return stem + "다."


# ---------------------------------------------------------------- 구성원

@dataclass
class Seal:
    """서명란에 찍히는 인영 한 개."""

    text: str                 # 도장에 새겨진 글자
    shape: str                # circle / square / rounded
    kind: str                 # 직인 / 성명인


@dataclass
class Officer:
    name: str
    hanja: str
    role: str                 # 사내이사 / 사외이사 / 기타비상무이사 / 감사
    title: str                # 대표이사 / 이사 / 감사 등 직함
    present: bool = True
    attend_mode: str = "출석"  # 출석 / 원격 / 불참
    absence_reason: Optional[str] = None
    seal: Optional["Seal"] = None

    def display(self, style: Style) -> str:
        if style.use_hanja_names and self.hanja:
            return f"{self.name}({self.hanja})"
        return self.name


@dataclass
class Company:
    name: str                 # 접두사 없는 상호
    suffix_position: str      # prefix / suffix
    address: str
    registry_office: str
    par_value: int            # 1주 액면가
    shares_issued: int        # 발행주식총수
    capital: int              # 자본금 = 액면가 * 발행주식총수
    authorized_shares: int    # 발행예정주식총수
    business: List[str]
    fiscal_year_end: str

    def full_name(self, style: Style) -> str:
        suf = style.company_suffix
        if self.suffix_position == "prefix":
            return f"{suf} {self.name}" if suf != "(주)" else f"(주){self.name}"
        return f"{self.name} {suf}" if suf != "(주)" else f"{self.name}(주)"


# ---------------------------------------------------------------- 의안

Block = Tuple[str, Any]  # ("para", str) / ("kv", [(k, v)]) / ("table", (header, rows)) / ("list", [str])


@dataclass
class AgendaItem:
    kind: str
    title: str
    blocks: List[Block]
    facts: Dict[str, Any] = field(default_factory=dict)
    interested_director: Optional[str] = None  # 상법 제398조 특별이해관계자
    special_majority: bool = False             # 이사 3분의 2 이상 찬성 필요
    resolution_text: Optional[str] = None


@dataclass
class Vote:
    eligible: int
    present: int
    favor: int
    against: int
    abstain: int
    result: str               # 원안가결 / 수정가결 / 부결
    unanimous: bool
    excluded: Optional[str] = None


@dataclass
class ReportItem:
    title: str
    blocks: List[Block]


@dataclass
class Minutes:
    company: Company
    style: Style
    meeting_no: int
    meeting_kind: str          # 정기 / 임시
    meeting_date: date
    start_time: time
    end_time: time
    place: str
    directors: List[Officer]
    auditors: List[Officer]
    chair: Officer
    chair_note: Optional[str]
    secretary: Optional[Officer]
    reports: List[ReportItem]
    agenda: List[Tuple[AgendaItem, Vote]]
    discussion: Optional[str]
    signers: List[Officer]
    notice_note: Optional[str]
    attachments: List[str]
    paging_seal: Optional[Seal] = None    # 간인(페이지에 걸쳐 찍는 도장)
    corner_stamp: Optional[str] = None    # 사본, 원본대조필 등 스탬프

    @property
    def total_directors(self) -> int:
        return len(self.directors)

    @property
    def present_directors(self) -> int:
        return sum(1 for d in self.directors if d.present)
