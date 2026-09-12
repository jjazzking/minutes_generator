# -*- coding: utf-8 -*-
"""회사·임원·회의체를 무작위로 구성하고 한 건의 의사록을 조립한다."""

import math
import random
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple

from . import lexicon as lx
from . import names as nm
from .agenda import GENERATORS, WEIGHTS, Ctx, LST, P
from .model import (
    AgendaItem, Company, Minutes, Officer, ReportItem, Style, Vote, comma,
)

# ---------------------------------------------------------------- 회사

PAR_VALUES = [100, 100, 500, 500, 1_000, 5_000, 5_000]


def make_company(rng: random.Random) -> Company:
    base = nm.company_name(rng)
    par = rng.choice(PAR_VALUES)
    shares = rng.choice([
        rng.randrange(20, 200) * 1_000,
        rng.randrange(20, 200) * 10_000,
        rng.randrange(10, 120) * 100_000,
    ])
    authorized = shares * rng.choice([2, 4, 5, 10, 10, 20])
    return Company(
        name=base,
        suffix_position=rng.choice(["prefix", "suffix", "suffix"]),
        address=nm.address(rng),
        registry_office=nm.registry_office(rng),
        par_value=par,
        shares_issued=shares,
        capital=par * shares,
        authorized_shares=authorized,
        business=nm.business_purposes(rng, rng.randint(2, 5)),
        fiscal_year_end=rng.choice(["12월 31일", "12월 31일", "12월 31일", "3월 31일", "6월 30일"]),
    )


# ---------------------------------------------------------------- 임원

DIRECTOR_ROLES = ["사내이사", "사내이사", "사내이사", "사외이사", "기타비상무이사"]

ABSENCE_REASONS = [
    "해외 출장", "개인 사정", "질병 치료", "국내 출장", "선행 일정 중복", "사전 통보 후 불참",
]


def make_officers(rng: random.Random, used: set) -> Tuple[List[Officer], List[Officer]]:
    n_dir = rng.choices([3, 3, 4, 4, 5, 5, 6, 7, 8, 9], weights=[16, 14, 16, 12, 12, 8, 8, 6, 5, 3])[0]
    directors: List[Officer] = []
    for i in range(n_dir):
        name, hanja = nm.person_name(rng, used)
        if i == 0:
            role, title = "사내이사", "대표이사"
        elif i == 1 and rng.random() < 0.12:
            role, title = "사내이사", "각자대표이사"
        else:
            role = rng.choice(DIRECTOR_ROLES)
            title = "이사"
        directors.append(Officer(name=name, hanja=hanja, role=role, title=title))

    n_aud = rng.choices([0, 1, 1, 2], weights=[18, 50, 20, 12])[0]
    auditors: List[Officer] = []
    for _ in range(n_aud):
        name, hanja = nm.person_name(rng, used)
        auditors.append(Officer(
            name=name, hanja=hanja, role="감사",
            title=rng.choice(["감사", "감사", "상근감사"]),
        ))
    return directors, auditors


def assign_attendance(rng: random.Random, directors: List[Officer], auditors: List[Officer]) -> None:
    n = len(directors)
    quorum = n // 2 + 1
    max_absent = n - quorum
    n_absent = 0
    if max_absent > 0:
        n_absent = rng.choices(list(range(max_absent + 1)),
                               weights=[62] + [22, 10, 4, 2][:max_absent])[0]
    absent_idx = set(rng.sample(range(1, n), n_absent)) if n_absent else set()
    for i, d in enumerate(directors):
        if i in absent_idx:
            d.present = False
            d.attend_mode = "불참"
            d.absence_reason = rng.choice(ABSENCE_REASONS)
        else:
            d.present = True
            d.attend_mode = "원격" if rng.random() < 0.16 else "출석"
    for a in auditors:
        a.present = rng.random() < 0.82
        a.attend_mode = "출석" if a.present else "불참"
        if not a.present:
            a.absence_reason = rng.choice(ABSENCE_REASONS)


# ---------------------------------------------------------------- 표기 스타일

