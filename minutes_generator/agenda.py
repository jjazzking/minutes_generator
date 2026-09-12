# -*- coding: utf-8 -*-
"""의안(議案) 생성기.

각 생성기는 수치가 서로 모순되지 않는 하나의 의안을 만든다.
예) 전환가능주식수 = 권면총액 / 전환가액, 자산총계 = 부채총계 + 자본총계.
"""

import random
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Callable, Dict, List, Optional, Set

from . import lexicon as lx
from . import names as nm
from .model import AgendaItem, Company, Officer, Style, comma, sino_korean

# ---------------------------------------------------------------- 컨텍스트


@dataclass
class Ctx:
    rng: random.Random
    company: Company
    style: Style
    meeting_date: date
    directors: List[Officer]
    auditors: List[Officer]
    used_names: Set[str] = field(default_factory=set)
    bond_series: int = 1

    def money(self, n: int) -> str:
        return self.style.fmt_money(n)

    def d(self, day: date) -> str:
        return self.style.fmt_date(day)

    def future(self, lo: int, hi: int) -> date:
        return self.meeting_date + timedelta(days=self.rng.randint(lo, hi))

    def past(self, lo: int, hi: int) -> date:
        return self.meeting_date - timedelta(days=self.rng.randint(lo, hi))

    def person(self):
        return nm.person_name(self.rng, self.used_names)


def P(text: str):
    return ("para", text)


def KV(pairs):
    return ("kv", list(pairs))


def TBL(header, rows):
    return ("table", (list(header), [list(r) for r in rows]))


def LST(items):
    return ("list", list(items))


