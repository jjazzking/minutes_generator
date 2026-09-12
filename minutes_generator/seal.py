# -*- coding: utf-8 -*-
"""인영(도장) 이미지를 그린다.

외부 이미지 자산 없이 Pillow 로 직접 그린다. 성명 텍스트 위에 겹쳐 찍히므로
OCR 모델이 인영에 가려진 글자를 읽어 내는지 확인하는 데 쓴다.
"""

import random
from typing import List, Optional, Tuple

from . import fonts

# 붉은 인주 색 계열
INK_COLORS = [
    (176, 32, 28), (193, 39, 45), (164, 26, 33), (186, 48, 40), (155, 34, 38),
]

HANJA_BY_TITLE = {
    "대표이사": "代表理事",
    "각자대표이사": "代表理事",
    "이사": "理事",
    "감사": "監事",
    "상근감사": "監事",
}


class SealUnavailable(RuntimeError):
    """Pillow 또는 글꼴이 없어 인영을 그릴 수 없을 때."""


def _require_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise SealUnavailable("인영 출력에는 Pillow 가 필요합니다.  pip install pillow") from exc


def _load_font(size: int, text: str = ""):
    """text 의 글자를 모두 담은 글꼴을 골라 연다. 명조 계열을 먼저 본다."""
    from PIL import ImageFont

    hit = fonts.find_font_for("myeongjo", text)
    if not hit:
        raise SealUnavailable("인영에 쓸 한글 글꼴을 찾지 못했습니다.")
    path, index = hit
    try:
        return ImageFont.truetype(path, size, index=index)
    except TypeError:
        return ImageFont.truetype(path, size)


def _grid(chars: List[str]) -> Tuple[int, int]:
    """글자 수에 따른 (열, 행). 전통 도장처럼 오른쪽 열부터 위에서 아래로 읽는다."""
    n = len(chars)
    if n <= 1:
        return 1, 1
    if n == 2:
        return 1, 2
    if n == 3:
        return 1, 3
    if n == 4:
        return 2, 2
    if n <= 6:
        return 2, 3
    return 3, 3


def hanja_available() -> bool:
    """설치된 글꼴이 인영에 쓰는 한자를 담고 있는지."""
    return fonts.supports("代表理事之印監")


def seal_text(name: str, title: str, rng: random.Random,
              hanja: Optional[bool] = None) -> Tuple[str, str]:
    """(도장에 새길 글자, 종류)를 고른다.

    글꼴에 한자가 없으면 한글 인영으로 대체하므로 네모가 찍히지 않는다.
    """
    if hanja is None:
        hanja = hanja_available()
    mark = "印" if hanja else "인"
    roll = rng.random()
    # 직인은 대표이사가 주로 쓰고, 일반 이사는 개인 인장을 쓴다.
    official_chance = {"대표이사": 0.42, "각자대표이사": 0.42,
                       "감사": 0.16, "상근감사": 0.16}.get(title, 0.04)
    if title in HANJA_BY_TITLE and roll < official_chance:
        if hanja:
            return HANJA_BY_TITLE[title] + "之印", "직인"
        return {"대표이사": "대표이사인", "각자대표이사": "대표이사인",
                "이사": "이사의인", "감사": "감사의인",
                "상근감사": "감사의인"}[title], "직인"
    if roll < 0.75:
        return name + mark, "성명인"
    if roll < 0.9:
        return name, "성명인"
    return name + ("之印" if hanja else "의인"), "성명인"


def make_seal(text: str,
              rng: random.Random,
              size: int = 240,
              shape: Optional[str] = None,
              color: Optional[Tuple[int, int, int]] = None):
    """RGBA 인영 이미지를 돌려준다. 배경은 투명하다."""
    _require_pillow()
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    shape = shape or rng.choices(["circle", "square", "rounded"], weights=[58, 28, 14])[0]
    color = color or rng.choice(INK_COLORS)
    chars = list(text)
    cols, rows = _grid(chars)

    canvas = Image.new("L", (size, size), 0)           # 잉크가 묻은 곳만 밝게
    draw = ImageDraw.Draw(canvas)
    margin = int(size * rng.uniform(0.05, 0.09))
    border = max(3, int(size * rng.uniform(0.035, 0.055)))
    box = [margin, margin, size - margin, size - margin]

    if shape == "circle":
        draw.ellipse(box, outline=255, width=border)
    elif shape == "rounded":
        draw.rounded_rectangle(box, radius=int(size * 0.12), outline=255, width=border)
    else:
        draw.rectangle(box, outline=255, width=border)

    inner = margin + border + int(size * 0.05)
    field = size - 2 * inner
    cell_w, cell_h = field / cols, field / rows
    glyph = int(min(cell_w, cell_h) * rng.uniform(0.86, 1.0))
    font = _load_font(max(8, glyph), text)

    for idx, ch in enumerate(chars):
        col = idx // rows                     # 오른쪽 열부터 채운다
        row = idx % rows
        cx = inner + field - (col + 0.5) * cell_w
        cy = inner + (row + 0.5) * cell_h
        draw.text((cx, cy), ch, font=font, fill=255, anchor="mm")

    # 인주가 고르게 묻지 않은 느낌: 노이즈로 알파를 깎는다.
    from .imaging import noise_layer

    grain = noise_layer((size, size), rng.uniform(26, 48), rng)
    grain = grain.filter(ImageFilter.GaussianBlur(rng.uniform(0.6, 1.6)))
    cut = rng.randint(96, 122)
    grain = grain.point([255 if v > cut else rng.randint(90, 175) for v in range(256)])
    alpha = ImageChops.multiply(canvas, grain)
    alpha = alpha.filter(ImageFilter.GaussianBlur(rng.uniform(0.2, 0.7)))

    seal = Image.new("RGBA", (size, size), color + (0,))
    seal.putalpha(alpha)

    angle = rng.uniform(-14, 14)
    seal = seal.rotate(angle, resample=Image.BICUBIC, expand=True)
    return seal


def seal_png(text: str, rng: random.Random, size: int = 240) -> bytes:
    """PNG 바이트. HTML 에 data URI 로 심을 때 쓴다."""
    import io

    buf = io.BytesIO()
    make_seal(text, rng, size=size).save(buf, format="PNG")
    return buf.getvalue()


def make_stamp(text: str, rng: random.Random, width: int = 520, height: int = 160):
    """'원본대조필' 같은 사각 스탬프. 본문 위에 비스듬히 찍는다."""
    _require_pillow()
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    color = rng.choice(INK_COLORS)
    canvas = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(canvas)
    border = max(3, int(height * 0.06))
    draw.rectangle([border, border, width - border, height - border],
                   outline=255, width=border)
    font = _load_font(int(height * 0.44), text)
    draw.text((width / 2, height / 2), text, font=font, fill=255, anchor="mm")

    from .imaging import noise_layer

    grain = noise_layer((width, height), rng.uniform(22, 40), rng)
    grain = grain.point([255 if v > 105 else rng.randint(70, 160) for v in range(256)])
    alpha = ImageChops.multiply(canvas, grain).filter(ImageFilter.GaussianBlur(0.5))

    stamp = Image.new("RGBA", (width, height), color + (0,))
    stamp.putalpha(alpha)
    return stamp.rotate(rng.uniform(-18, 18), resample=Image.BICUBIC, expand=True)