def make_style(rng: random.Random) -> Style:
    hanja = rng.random() < 0.22
    return Style(
        ending=rng.choices(["da", "yeoss", "ham"], weights=[45, 45, 10])[0],
        date_format=rng.choices(
            ["korean", "dotted", "dotted_pad", "hanja"],
            weights=[46, 30, 16, 8 if hanja else 0])[0],
        money_format=rng.choices(
            ["plain", "geum", "hangul_paren", "paren_hangul"], weights=[40, 28, 16, 16])[0],
        agenda_label=rng.choices(["ho", "uian", "num"], weights=[58, 24, 18])[0],
        use_hanja_title=hanja and rng.random() < 0.5,
        use_hanja_names=hanja and rng.random() < 0.6,
        seal_mark=rng.choices(["(인)", "(印)", "(서명)"], weights=[62, 18, 20])[0],
        time_format=rng.choices(["korean", "colon"], weights=[72, 28])[0],
        show_seconds_in_time=False,
        company_suffix=rng.choices(
            ["주식회사", "(주)", "株式會社"], weights=[62, 28, 10 if hanja else 0])[0],
        doc_title=rng.choice([
            "이 사 회 의 사 록", "이사회 의사록", "이 사 회  의 사 록",
            "이사회의사록", "理事會 議事錄" if hanja else "이사회 회의록",
        ]),
        attendance_layout=rng.choices(["inline", "roster", "both"], weights=[42, 26, 32])[0],
        spaced_labels=rng.random() < 0.5,
        numbering=rng.choices(["hangul", "arabic"], weights=[55, 45])[0],
    )


# ---------------------------------------------------------------- 표결

def make_vote(rng: random.Random, item: AgendaItem, directors: List[Officer]) -> Vote:
    excluded = item.interested_director
    voters = [d for d in directors if d.present and d.name != excluded]
    present = len(voters)
    eligible = len([d for d in directors if d.name != excluded])
    majority = present // 2 + 1

    if item.special_majority:
        need = math.ceil(len(directors) * 2 / 3)
        need = min(need, present)
    else:
        need = majority

    roll = rng.random()
    if present <= 2 or roll < 0.70:
        favor, against, abstain, result = present, 0, 0, "원안가결"
    elif roll < 0.88:
        dissent = rng.randint(1, max(1, present - need))
        split = rng.random()
        against = dissent if split < 0.6 else 0
        abstain = dissent - against
        favor = present - dissent
        result = "원안가결" if favor >= need else "부결"
    elif roll < 0.96:
        favor, against, abstain, result = present, 0, 0, "수정가결"
    else:
        favor = max(0, need - 1)
        against = present - favor
        abstain = 0
        result = "부결"

    if result != "부결" and favor < need:
        favor, against, abstain, result = present, 0, 0, "원안가결"

    return Vote(
        eligible=eligible, present=present, favor=favor, against=against,
        abstain=abstain, result=result,
        unanimous=(favor == present and present > 0), excluded=excluded,
    )


# ---------------------------------------------------------------- 보고·토의

def make_reports(rng: random.Random, ctx: Ctx) -> List[ReportItem]:
    n = rng.choices([0, 1, 1, 2, 3], weights=[38, 26, 14, 15, 7])[0]
    out: List[ReportItem] = []
    for topic in rng.sample(lx.REPORT_TOPICS, n):
        title = topic.format(q=rng.randint(1, 4), y=ctx.meeting_date.year)
        blocks = [P(rng.choice([
            f"{rng.choice(['경영지원실장', '재무팀장', '내부감사팀장', '준법지원인', '경영기획팀장'])}이(가) "
            f"위 사항을 보고하였고, 이사회는 이를 청취하였다.",
            "담당 임원이 배부된 자료에 따라 보고하였으며, 이사회는 질의응답을 거쳐 보고를 접수하였다.",
            "의장이 요약 보고하였고 별도의 이의 제기는 없었다.",
        ]))]
        if rng.random() < 0.35:
            blocks.append(LST(rng.sample([
                "전년 동기 대비 매출 증감 요인",
                "주요 원가 항목의 변동 내역",
                "차입금 만기구조 및 상환계획",
                "미수채권 회수 현황",
                "인력 운영 및 채용 계획",
                "주요 설비 가동률",
            ], rng.randint(2, 3))))
        out.append(ReportItem(title=title, blocks=blocks))
    return out


# ---------------------------------------------------------------- 조립

