# -*- coding: utf-8 -*-
"""PDF 출력에 쓸 한글 글꼴을 찾는다.

운영체제마다 기본 한글 글꼴 경로가 다르므로 후보를 훑어 처음 발견된 것을 쓴다.
환경변수 MINUTES_FONT_GOTHIC / MINUTES_FONT_MYEONGJO 로 직접 지정할 수 있다.
"""

import glob
import os
import struct
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
    # AppleSDGothicNeo 는 CFF(PostScript) 아웃라인이라 reportlab 이 못 읽는다.
    # Pillow 는 읽을 수 있으므로 목록에는 두고, truetype_only 일 때만 걸러낸다.
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


# ------------------------------------------------------------ 글꼴 형식 판별

_TRUETYPE_TAGS = (b"\x00\x01\x00\x00", b"true", b"ttcf")

_TRUETYPE_CACHE: dict = {}


def _sfnt_tag(path: str, index: int) -> Optional[bytes]:
    """글꼴 파일(또는 TTC 안의 index 번째 글꼴)의 sfnt 버전 태그를 읽는다.

    ``b"OTTO"`` 면 CFF(PostScript) 아웃라인, 그 밖의 값이면 TrueType 이다.
    """
    try:
        with open(path, "rb") as fh:
            tag = fh.read(4)
            if tag == b"ttcf":                       # TTC: 내부 글꼴 오프셋을 따라간다
                fh.read(4)                           # version
                raw = fh.read(4)
                if len(raw) < 4:
                    return None
                count = struct.unpack(">I", raw)[0]
                if not 0 <= index < count:
                    return None
                raw = fh.read(4 * count)
                if len(raw) < 4 * count:
                    return None
                offsets = struct.unpack(">%dI" % count, raw)
                fh.seek(offsets[index])
                tag = fh.read(4)
            return tag if len(tag) == 4 else None
    except OSError:
        return None


def is_truetype(path: str, index: int = 0) -> bool:
    """reportlab 이 읽을 수 있는 TrueType 아웃라인 글꼴인지.

    reportlab 의 TTFont 은 glyf 테이블만 다루므로 CFF 아웃라인을 넘기면
    ``TTFError: ... postscript outlines are not supported`` 로 죽는다.
    무거운 파싱 대신 파일 머리 4바이트만 보고 미리 걸러낸다.
    """
    key = (path, index)
    if key not in _TRUETYPE_CACHE:
        _TRUETYPE_CACHE[key] = _sfnt_tag(path, index) in _TRUETYPE_TAGS
    return _TRUETYPE_CACHE[key]


def _acceptable(path: str, index: int, truetype_only: bool) -> bool:
    if not os.path.exists(path):
        return False
    return is_truetype(path, index) if truetype_only else True


def _first_existing(candidates: List[Candidate],
                    truetype_only: bool = False) -> Optional[Candidate]:
    for path, index in candidates:
        if _acceptable(path, index, truetype_only):
            return path, index
    return None


def _glob_any(truetype_only: bool = False) -> Optional[Candidate]:
    for pattern in GLOB_FALLBACKS:
        for hit in sorted(glob.glob(pattern, recursive=True)):
            if _acceptable(hit, 0, truetype_only):
                return hit, 0
    return None


def find_font(family: str = "gothic",
              truetype_only: bool = False) -> Optional[Candidate]:
    """(글꼴 파일 경로, TTC 인덱스)를 돌려준다. 찾지 못하면 None.

    truetype_only 를 켜면 CFF(PostScript) 아웃라인 글꼴을 건너뛴다.
    reportlab 으로 PDF를 찍을 때 필요하다. Pillow 로 그릴 때는 끄면 된다.
    """
    env = os.environ.get(
        "MINUTES_FONT_MYEONGJO" if family == "myeongjo" else "MINUTES_FONT_GOTHIC")
    if env and _acceptable(env, 0, truetype_only):
        return env, 0

    table = MYEONGJO_CANDIDATES if family == "myeongjo" else GOTHIC_CANDIDATES
    hit = _first_existing(table, truetype_only)
    if hit:
        return hit
    other = GOTHIC_CANDIDATES if family == "myeongjo" else MYEONGJO_CANDIDATES
    hit = _first_existing(other, truetype_only)
    if hit:
        return hit
    return _glob_any(truetype_only)


def find_bold(family: str = "gothic",
              truetype_only: bool = False) -> Optional[Candidate]:
    """굵은 글꼴. 없으면 None을 주고 호출 측에서 보통 글꼴로 대체한다."""
    env = os.environ.get("MINUTES_FONT_BOLD")
    if env and _acceptable(env, 0, truetype_only):
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
    return _first_existing(bold_tables.get(family, []), truetype_only)


def describe() -> str:
    """설치 상태를 사람이 읽을 수 있게 요약한다."""
    lines = []
    for fam in ("gothic", "myeongjo"):
        hit = find_font(fam)
        lines.append(f"{fam:9s}: {hit[0] if hit else '없음'}")
        bold = find_bold(fam)
        lines.append(f"{fam + ' bold':9s}: {bold[0] if bold else '없음(보통 글꼴로 대체)'}")

    lines.append("")
    lines.append("PDF(reportlab)용 — CFF 아웃라인 글꼴은 쓸 수 없어 제외한 결과:")
    for fam in ("gothic", "myeongjo"):
        hit = find_font(fam, truetype_only=True)
        lines.append(f"  {fam:9s}: {hit[0] if hit else '없음'}")
        bold = find_bold(fam, truetype_only=True)
        lines.append(f"  {fam + ' bold':9s}: {bold[0] if bold else '없음(보통 글꼴로 대체)'}")

    skipped = [path for path, index in GOTHIC_CANDIDATES + MYEONGJO_CANDIDATES
               if os.path.exists(path) and not is_truetype(path, index)]
    if skipped:
        lines.append("")
        lines.append("CFF 아웃라인이라 PDF에서 제외된 글꼴:")
        lines.extend(f"  {path}" for path in skipped)
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


def find_font_for(family: str, text: str = "",
                  truetype_only: bool = False) -> Optional[Candidate]:
    """text 를 모두 표현할 수 있는 글꼴을 고른다.

    요청한 계열이 글자를 다 담지 못하면 다른 계열로 넘어간다.
    """
    seen = []
    for fam in (family, "myeongjo" if family == "gothic" else "gothic"):
        hit = find_font(fam, truetype_only)
        if hit and hit not in seen:
            seen.append(hit)
    for path, index in seen:
        if not text or covers(path, index, text):
            return path, index
    return seen[0] if seen else None


def find_bold_for(family: str, text: str = "",
                  truetype_only: bool = False) -> Optional[Candidate]:
    """굵은 글꼴도 같은 방식으로 고른다. 없으면 None."""
    for fam in (family, "myeongjo" if family == "gothic" else "gothic"):
        hit = find_bold(fam, truetype_only)
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
