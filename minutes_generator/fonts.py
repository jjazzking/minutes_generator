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


# ---------------------------------------------------------------- 글리프 확인

_COVER_CACHE: dict = {}


def covers(path: str, index: int, text: str) -> bool:
    """글꼴 파일이 text 의 모든 글자를 가지고 있는지 본다.

    나눔명조처럼 한자가 빠진 글꼴이 있어 한자 혼용 문서에서 네모(두부)가 찍히는 것을 막는다.
    Pillow 가 없으면 판단하지 않고 True 를 준다.
    """
    key = (path, index, text)
    if key in _COVER_CACHE:
        return _COVER_CACHE[key]
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return True
    try:
        try:
            font = ImageFont.truetype(path, 40, index=index)
        except TypeError:
            font = ImageFont.truetype(path, 40)
    except OSError:
        _COVER_CACHE[key] = False
        return False

    def bitmap(ch: str) -> bytes:
        img = Image.new("L", (56, 56), 0)
        ImageDraw.Draw(img).text((28, 28), ch, font=font, fill=255, anchor="mm")
        return img.tobytes()

    missing = bitmap("")          # 어떤 글꼴에도 없는 사용자 영역 문자
    ok = all(ch.isspace() or bitmap(ch) != missing for ch in set(text))
    _COVER_CACHE[key] = ok
    return ok


def find_font_for(family: str, text: str = "") -> Optional[Candidate]:
    """text 를 모두 표현할 수 있는 글꼴을 고른다.

    요청한 계열이 글자를 다 담지 못하면 다른 계열로 넘어간다.
    """
    seen = []
    for fam in (family, "myeongjo" if family == "gothic" else "gothic"):
        hit = find_font(fam)
        if hit and hit not in seen:
            seen.append(hit)
    for path, index in seen:
        if not text or covers(path, index, text):
            return path, index
    return seen[0] if seen else None


def find_bold_for(family: str, text: str = "") -> Optional[Candidate]:
    """굵은 글꼴도 같은 방식으로 고른다. 없으면 None."""
    for fam in (family, "myeongjo" if family == "gothic" else "gothic"):
        hit = find_bold(fam)
        if hit and (not text or covers(hit[0], hit[1], text)):
            return hit
    return None


def supports(text: str) -> bool:
    """설치된 글꼴 중 하나라도 text 를 온전히 표현할 수 있는지."""
    for fam in ("gothic", "myeongjo"):
        hit = find_font(fam)
        if hit and covers(hit[0], hit[1], text):
            return True
    return False