def build_minutes(seed: Optional[int] = None,
                  agenda_kinds: Optional[List[str]] = None,
                  n_agenda: Optional[int] = None) -> Minutes:
    rng = random.Random(seed)
    used: set = set()

    company = make_company(rng)
    style = make_style(rng)
    directors, auditors = make_officers(rng, used)
    assign_attendance(rng, directors, auditors)

    base = date(rng.randint(2018, 2026), rng.randint(1, 12), rng.randint(1, 28))
    hour = rng.choice([9, 10, 10, 11, 13, 14, 14, 15, 16, 17])
    minute = rng.choice([0, 0, 0, 10, 20, 30, 30, 40, 50])
    start = time(hour, minute)
    duration = rng.choice([20, 25, 30, 35, 40, 45, 50, 60, 75, 90, 120])
    end_dt = datetime.combine(base, start) + timedelta(minutes=duration)
    end = end_dt.time()

    ctx = Ctx(rng=rng, company=company, style=style, meeting_date=base,
              directors=directors, auditors=auditors, used_names=used,
              bond_series=rng.randint(1, 18))

    # ----- 의안 선정 -----
    if agenda_kinds:
        kinds = list(agenda_kinds)
    else:
        count = n_agenda if n_agenda is not None else rng.choices(
            [1, 2, 2, 3, 3, 4, 5, 6], weights=[20, 20, 12, 18, 8, 12, 7, 3])[0]
        pool = list(GENERATORS)
        weights = [WEIGHTS[k] for k in pool]
        kinds = []
        for _ in range(min(count, len(pool))):
            pick = rng.choices(pool, weights=weights)[0]
            idx = pool.index(pick)
            pool.pop(idx)
            weights.pop(idx)
            kinds.append(pick)

    items = [GENERATORS[k](ctx) for k in kinds]
    agenda = [(it, make_vote(rng, it, directors)) for it in items]

    # ----- 의장 -----
    chair = directors[0]
    chair_note = None
    if not chair.present:
        chair = next(d for d in directors if d.present)
        chair_note = rng.choice([
            "대표이사의 불참으로 정관 제38조에 따라 이사 중 연장자가 의장으로 회의를 주재하다",
            "대표이사 유고로 이사회에서 선임한 임시의장이 회의를 주재하다",
        ])
    elif any(it.kind == "ceo_election" for it, _ in agenda) and rng.random() < 0.4:
        chair_note = "대표이사 선임의 건과 관련하여 이사회의 동의로 최연장 이사가 임시의장을 맡다"

    secretary = None
    if rng.random() < 0.45:
        sname, shanja = nm.person_name(rng, used)
        secretary = Officer(name=sname, hanja=shanja, role="간사",
                            title=rng.choice(["경영지원팀장", "법무팀장", "총무팀장", "이사회 간사"]))

    discussion = None
    if rng.random() < 0.3:
        topic = rng.choice(lx.DISCUSSION_TOPICS)
        discussion = (f"이사들은 {topic}에 관하여 의견을 교환하였으나, "
                      f"{rng.choice(['별도의 결의 없이 차기 이사회에서 재논의하기로 하였다', '경영진이 추가 검토 후 보고하기로 하였다', '구체적인 실행안을 마련하여 다시 부의하기로 하였다'])}.")

    notice_note = None
    roll = rng.random()
    if roll < 0.45:
        days = rng.choice([1, 3, 7])
        notice_note = (f"본 이사회의 소집통지는 회의일 {days}일 전에 각 이사 및 감사에게 "
                       f"{rng.choice(['서면', '전자우편', '서면 및 전자우편'])}으로 발송되었다.")
    elif roll < 0.6:
        notice_note = ("이사 및 감사 전원의 동의로 상법 제390조 제4항에 따라 소집절차를 생략하였다.")

    attachments: List[str] = []
    if rng.random() < 0.35:
        attachments = rng.sample([
            "이사회 부의안건 설명자료 1부",
            "주식인수계약서(안) 1부",
            "재무제표 및 영업보고서 1부",
            "감정평가서 사본 1부",
            "여신거래약정서(안) 1부",
            "정관 신구대조표 1부",
            "이사회 참석자 서명부 1부",
        ], rng.randint(1, 3))

    # 상법 제391조의3에 따라 출석한 이사와 감사는 모두 기명날인한다.
    signers = [d for d in directors if d.present] + [a for a in auditors if a.present]

    return Minutes(
        company=company, style=style,
        meeting_no=rng.randint(1, 14),
        meeting_kind=rng.choices(["임시", "정기"], weights=[62, 38])[0],
        meeting_date=base, start_time=start, end_time=end,
        place=rng.choice([
            f"{company.address} {rng.choice(lx.BUILDINGS)}",
            f"본점 소재지 {rng.choice(lx.BUILDINGS)}",
            f"{nm.address(rng)}({rng.choice(['서울사무소', '연구소', '제2공장'])}) 회의실",
        ]),
        directors=directors, auditors=auditors,
        chair=chair, chair_note=chair_note, secretary=secretary,
        reports=make_reports(rng, ctx), agenda=agenda,
        discussion=discussion, signers=signers,
        notice_note=notice_note, attachments=attachments,
    )
