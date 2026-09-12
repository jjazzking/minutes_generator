# -*- coding: utf-8 -*-
"""PDF 출력에 쓸 한글 글꼴을 찾는다.

운영체제마다 기본 한글 글꼴 경로가 다르므로 후보를 훑어 처음 발견된 것을 쓴다.
환경변수 MINUTES_FONT_GOTHIC / MINUTES_FONT_MYEONGJO 로 직접 지정할 수 있다.
"""

import glob
import os
from typing import List, Optional, Tuple

# (경로, TTC 내부 글꼴 번호)
Candidate = Tuple[str, int]

GOTHIC_CANDIDATES: List[Candidate] = [
    # Windows
    ("C:/Windows/Fonts/malgun.ttf", 0),          # 맑은 고딕
    ("C:/Windows/Fonts/NanumGothic.ttf", 0),
    ("C:/Windows/Fonts/gulim.ttc", 0),           # 굴림
    ("C:/Windows/Fonts/dotum.ttc", 0),           # 돋움
    # macOS
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", 0),
    ("/Library/Fonts/NanumGothic.ttf", 0),
    # Linux
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 0),
    ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 1),
]

MYEONGJO_CANDIDATES: List[Candidate] = [
    # Windows
    ("C:/Windows/Fonts/batang.ttc", 0),          # 바탕
    ("C:/Windows/Fonts/gungsuh.ttc", 0),         # 궁서
    ("C:/Windows/Fonts/NanumMyeongjo.ttf", 0),
    # macOS
    ("/System/Library/Fonts/Supplemental/AppleMyungjo.ttf", 0),
    ("/Library/Fonts/NanumMyeongjo.ttf", 0),
    # Linux
    ("/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJKkr-Regular.otf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 1),
]

GLOB_FALLBACKS = [
    "/usr/share/fonts/**/*Nanum*.ttf",
    "/usr/share/fonts/**/*CJK*.ttc",
    "/usr/share/fonts/**/*CJK*.otf",
    os.path.expanduser("~/.fonts/**/*.ttf"),
    os.path.expanduser("~/Library/Fonts/*.ttf"),
]


def _first_existing(candidates: List[Candidate]) -> Optional[Candidate]:
    for path, index in candidates:
        if os.path.exists(path):
            return path, index
    return None


def _glob_any() -> Optional[Candidate]:
    for pattern in GLOB_FALLBACKS:
        for hit in sorted(glob.glob(pattern, recursive=True)):
            return hit, 0
    return None


def find_font(family: str = "gothic") -> Optional[Candidate]:
    """(글꼴 파일 경로, TTC 인덱스)를 돌려준다. 찾지 못하면 None."""
    env = os.environ.get(
        "MINUTES_FONT_MYEONGJO" if family == "myeongjo" else "MINUTES_FONT_GOTHIC")
    if env and os.path.exists(env):
        return env, 0

    table = MYEONGJO_CANDIDATES if family == "myeongjo" else GOTHIC_CANDIDATES
    hit = _first_existing(table)
    if hit:
        return hit
    other = GOTHIC_CANDIDATES if family == "myeongjo" else MYEONGJO_CANDIDATES
    hit = _first_existing(other)
    if hit:
        return hit
    return _glob_any()


def find_bold(family: str = "gothic") -> Optional[Candidate]:
    """굵은 글꼴. 없으면 None을 주고 호출 측에서 보통 글꼴로 대체한다."""
    env = os.environ.get("MINUTES_FONT_BOLD")
    if env and os.path.exists(env):
        return env, 0
    bold_tables = {
        "gothic": [
            ("C:/Windows/Fonts/malgunbd.ttf", 0),
            ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0),
            ("/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf", 0),
            ("/Library/Fonts/NanumGothicBold.ttf", 0),
        ],
        "myeongjo": [
            ("/usr/share/fonts/truetype/nanum/NanumMyeongjoBold.ttf", 0),
            ("/Library/Fonts/NanumMyeongjoBold.ttf", 0),
            ("C:/Windows/Fonts/batangb.ttc", 0),
        ],
    }
    return _first_existing(bold_tables.get(family, []))


def describe() -> str:
    """설치 상태를 사람이 읽을 수 있게 요약한다."""
    lines = []
    for fam in ("gothic", "myeongjo"):
        hit = find_font(fam)
        lines.append(f"{fam:9s}: {hit[0] if hit else '없음'}")
        bold = find_bold(fam)
        lines.append(f"{fam + ' bold':9s}: {bold[0] if bold else '없음(보통 글꼴로 대체)'}")
    return "\n".join(lines)