def _amt(rng: random.Random, lo: int, hi: int, step: int) -> int:
    return rng.randrange(lo // step, hi // step + 1) * step


def _split(rng: random.Random, total: int, parts: int, unit: int = 1) -> List[int]:
    """total을 parts개로 나눈다. 각 조각은 unit의 배수이고 합은 정확히 total."""
    if parts == 1:
        return [total]
    units = total // unit
    cuts = sorted(rng.sample(range(1, units), parts - 1)) if units > parts else None
    if cuts is None:
        base = [units // parts] * parts
        base[0] += units - sum(base)
        return [b * unit for b in base]
    out, prev = [], 0
    for c in cuts:
        out.append((c - prev) * unit)
        prev = c
    out.append((units - prev) * unit)
    return out


# ---------------------------------------------------------------- 의안 생성기

def ag_third_party_issue(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    new_shares = _amt(rng, 20_000, 2_000_000, 1_000)
    price = rng.choice([ctx.company.par_value * m for m in (1, 2, 3, 4, 5, 8, 10, 15, 20, 30)])
    price = max(price, ctx.company.par_value)
    total = new_shares * price
    n_allottee = rng.choices([1, 2, 3, 4], weights=[45, 30, 18, 7])[0]
    shares = _split(rng, new_shares, n_allottee, 1_000)
    rows = []
    allottees = []
    for s in shares:
        who = nm.counterparty(rng)
        rel = rng.choice(["제3자", "재무적 투자자", "전략적 투자자", "특수관계인 없음", "기존 주주"])
        rows.append([who, rel, f"{comma(s)}주", f"{comma(s * price)}원"])
        allottees.append({"name": who, "shares": s, "amount": s * price})
    pay_day = ctx.future(7, 45)
    kind = rng.choice(["기명식 보통주식", "기명식 보통주식", "기명식 전환우선주식", "기명식 상환전환우선주식"])
    return AgendaItem(
        kind="third_party_issue",
        title=rng.choice([
            "신주발행(제3자배정 유상증자)의 건",
            "제3자배정 방식에 의한 신주발행의 건",
            "운영자금 조달을 위한 신주발행의 건",
        ]),
        blocks=[
            P(f"의장은 회사의 {rng.choice(['운영자금', '시설투자자금', '연구개발자금', '차입금 상환 및 운영자금'])} "
              f"조달을 위하여 정관 제{rng.randint(8, 12)}조에 따라 제3자배정 방식의 신주발행이 필요함을 설명하고 "
              f"다음과 같이 승인하여 줄 것을 요청하였다."),
            KV([
                ("신주의 종류와 수", f"{kind} {comma(new_shares)}주"),
                ("1주의 금액", f"{comma(ctx.company.par_value)}원"),
                ("신주의 발행가액", f"1주당 {comma(price)}원"),
                ("발행가액 총액", ctx.money(total)),
                ("납입기일", ctx.d(pay_day)),
                ("납입취급장소", f"{rng.choice(lx.BANKS)} {rng.choice(['강남중앙', '역삼', '판교', '여의도', '시청', '서초'])}지점"),
                ("신주의 배당기산일", ctx.d(date(pay_day.year, 1, 1))),
            ]),
            TBL(["배정대상자", "관계", "배정주식수", "인수금액"], rows),
        ],
        facts={
            "new_shares": new_shares, "issue_price": price, "total_amount": total,
            "share_class": kind, "payment_date": pay_day.isoformat(), "allottees": allottees,
        },
    )


def ag_convertible_bond(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    face = _amt(rng, 500_000_000, 30_000_000_000, 100_000_000)
    coupon = rng.choice([0.0, 0.0, 1.0, 1.5, 2.0, 3.0])
    ytm = round(coupon + rng.choice([0.0, 1.0, 2.0, 3.0, 4.0]), 1)
    conv_price = rng.choice([1_000, 1_500, 2_000, 2_500, 3_000, 5_000, 7_500, 10_000, 12_500, 20_000])
    conv_shares = face // conv_price
    years = rng.choice([2, 3, 3, 5])
    issue_day = ctx.future(5, 30)
    maturity = date(issue_day.year + years, issue_day.month, issue_day.day)
    series = ctx.bond_series
    ctx.bond_series += 1
    return AgendaItem(
        kind="convertible_bond",
        title=f"제{series}회 무기명식 이권부 무보증 사모 전환사채 발행의 건",
        blocks=[
            P(f"의장은 {rng.choice(['운영자금', '시설자금', '타법인 증권 취득자금', '채무상환자금'])} 조달을 위한 "
              f"전환사채 발행의 필요성을 설명하고 다음의 조건으로 발행할 것을 부의하였다."),
            KV([
                ("사채의 명칭", f"{ctx.company.full_name(ctx.style)} 제{series}회 무보증 사모 전환사채"),
                ("사채의 권면총액", ctx.money(face)),
                ("표면이자율", f"연 {coupon:.1f}%"),
                ("만기보장수익률", f"연 {ytm:.1f}%"),
                ("사채 발행일", ctx.d(issue_day)),
                ("사채 만기일", ctx.d(maturity)),
                ("전환가액", f"1주당 {comma(conv_price)}원"),
                ("전환에 따라 발행할 주식", f"기명식 보통주식 {comma(conv_shares)}주"),
                ("전환청구기간", f"{ctx.d(issue_day + timedelta(days=365))}부터 {ctx.d(maturity - timedelta(days=30))}까지"),
                ("원리금 지급방법", rng.choice(["만기일시상환", "만기일시상환(3개월 후급 이자지급)"])),
            ]),
        ],
        facts={
            "face_value": face, "coupon_rate": coupon, "ytm": ytm,
            "conversion_price": conv_price, "convertible_shares": conv_shares,
            "issue_date": issue_day.isoformat(), "maturity_date": maturity.isoformat(),
            "series": series,
        },
    )


def ag_warrant_bond(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    face = _amt(rng, 500_000_000, 20_000_000_000, 100_000_000)
    ex_price = rng.choice([1_000, 2_000, 2_500, 3_000, 5_000, 8_000, 10_000])
    ex_shares = face // ex_price
    coupon = rng.choice([1.0, 2.0, 3.0, 4.0])
    years = rng.choice([2, 3, 5])
    issue_day = ctx.future(5, 30)
    series = ctx.bond_series
    ctx.bond_series += 1
    return AgendaItem(
        kind="warrant_bond",
        title=f"제{series}회 무기명식 이권부 무보증 사모 신주인수권부사채 발행의 건",
        blocks=[
            P("의장은 다음과 같은 조건으로 신주인수권부사채를 발행하고자 한다는 뜻을 밝히고 이를 부의하였다."),
            KV([
                ("사채의 권면총액", ctx.money(face)),
                ("표면이자율", f"연 {coupon:.1f}%"),
                ("신주인수권 행사가액", f"1주당 {comma(ex_price)}원"),
                ("행사 시 발행할 주식수", f"기명식 보통주식 {comma(ex_shares)}주"),
                ("사채 발행일", ctx.d(issue_day)),
                ("사채 만기", f"발행일로부터 {years}년"),
                ("신주인수권 행사기간", f"발행일 익일부터 만기일 1개월 전까지"),
                ("분리형 여부", rng.choice(["비분리형", "비분리형", "분리형"])),
            ]),
        ],
        facts={
            "face_value": face, "exercise_price": ex_price, "exercise_shares": ex_shares,
            "coupon_rate": coupon, "issue_date": issue_day.isoformat(), "series": series,
        },
    )


def ag_ceo_election(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    pool = [d for d in ctx.directors if d.role == "사내이사"] or ctx.directors
    pick = rng.choice(pool)
    term = rng.choice([2, 3, 3])
    start = ctx.meeting_date
    reason = rng.choice([
        "전임 대표이사의 임기만료",
        "전임 대표이사의 일신상의 사유에 의한 사임",
        "경영 효율화를 위한 각자대표 체제 전환",
        "정기주주총회에서의 이사 재선임에 따른 대표이사 재선임",
    ])
    return AgendaItem(
        kind="ceo_election",
        title=rng.choice(["대표이사 선임의 건", "대표이사 선임 및 취임의 건"]),
        blocks=[
            P(f"의장은 {reason}(으)로 대표이사를 선임할 필요가 있음을 설명하고, "
              f"정관 제{rng.randint(28, 40)}조에 따라 이사 중에서 대표이사를 선임할 것을 부의하였다."),
            KV([
                ("선임 대상자", f"{pick.display(ctx.style)} ({pick.role})"),
                ("직위", rng.choice(["대표이사", "대표이사 사장", "각자대표이사"])),
                ("취임일", ctx.d(start)),
                ("임기", f"{term}년(이사로서의 잔여임기와 동일)"),
            ]),
            P(f"피선임자 {pick.name}은(는) 그 자리에서 취임을 승낙하였다."),
        ],
        facts={"elected_name": pick.name, "term_years": term, "reason": reason},
    )


def _shareholder_meeting(ctx: Ctx, regular: bool) -> AgendaItem:
    rng = ctx.rng
    mday = ctx.future(25, 70)
    record = ctx.past(1, 60) if regular else ctx.future(3, 12)
    fy = ctx.meeting_date.year - 1 if regular else ctx.meeting_date.year
    term_no = rng.randint(3, 40)
    purposes: List[str] = []
    if regular:
        purposes.append(f"제{term_no}기({fy}. 1. 1. ~ {fy}. 12. 31.) 재무제표 승인의 건")
        purposes.append("이사 보수한도 승인의 건")
        purposes.append("감사 보수한도 승인의 건")
        if rng.random() < 0.5:
            purposes.append("이사 선임의 건")
        if rng.random() < 0.35:
            purposes.append("정관 일부 변경의 건")
    else:
        pool = [
            "정관 일부 변경의 건", "이사 선임의 건", "감사 선임의 건",
            "이사 보수한도 승인의 건", "주식매수선택권 부여 승인의 건",
            "자본감소의 건", "영업의 중요한 일부 양도 승인의 건", "합병계약서 승인의 건",
        ]
        purposes = rng.sample(pool, rng.randint(1, 3))
    place = rng.choice([
        f"{ctx.company.address} {rng.choice(['대회의실', '본사 강당', '3층 회의실'])}",
        f"{nm.address(rng)} {rng.choice(['회의실', '세미나실'])}",
    ])
    return AgendaItem(
        kind="agm_convocation" if regular else "egm_convocation",
        title=(f"제{term_no}기 정기주주총회 소집의 건" if regular
               else "임시주주총회 소집의 건"),
        blocks=[
            P(f"의장은 상법 제362조 및 정관 제{rng.randint(18, 24)}조에 따라 "
              f"{'정기' if regular else '임시'}주주총회를 다음과 같이 소집할 것을 부의하였다."),
            KV([
                ("일시", f"{ctx.d(mday)} {ctx.style.fmt_time(time(rng.choice([9, 10, 11, 14, 15]), rng.choice([0, 0, 30])))}"),
                ("장소", place),
                ("기준일", ctx.d(record)),
                ("주주명부 폐쇄기간", f"{ctx.d(record + timedelta(days=1))} ~ {ctx.d(record + timedelta(days=rng.randint(7, 20)))}"),
            ]),
            P("회의의 목적사항"),
            LST(([ "보고사항: 감사보고, 영업보고, 내부회계관리제도 운영실태 보고"] if regular else [])
                + [f"부의안건 제{i}호: {t}" for i, t in enumerate(purposes, start=1)]),
        ],
        facts={
            "term_no": term_no, "meeting_date": mday.isoformat(),
            "record_date": record.isoformat(), "place": place, "purposes": purposes,
        },
    )


def ag_agm(ctx: Ctx) -> AgendaItem:
    return _shareholder_meeting(ctx, True)


def ag_egm(ctx: Ctx) -> AgendaItem:
    return _shareholder_meeting(ctx, False)


def ag_financial_statements(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    fy = ctx.meeting_date.year - 1
    revenue = _amt(rng, 3_000_000_000, 900_000_000_000, 1_000_000)
    op_margin = rng.uniform(-0.06, 0.22)
    op_income = int(revenue * op_margin / 1_000_000) * 1_000_000
    net_income = int(op_income * rng.uniform(0.45, 0.95) / 1_000_000) * 1_000_000
    equity = _amt(rng, max(1_000_000_000, revenue // 4), max(2_000_000_000, revenue * 2), 1_000_000)
    liabilities = _amt(rng, equity // 3, equity * 3, 1_000_000)
    assets = equity + liabilities
    term_no = rng.randint(3, 45)
    return AgendaItem(
        kind="financial_statements",
        title=f"제{term_no}기({fy}. 1. 1. ~ {fy}. 12. 31.) 재무제표 및 영업보고서 승인의 건",
        blocks=[
            P(f"의장은 상법 제447조에 따라 제{term_no}기 재무제표와 영업보고서를 작성하여 "
              f"감사의 감사를 받았음을 보고하고, 이사회의 승인을 요청하였다."),
            TBL(["구분", "금액(원)"], [
                ["자산총계", comma(assets)],
                ["부채총계", comma(liabilities)],
                ["자본총계", comma(equity)],
                ["매출액", comma(revenue)],
                ["영업이익", comma(op_income)],
                ["당기순이익", comma(net_income)],
            ]),
            P(f"감사 {ctx.auditors[0].name if ctx.auditors else '미선임'}은(는) 위 재무제표가 "
              f"회사의 재무상태와 경영성과를 적정하게 표시하고 있다는 의견을 진술하였다."
              if ctx.auditors else "감사 미선임 회사로서 감사의견 진술은 생략하였다."),
        ],
        facts={
            "term_no": term_no, "fiscal_year": fy, "assets": assets, "liabilities": liabilities,
            "equity": equity, "revenue": revenue, "operating_income": op_income,
            "net_income": net_income,
        },
    )


def ag_branch(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    action = rng.choice(["설치", "설치", "이전", "폐지"])
    addr = nm.address(rng)
    label = rng.choice(["지점", "지점", "영업소", "사무소", "연구소"])
    bname = f"{rng.choice(['서울', '부산', '대구', '광주', '대전', '울산', '판교', '동탄', '송도', '창원', '구미', '천안'])}{label}"
    when = ctx.future(3, 60)
    kv = [("명칭", bname), ("소재지", addr), (f"{action}일", ctx.d(when))]
    if action == "이전":
        kv.insert(1, ("종전 소재지", nm.address(rng)))
    return AgendaItem(
        kind="branch",
        title=f"{label} {action}의 건",
        blocks=[
            P(f"의장은 {rng.choice(['영업망 확대', '거래처 근접 대응', '운영 효율화', '임차계약 만료'])}을(를) 위하여 "
              f"{label}을(를) {action}할 필요가 있음을 설명하고 이를 부의하였다."),
            KV(kv),
            P(f"위 {action}에 따른 변경등기 및 관련 절차 일체는 대표이사에게 위임하기로 하였다."),
        ],
        facts={"action": action, "branch_name": bname, "address": addr, "effective_date": when.isoformat()},
    )


def ag_head_office_move(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    new_addr = nm.address(rng)
    when = ctx.future(7, 60)
    same_city = new_addr.split()[0] == ctx.company.address.split()[0]
    return AgendaItem(
        kind="head_office_move",
        title="본점 이전의 건",
        blocks=[
            P("의장은 사무공간 확보 및 임차조건 개선을 위하여 본점을 이전하고자 한다는 뜻을 밝히고 이를 부의하였다."),
            KV([
                ("현 본점 소재지", ctx.company.address),
                ("이전할 소재지", new_addr),
                ("이전 예정일", ctx.d(when)),
                ("정관 변경 필요 여부",
                 "불요(동일 특별시·광역시·시·군 내 이전)" if same_city else "필요(주주총회 결의 대상)"),
            ]),
        ],
        facts={"new_address": new_addr, "effective_date": when.isoformat(),
               "requires_articles_change": not same_city},
    )


def ag_articles_amendment(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    rows = []
    changes = []
    candidates = [
        ("제2조(목적)", "현행 각 호의 사업", "현행 각 호에 다음 사업을 추가한다"),
        ("제5조(발행예정주식총수)",
         f"{comma(ctx.company.authorized_shares)}주",
         f"{comma(ctx.company.authorized_shares * rng.choice([2, 4, 5, 10]))}주"),
        ("제8조(주식의 종류)", "보통주식 및 우선주식", "보통주식, 우선주식 및 상환전환우선주식"),
        ("제10조(신주인수권)", "주주는 소유 주식수에 비례하여 신주를 배정받는다",
         "이사회 결의로 제3자에게 신주를 배정할 수 있다"),
        ("제14조(전환사채의 발행)", f"{ctx.style.fmt_money(_amt(rng, 1_000_000_000, 10_000_000_000, 1_000_000_000))} 한도",
         f"{ctx.style.fmt_money(_amt(rng, 20_000_000_000, 100_000_000_000, 10_000_000_000))} 한도"),
        ("제33조(이사의 수)", f"이사는 {rng.randint(3, 4)}명 이상", f"이사는 {rng.randint(5, 9)}명 이내"),
        ("제45조(사업연도)", "매년 1월 1일부터 12월 31일까지", "매년 4월 1일부터 다음해 3월 31일까지"),
    ]
    for art, before, after in rng.sample(candidates, rng.randint(2, 4)):
        rows.append([art, before, after])
        changes.append({"article": art, "before": before, "after": after})
    return AgendaItem(
        kind="articles_amendment",
        title="정관 일부 변경의 건(주주총회 부의)",
        blocks=[
            P("의장은 사업환경 변화와 관계법령 개정사항을 반영하기 위하여 정관을 다음과 같이 변경하고, "
              "이를 주주총회에 부의하고자 한다는 뜻을 밝혔다."),
            TBL(["조항", "현    행", "변  경  안"], rows),
        ],
        facts={"changes": changes},
    )


def ag_borrowing(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    bank = rng.choice(lx.BANKS)
    limit = _amt(rng, 300_000_000, 50_000_000_000, 100_000_000)
    rate = round(rng.uniform(3.2, 8.9), 2)
    months = rng.choice([6, 12, 12, 24, 36, 60])
    max_claim = int(limit * rng.choice([1.2, 1.3]))
    kind = rng.choice(["운전자금대출", "시설자금대출", "한도대출(마이너스통장)", "일반자금대출", "산업운영자금대출"])
    return AgendaItem(
        kind="borrowing",
        title=f"{bank}(으)로부터의 자금 차입의 건",
        blocks=[
            P(f"의장은 {rng.choice(['원자재 구매대금 결제', '신규 설비 도입', '기존 차입금 대환', '운영자금 확보'])}를 위하여 "
              f"다음과 같이 금융기관으로부터 자금을 차입할 필요가 있음을 설명하였다."),
            KV([
                ("차입처", bank),
                ("차입 종류", kind),
                ("차입 한도", ctx.money(limit)),
                ("적용 이자율", f"연 {rate:.2f}%(변동금리, 기준금리 연동)"),
                ("차입 기간", f"{months}개월(기한연장 가능)"),
                ("담보", rng.choice([
                    f"회사 소유 부동산 근저당권 설정(채권최고액 {comma(max_claim)}원)",
                    f"대표이사 연대보증 및 예금담보 {comma(int(limit * 0.1))}원",
                    "신용(무담보)",
                    f"기술보증기금 보증서({comma(int(limit * 0.85))}원)",
                ])),
            ]),
            P("의장은 위 차입과 관련한 약정 체결 및 담보 제공에 관한 일체의 권한을 "
              "대표이사에게 위임할 것을 함께 부의하였다."),
        ],
        facts={"lender": bank, "limit": limit, "rate": rate, "months": months, "loan_type": kind},
    )


def ag_equity_investment(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    target = nm.counterparty(rng)
    shares = _amt(rng, 1_000, 500_000, 100)
    unit = rng.choice([5_000, 10_000, 20_000, 50_000, 100_000, 250_000])
    amount = shares * unit
    ratio = round(rng.uniform(4.5, 100.0), 2)
    return AgendaItem(
        kind="equity_investment",
        title=f"타법인({target}) 주식 취득의 건",
        blocks=[
            P(f"의장은 {rng.choice(['사업 다각화', '공급망 안정화', '핵심 기술 확보', '해외 판로 확대'])}을(를) 위하여 "
              f"{target}의 주식을 취득하고자 한다는 뜻을 밝히고 이를 부의하였다."),
            KV([
                ("취득 대상회사", target),
                ("취득 주식수", f"기명식 보통주식 {comma(shares)}주"),
                ("1주당 취득단가", f"{comma(unit)}원"),
                ("취득금액 총액", ctx.money(amount)),
                ("취득 후 지분율", f"{ratio:.2f}%"),
                ("취득 예정일", ctx.d(ctx.future(10, 90))),
                ("취득 방법", rng.choice(["제3자배정 유상증자 참여", "구주 양수", "현금 취득", "주식양수도계약 체결"])),
            ]),
        ],
        facts={"target": target, "shares": shares, "unit_price": unit,
               "amount": amount, "ownership_ratio": ratio},
    )


def ag_real_estate(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    action = rng.choice(["취득", "취득", "처분"])
    addr = nm.address(rng).split(",")[0]
    sqm = round(rng.uniform(180.0, 9800.0), 2)
    pyeong = round(sqm / 3.305785, 2)
    price = _amt(rng, 300_000_000, 40_000_000_000, 10_000_000)
    contract = ctx.future(1, 20)
    balance = contract + timedelta(days=rng.choice([30, 45, 60, 90]))
    return AgendaItem(
        kind="real_estate",
        title=f"부동산 {action}의 건",
        blocks=[
            P(f"의장은 {rng.choice(['물류창고 확보', '생산시설 증설', '유휴자산 정리', '사옥 확보'])}를 위한 "
              f"부동산 {action}의 필요성을 설명하고 다음과 같이 부의하였다."),
            KV([
                ("소재지", addr),
                ("지목/용도", rng.choice(["대(垈)/공장용지", "공장용지", "대(垈)/업무시설", "창고용지", "대(垈)/근린생활시설"])),
                ("면적", f"{sqm:,.2f}㎡({pyeong:,.2f}평)"),
                (f"{action}가액", ctx.money(price)),
                ("계약예정일", ctx.d(contract)),
                ("잔금지급일", ctx.d(balance)),
                ("거래상대방", nm.counterparty(rng)),
            ]),
        ],
        facts={"action": action, "address": addr, "area_sqm": sqm, "area_pyeong": pyeong,
               "price": price, "contract_date": contract.isoformat(),
               "balance_date": balance.isoformat()},
    )


def ag_stock_option(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    n = rng.randint(2, 6)
    cap = max(1, int(ctx.company.shares_issued * 0.05))
    rows, grants, total = [], [], 0
    positions = ["연구소장", "최고기술책임자", "최고재무책임자", "영업본부장", "개발팀장",
                 "책임연구원", "선임연구원", "생산본부장", "경영지원실장", "해외사업팀장"]
    ex_price = rng.choice([1_000, 2_000, 3_000, 5_000, 7_000, 10_000, 15_000])
    for _ in range(n):
        name, _h = ctx.person()
        qty = _amt(rng, 1_000, max(2_000, cap // max(1, n)), 500)
        total += qty
        pos = rng.choice(positions)
        rows.append([name, pos, f"{comma(qty)}주", f"{comma(ex_price)}원"])
        grants.append({"name": name, "position": pos, "shares": qty})
    start = ctx.future(720, 760)
    return AgendaItem(
        kind="stock_option",
        title="주식매수선택권 부여의 건(주주총회 부의)",
        blocks=[
            P("의장은 임직원의 장기 성과 동기 부여를 위하여 상법 제340조의2 및 정관에 따라 "
              "다음과 같이 주식매수선택권을 부여하고, 이를 주주총회에 부의할 것을 제안하였다."),
            TBL(["성명", "직위", "부여주식수", "행사가격"], rows),
            KV([
                ("부여주식 총수", f"기명식 보통주식 {comma(total)}주"),
                ("발행주식총수 대비 비율", f"{total / ctx.company.shares_issued * 100:.2f}%"),
                ("부여방법", rng.choice(["신주발행 교부", "자기주식 교부", "차액 현금정산"])),
                ("행사기간", f"{ctx.d(start)}부터 {ctx.d(date(start.year + rng.choice([3, 5]), start.month, start.day))}까지"),
                ("가득조건", f"부여일로부터 {rng.choice([2, 2, 3])}년 이상 재임·재직"),
            ]),
        ],
        facts={"grants": grants, "total_shares": total, "exercise_price": ex_price,
               "ratio_pct": round(total / ctx.company.shares_issued * 100, 2)},
    )


def ag_related_party(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    pick = rng.choice(ctx.directors)
    other = nm.counterparty(rng)
    amount = _amt(rng, 50_000_000, 8_000_000_000, 10_000_000)
    months = rng.choice([6, 12, 12, 24, 36])
    nature = rng.choice([
        "원재료 공급계약 체결", "용역 위탁계약 체결", "부동산 임대차계약 체결",
        "자금 대여", "설비 매매계약 체결", "상표권 사용계약 체결",
    ])
    return AgendaItem(
        kind="related_party",
        title=f"이사와 회사 간 거래 승인의 건(상법 제398조)",
        blocks=[
            P(f"의장은 {pick.display(ctx.style)} 이사가 대표를 겸하고 있는 {other}와(과) "
              f"{nature}을(를) 하고자 하므로, 상법 제398조에 따라 이사회의 사전 승인이 필요함을 설명하였다."),
            KV([
                ("거래상대방", other),
                ("특별이해관계 있는 이사", pick.display(ctx.style)),
                ("관계", rng.choice(["해당 이사가 대표이사인 법인", "해당 이사의 배우자가 지배하는 법인",
                                    "해당 이사가 100분의 50 이상의 지분을 보유한 법인"])),
                ("거래의 내용", nature),
                ("거래금액", ctx.money(amount)),
                ("거래기간", f"{months}개월"),
                ("거래조건", rng.choice(["동종 거래의 일반적인 조건과 동일", "시장가격 대비 불리하지 아니한 조건",
                                       "복수 견적 비교 후 최저가 기준"])),
            ]),
            P(f"의장은 상법 제398조에 따라 {pick.name} 이사는 본 의안에 관하여 의결권을 행사할 수 없음을 고지하고, "
              f"동 이사를 제외한 나머지 이사들의 의결에 부쳤다."),
        ],
        facts={"counterparty": other, "interested_director": pick.name,
               "amount": amount, "months": months, "nature": nature},
        interested_director=pick.name,
        special_majority=True,
    )


def ag_regulation(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    reg = rng.choice(lx.REGULATION_NAMES)
    action = rng.choice(["제정", "개정", "개정", "전부개정"])
    items = rng.sample([
        "이사회 부의사항의 범위 조정",
        "전결권한 금액 기준 상향",
        "내부신고 접수 및 처리 절차 신설",
        "성과평가 지표 및 지급률 구간 조정",
        "겸직 승인 절차 명문화",
        "개인정보 처리 위탁 관리 조항 신설",
        "중대재해처벌법 대응 조직 및 책임 명확화",
        "부패방지 및 이해충돌 방지 조항 신설",
        "원격근무 및 유연근무제 시행 근거 마련",
    ], rng.randint(2, 4))
    eff = ctx.future(1, 60)
    return AgendaItem(
        kind="regulation",
        title=f"{reg} {action}의 건",
        blocks=[
            P(f"의장은 {reg}을(를) 다음과 같이 {action}하고자 한다는 뜻을 밝히고 이를 부의하였다."),
            P("주요 내용"),
            LST(items),
            KV([("시행일", ctx.d(eff)),
                ("경과조치", rng.choice(["시행일 이전 진행 중인 사항은 종전 규정에 따른다",
                                       "별도의 경과조치를 두지 아니한다"]))]),
        ],
        facts={"regulation": reg, "action": action, "items": items,
               "effective_date": eff.isoformat()},
    )


def ag_treasury_stock(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    shares = _amt(rng, 1_000, max(2_000, ctx.company.shares_issued // 10), 100)
    price = rng.choice([1_000, 2_500, 5_000, 8_000, 12_000, 18_000, 25_000])
    amount = shares * price
    start = ctx.future(3, 20)
    end = start + timedelta(days=rng.choice([30, 60, 90, 180]))
    return AgendaItem(
        kind="treasury_stock",
        title="자기주식 취득의 건",
        blocks=[
            P("의장은 주주가치 제고 및 주가안정을 위하여 상법 제341조에 따라 배당가능이익의 범위 내에서 "
              "자기주식을 취득하고자 한다는 뜻을 밝히고 이를 부의하였다."),
            KV([
                ("취득할 주식의 종류", "기명식 보통주식"),
                ("취득 예정 주식수", f"{comma(shares)}주"),
                ("취득 예정 단가", f"1주당 {comma(price)}원"),
                ("취득 예정금액", ctx.money(amount)),
                ("취득 기간", f"{ctx.d(start)} ~ {ctx.d(end)}"),
                ("취득 방법", rng.choice(["장내매수", "자기주식 취득 신탁계약 체결", "주주 전체에 대한 취득의 통지에 의한 방법"])),
                ("취득 재원", "직전 결산기 배당가능이익 범위 내"),
            ]),
        ],
        facts={"shares": shares, "unit_price": price, "amount": amount,
               "start_date": start.isoformat(), "end_date": end.isoformat()},
    )


def ag_interim_dividend(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    dps = rng.choice([50, 100, 150, 200, 250, 300, 500, 750, 1_000, 1_500])
    target_shares = ctx.company.shares_issued - _amt(rng, 0, max(1, ctx.company.shares_issued // 20), 100)
    total = dps * target_shares
    record = ctx.past(0, 30)
    pay = ctx.future(15, 45)
    return AgendaItem(
        kind="interim_dividend",
        title="중간배당 결의의 건",
        blocks=[
            P(f"의장은 상법 제462조의3 및 정관 제{rng.randint(48, 56)}조에 따라 중간배당을 실시하고자 한다는 뜻을 "
              f"밝히고 다음과 같이 부의하였다."),
            KV([
                ("배당 기준일", ctx.d(record)),
                ("배당 대상 주식수", f"기명식 보통주식 {comma(target_shares)}주"),
                ("1주당 배당금", f"{comma(dps)}원"),
                ("배당금 총액", ctx.money(total)),
                ("배당금 지급 예정일", ctx.d(pay)),
                ("배당 재원", "직전 결산기 대차대조표상 배당가능이익"),
            ]),
        ],
        facts={"dividend_per_share": dps, "target_shares": target_shares,
               "total_dividend": total, "record_date": record.isoformat(),
               "payment_date": pay.isoformat()},
    )


def ag_guarantee(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    sub = nm.counterparty(rng)
    bank = rng.choice(lx.BANKS)
    amount = _amt(rng, 200_000_000, 20_000_000_000, 100_000_000)
    months = rng.choice([12, 12, 24, 36])
    return AgendaItem(
        kind="guarantee",
        title=f"계열회사({sub})에 대한 지급보증의 건",
        blocks=[
            P(f"의장은 {sub}의 {bank}에 대한 차입금과 관련하여 회사가 지급보증을 제공할 필요가 있음을 설명하였다."),
            KV([
                ("피보증인", sub),
                ("보증채권자", bank),
                ("보증금액", ctx.money(amount)),
                ("보증기간", f"{months}개월"),
                ("보증의 종류", rng.choice(["연대보증", "한정근보증", "특정채무보증"])),
                ("자기자본 대비 비율", f"{rng.uniform(1.5, 35.0):.2f}%"),
            ]),
        ],
        facts={"guarantee_for": sub, "creditor": bank, "amount": amount, "months": months},
    )


def ag_new_business(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    added = nm.business_purposes(rng, rng.randint(1, 3))
    return AgendaItem(
        kind="new_business",
        title="사업목적 추가를 위한 정관 변경의 건(주주총회 부의)",
        blocks=[
            P("의장은 신규 사업 추진을 위하여 정관 제2조(목적)에 다음 사업을 추가하고, "
              "이를 주주총회에 부의하고자 한다는 뜻을 밝혔다."),
            LST([f"{i}. {p}" for i, p in enumerate(added, start=len(ctx.company.business) + 1)]),
            KV([("추진 예정시기", ctx.d(ctx.future(60, 400))),
                ("예상 투자규모", ctx.money(_amt(rng, 100_000_000, 20_000_000_000, 100_000_000)))]),
        ],
        facts={"added_purposes": added},
    )


def ag_remuneration(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    rows = []
    data = []
    for title, lo, hi in [("대표이사", 150_000_000, 900_000_000),
                          ("사내이사", 80_000_000, 400_000_000),
                          ("사외이사", 24_000_000, 90_000_000),
                          ("감사", 20_000_000, 120_000_000)]:
        base = _amt(rng, lo, hi, 1_000_000)
        bonus = int(base * rng.choice([0.0, 0.3, 0.5, 1.0]) / 1_000_000) * 1_000_000
        rows.append([title, f"{comma(base)}원", f"{comma(bonus)}원", f"{comma(base + bonus)}원"])
        data.append({"title": title, "base": base, "bonus": bonus, "total": base + bonus})
    return AgendaItem(
        kind="remuneration",
        title="임원 보수 지급기준 승인의 건",
        blocks=[
            P(f"의장은 {ctx.meeting_date.year}년도 임원 보수 지급기준을 다음과 같이 정할 것을 부의하였다. "
              f"다만 이사 전체의 보수총액은 주주총회에서 승인한 한도 내로 한다."),
            TBL(["직위", "연간 기본보수", "성과급 한도", "합계"], rows),
        ],
        facts={"remuneration": data},
    )


def ag_subsidiary(ctx: Ctx) -> AgendaItem:
    rng = ctx.rng
    sub = nm.counterparty(rng)
    capital = _amt(rng, 100_000_000, 10_000_000_000, 10_000_000)
    ratio = rng.choice([100.0, 100.0, 80.0, 70.0, 60.0, 51.0])
    invest = int(capital * ratio / 100)
    return AgendaItem(
        kind="subsidiary",
        title=f"자회사({sub}) 설립의 건",
        blocks=[
            P("의장은 신규 사업의 독립적 운영을 위하여 자회사를 설립하고자 한다는 뜻을 밝히고 이를 부의하였다."),
            KV([
                ("상호", sub),
                ("소재지", nm.address(rng)),
                ("설립 자본금", ctx.money(capital)),
                ("당사 출자금액", ctx.money(invest)),
                ("당사 지분율", f"{ratio:.1f}%"),
                ("주요 사업", nm.business_purposes(rng, 1)[0]),
                ("설립 예정일", ctx.d(ctx.future(20, 120))),
            ]),
        ],
        facts={"subsidiary": sub, "capital": capital, "investment": invest, "ratio": ratio},
    )


GENERATORS: Dict[str, Callable[[Ctx], AgendaItem]] = {
    "third_party_issue": ag_third_party_issue,
    "convertible_bond": ag_convertible_bond,
    "warrant_bond": ag_warrant_bond,
    "ceo_election": ag_ceo_election,
    "agm_convocation": ag_agm,
    "egm_convocation": ag_egm,
    "financial_statements": ag_financial_statements,
    "branch": ag_branch,
    "head_office_move": ag_head_office_move,
    "articles_amendment": ag_articles_amendment,
    "borrowing": ag_borrowing,
    "equity_investment": ag_equity_investment,
    "real_estate": ag_real_estate,
    "stock_option": ag_stock_option,
    "related_party": ag_related_party,
    "regulation": ag_regulation,
    "treasury_stock": ag_treasury_stock,
    "interim_dividend": ag_interim_dividend,
    "guarantee": ag_guarantee,
    "new_business": ag_new_business,
    "remuneration": ag_remuneration,
    "subsidiary": ag_subsidiary,
}

# 자주 등장하는 의안일수록 가중치를 높여 실제 분포에 가깝게 만든다.
WEIGHTS: Dict[str, float] = {
    "third_party_issue": 9, "convertible_bond": 7, "warrant_bond": 3,
    "ceo_election": 5, "agm_convocation": 6, "egm_convocation": 6,
    "financial_statements": 6, "branch": 5, "head_office_move": 3,
    "articles_amendment": 5, "borrowing": 9, "equity_investment": 6,
    "real_estate": 5, "stock_option": 5, "related_party": 5,
    "regulation": 5, "treasury_stock": 3, "interim_dividend": 3,
    "guarantee": 4, "new_business": 4, "remuneration": 4, "subsidiary": 3,
}


# 화면에 보여줄 한글 이름.
KIND_LABELS: Dict[str, str] = {
    "third_party_issue": "유상증자(제3자배정)",
    "convertible_bond": "전환사채 발행",
    "warrant_bond": "신주인수권부사채 발행",
    "ceo_election": "대표이사 선임",
    "agm_convocation": "정기주주총회 소집",
    "egm_convocation": "임시주주총회 소집",
    "financial_statements": "재무제표 승인",
    "branch": "지점 설치·이전·폐지",
    "head_office_move": "본점 이전",
    "articles_amendment": "정관 변경",
    "borrowing": "금융기관 차입",
    "equity_investment": "타법인 주식 취득",
    "real_estate": "부동산 취득·처분",
    "stock_option": "주식매수선택권 부여",
    "related_party": "이사와 회사 간 거래(제398조)",
    "regulation": "사내규정 제·개정",
    "treasury_stock": "자기주식 취득",
    "interim_dividend": "중간배당",
    "guarantee": "지급보증",
    "new_business": "사업목적 추가",
    "remuneration": "임원 보수 지급기준",
    "subsidiary": "자회사 설립",
}
