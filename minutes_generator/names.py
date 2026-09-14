# -*- coding: utf-8 -*-
"""인명·상호·주소 무작위 생성기."""

import random
from typing import List, Tuple

from . import lexicon as lx


def person_name(rng: random.Random, used: set) -> Tuple[str, str]:
    """중복되지 않는 (한글 성명, 한자 성명)을 만든다."""
    for _ in range(200):
        sur = rng.choice(lx.SURNAMES)
        if rng.random() < 0.06:
            syllables = [rng.choice(lx.SINGLE_GIVEN)]   # 외자 이름
        else:
            syllables = [rng.choice(lx.GIVEN_FIRST), rng.choice(lx.GIVEN_SECOND)]
        given = "".join(syllables)
        name = sur + given
        if name in used:
            continue
        used.add(name)
        hanja = lx.SURNAME_HANJA.get(sur, "") + "".join(
            lx.GIVEN_HANJA.get(s, "〇") for s in syllables
        )
        return name, hanja
    raise RuntimeError("인명 생성 실패")


def company_name(rng: random.Random) -> str:
    head = rng.choice(lx.COMPANY_HEAD)
    if head not in lx.GEO_HEAD and rng.random() < 0.28:
        return head                      # 업종어 없는 단독 상호
    mid = rng.choice(lx.COMPANY_MID) if rng.random() < 0.18 else ""
    return head + mid + rng.choice(lx.COMPANY_TAIL)


def counterparty(rng: random.Random) -> str:
    base = company_name(rng)
    roll = rng.random()
    if roll < 0.45:
        return f"주식회사 {base}"
    if roll < 0.70:
        return f"{base} 주식회사"
    if roll < 0.82:
        return f"{base}(주)"
    if roll < 0.92:
        return rng.choice(lx.INVESTORS).format(c=base)
    return rng.choice(lx.FUND_NAMES).format(c=base, n=rng.randint(1, 12))


def address(rng: random.Random) -> str:
    sido, gus = rng.choice(lx.CITIES)
    gu = rng.choice(gus)
    road = rng.choice(lx.ROADS)
    num = rng.randint(1, 640)
    tail = ""
    if rng.random() < 0.55:
        tail = f", {rng.randint(2, 32)}층"
        if rng.random() < 0.35:
            tail += f" {rng.randint(201, 2410)}호"
    return f"{sido} {gu} {road} {num}{tail}"


def registry_office(rng: random.Random) -> str:
    return rng.choice([
        "서울중앙지방법원 등기국", "서울중앙지방법원 등기과", "수원지방법원 성남지원 등기계",
        "인천지방법원 등기국", "대전지방법원 등기국", "대구지방법원 등기국",
        "부산지방법원 등기국", "광주지방법원 등기국", "의정부지방법원 고양지원 등기계",
        "창원지방법원 등기국", "청주지방법원 등기계", "전주지방법원 등기계",
    ])


def business_purposes(rng: random.Random, n: int) -> List[str]:
    return rng.sample(lx.BUSINESS_PURPOSES, n)
