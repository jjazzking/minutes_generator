# -*- coding: utf-8 -*-
"""깨끗한 PDF 를 스캔본·촬영본처럼 열화시킨다.

PDF 를 이미지로 래스터화한 뒤 회전, 흐림, 잡음, 그림자, 얼룩, 접힘선 등을 입힌다.
적용한 값은 모두 돌려주므로 정답셋에 기록해 조건별 성능을 나눠 볼 수 있다.

필요한 것: Pillow, 그리고 래스터라이저로 pypdfium2 또는 PyMuPDF 중 하나.
"""

import io
import random
from typing import Any, Dict, List, Optional, Tuple

A4_RATIO = 297 / 210


class ScanUnavailable(RuntimeError):
    """Pillow 또는 PDF 래스터라이저가 없을 때."""


# ---------------------------------------------------------------- 래스터화

def _require_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise ScanUnavailable("Pillow 가 필요합니다.  pip install pillow") from exc


def rasterize(pdf_data: bytes, dpi: int = 300) -> List[Any]:
    """PDF 바이트를 페이지별 PIL 이미지로 바꾼다."""
    _require_pillow()
    try:
        import pypdfium2 as pdfium
    except ImportError:
        pass
    else:
        doc = pdfium.PdfDocument(pdf_data)
        try:
            return [doc[i].render(scale=dpi / 72).to_pil().convert("RGB")
                    for i in range(len(doc))]
        finally:
            doc.close()

    try:
        import fitz
    except ImportError as exc:
        raise ScanUnavailable(
            "PDF 를 이미지로 바꾸려면 pypdfium2 가 필요합니다.  pip install pypdfium2"
        ) from exc
    from PIL import Image

    doc = fitz.open(stream=pdf_data, filetype="pdf")
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    doc.close()
    return pages


# ---------------------------------------------------------------- 낱개 연산

def _solve(matrix: List[List[float]], rhs: List[float]) -> List[float]:
    """작은 연립방정식을 가우스 소거법으로 푼다. numpy 를 쓰지 않기 위한 것."""
    n = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("특이행렬")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        head = aug[col][col]
        aug[col] = [v / head for v in aug[col]]
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if factor:
                aug[r] = [v - factor * w for v, w in zip(aug[r], aug[col])]
    return [aug[i][n] for i in range(n)]


def _perspective(image, amount: float, rng: random.Random):
    """촬영본처럼 네 귀퉁이를 조금씩 어긋나게 한다."""
    from PIL import Image

    w, h = image.size
    jitter = lambda span: rng.uniform(-span, span)      # noqa: E731
    dx, dy = w * amount, h * amount
    target = [(jitter(dx), jitter(dy)), (w + jitter(dx), jitter(dy)),
              (w + jitter(dx), h + jitter(dy)), (jitter(dx), h + jitter(dy))]
    source = [(0, 0), (w, 0), (w, h), (0, h)]
    rows, rhs = [], []
    for (tx, ty), (sx, sy) in zip(target, source):
        rows.append([sx, sy, 1, 0, 0, 0, -tx * sx, -tx * sy])
        rhs.append(tx)
        rows.append([0, 0, 0, sx, sy, 1, -ty * sx, -ty * sy])
        rhs.append(ty)
    coeffs = _solve(rows, rhs)
    return image.transform((w, h), Image.PERSPECTIVE, coeffs,
                           resample=Image.BICUBIC, fillcolor=(255, 255, 255))


def _rotate(image, degrees: float):
    from PIL import Image

    return image.rotate(degrees, resample=Image.BICUBIC, expand=False,
                        fillcolor=(255, 255, 255))


def _blur(image, radius: float):
    from PIL import ImageFilter

    return image.filter(ImageFilter.GaussianBlur(radius))


def _noise(image, sigma: float, rng: random.Random):
    from PIL import ImageChops

    from .imaging import noise_layer

    layer = noise_layer(image.size, sigma, rng).convert("RGB")
    return ImageChops.add(image, layer, scale=1.0, offset=-128)


def _resample(image, factor: float):
    from PIL import Image

    w, h = image.size
    small = image.resize((max(1, int(w * factor)), max(1, int(h * factor))),
                         Image.BILINEAR)
    return small.resize((w, h), Image.BILINEAR)


def _shadow(image, strength: float, rng: random.Random):
    """스마트폰으로 찍을 때 생기는 한쪽 그늘."""
    from PIL import Image, ImageChops, ImageFilter

    w, h = image.size
    side = int(((w * w + h * h) ** 0.5) * 1.06) + 2
    gradient = Image.linear_gradient("L").resize((side, side), Image.BILINEAR)
    # 정사각형을 회전한 뒤 가운데를 잘라내야 모서리에 검은 삼각형이 남지 않는다.
    gradient = gradient.rotate(rng.uniform(0, 360), resample=Image.BILINEAR,
                               expand=False, fillcolor=128)
    left, top = (side - w) // 2, (side - h) // 2
    gradient = gradient.crop((left, top, left + w, top + h))
    gradient = gradient.point(lambda v: int(255 - v * strength))
    gradient = gradient.filter(ImageFilter.GaussianBlur(w * 0.05))
    return ImageChops.multiply(image, gradient.convert("RGB"))


def _vignette(image, strength: float):
    from PIL import Image, ImageChops

    mask = Image.radial_gradient("L").resize(image.size, Image.BILINEAR)
    mask = mask.point(lambda v: int(255 - v * strength))
    return ImageChops.multiply(image, mask.convert("RGB"))


def _speckle(image, count: int, rng: random.Random):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    w, h = image.size
    for _ in range(count):
        x, y = rng.randrange(w), rng.randrange(h)
        r = rng.randint(0, 2)
        tone = rng.randint(20, 110)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(tone, tone, tone))
    return image


def _blotches(image, count: int, rng: random.Random):
    """복사기 얼룩이나 종이 오염."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    layer = Image.new("L", image.size, 255)
    draw = ImageDraw.Draw(layer)
    w, h = image.size
    for _ in range(count):
        cx, cy = rng.randrange(w), rng.randrange(h)
        rx, ry = rng.randint(w // 40, w // 8), rng.randint(h // 60, h // 12)
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                     fill=rng.randint(216, 249))
    layer = layer.filter(ImageFilter.GaussianBlur(w * 0.006))
    return ImageChops.multiply(image, layer.convert("RGB"))


def _fold(image, rng: random.Random, count: int = 1):
    """접힌 자국."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    layer = Image.new("L", image.size, 255)
    draw = ImageDraw.Draw(layer)
    w, h = image.size
    for _ in range(count):
        if rng.random() < 0.6:
            y = rng.randint(int(h * 0.2), int(h * 0.8))
            draw.rectangle([0, y - 2, w, y + 2], fill=rng.randint(188, 226))
        else:
            x = rng.randint(int(w * 0.2), int(w * 0.8))
            draw.rectangle([x - 2, 0, x + 2, h], fill=rng.randint(188, 226))
    layer = layer.filter(ImageFilter.GaussianBlur(w * 0.004))
    return ImageChops.multiply(image, layer.convert("RGB"))


def _streaks(image, count: int, rng: random.Random):
    """팩스나 급지 불량으로 생기는 가로줄."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    w, h = image.size
    for _ in range(count):
        y = rng.randrange(h)
        thickness = rng.randint(1, 3)
        tone = rng.choice([rng.randint(30, 90), rng.randint(215, 255)])
        draw.rectangle([0, y, w, y + thickness], fill=(tone, tone, tone))
    return image


def _bleed_through(image, opacity: float):
    """뒷면 글씨가 비쳐 보이는 효과."""
    from PIL import Image, ImageChops, ImageFilter, ImageOps

    back = ImageOps.mirror(image).filter(ImageFilter.GaussianBlur(image.size[0] * 0.002))
    back = Image.blend(Image.new("RGB", image.size, (255, 255, 255)), back, opacity)
    return ImageChops.multiply(image, back)


def _paper_tint(image, tint: Tuple[int, int, int]):
    from PIL import Image, ImageChops

    return ImageChops.multiply(image, Image.new("RGB", image.size, tint))


def _bitonal(image, threshold: int):
    """복사기·팩스처럼 흑백 2치화."""
    gray = image.convert("L").point(lambda v: 255 if v > threshold else 0)
    return gray.convert("RGB")


def _enhance(image, contrast: float, brightness: float):
    from PIL import ImageEnhance

    if contrast and abs(contrast - 1.0) > 1e-3:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    if brightness and abs(brightness - 1.0) > 1e-3:
        image = ImageEnhance.Brightness(image).enhance(brightness)
    return image


def _jpeg(image, quality: int):
    from PIL import Image

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _scan_border(image, pad: int, tone: int):
    """스캐너 덮개가 닫히지 않아 생기는 검은 테두리."""
    from PIL import ImageOps

    return ImageOps.expand(image, border=pad, fill=(tone, tone, tone))


# ---------------------------------------------------------------- 프로파일

def _profile_clean(rng):
    return {"dpi": 300}


def _profile_office(rng):
    return {
        "dpi": 300,
        "rotate": rng.uniform(-0.8, 0.8),
        "blur": rng.uniform(0.3, 0.8),
        "noise": rng.uniform(3, 9),
        "contrast": rng.uniform(0.96, 1.12),
        "brightness": rng.uniform(0.95, 1.04),
        "speckle": rng.randint(0, 60),
    }


def _profile_low_dpi(rng):
    return {
        "dpi": rng.choice([120, 150, 150, 200]),
        "rotate": rng.uniform(-1.4, 1.4),
        "resample": rng.uniform(0.55, 0.8),
        "blur": rng.uniform(0.4, 1.0),
        "noise": rng.uniform(5, 13),
        "contrast": rng.uniform(0.92, 1.1),
        "speckle": rng.randint(0, 40),
    }


def _profile_mobile(rng):
    return {
        "dpi": rng.choice([150, 180, 200, 240]),
        "perspective": rng.uniform(0.004, 0.018),
        "rotate": rng.uniform(-3.5, 3.5),
        "shadow": rng.uniform(0.10, 0.30),
        "vignette": rng.uniform(0.06, 0.2),
        "blur": rng.uniform(0.4, 1.3),
        "noise": rng.uniform(4, 12),
        "contrast": rng.uniform(0.9, 1.15),
        "brightness": rng.uniform(0.96, 1.14),
        "jpeg": rng.randint(45, 82),
    }


def _profile_photocopy(rng):
    return {
        "dpi": rng.choice([150, 200, 200, 300]),
        "rotate": rng.uniform(-1.8, 1.8),
        "blotches": rng.randint(1, 5),
        "fold": rng.randint(0, 2),
        "blur": rng.uniform(0.3, 0.9),
        "contrast": rng.uniform(1.15, 1.7),
        "brightness": rng.uniform(0.85, 1.0),
        "noise": rng.uniform(4, 11),
        "speckle": rng.randint(40, 260),
        "border": rng.choice([0, 0, rng.randint(6, 26)]),
    }


def _profile_fax(rng):
    return {
        "dpi": rng.choice([100, 120, 150]),
        "rotate": rng.uniform(-1.2, 1.2),
        "resample": rng.uniform(0.5, 0.75),
        "blur": rng.uniform(0.3, 0.8),
        "contrast": rng.uniform(1.2, 1.8),
        "bitonal": rng.randint(112, 168),
        "speckle": rng.randint(120, 520),
        "streaks": rng.randint(1, 7),
    }


def _profile_aged(rng):
    return {
        "dpi": rng.choice([200, 240, 300]),
        "paper_tint": (rng.randint(238, 252), rng.randint(228, 244), rng.randint(206, 228)),
        "bleed": rng.uniform(0.02, 0.07),
        "blotches": rng.randint(2, 7),
        "fold": rng.randint(1, 3),
        "rotate": rng.uniform(-2.2, 2.2),
        "blur": rng.uniform(0.3, 0.9),
        "noise": rng.uniform(5, 12),
        "vignette": rng.uniform(0.08, 0.22),
        "speckle": rng.randint(60, 300),
        "jpeg": rng.choice([None, rng.randint(60, 88)]),
    }


PROFILES = {
    "clean": _profile_clean,
    "office_scan": _profile_office,
    "low_dpi": _profile_low_dpi,
    "mobile_photo": _profile_mobile,
    "photocopy": _profile_photocopy,
    "fax": _profile_fax,
    "aged": _profile_aged,
}

PROFILE_LABELS = {
    "clean": "깨끗한 원본",
    "office_scan": "사무실 스캔 (300dpi)",
    "low_dpi": "저해상도 스캔",
    "mobile_photo": "스마트폰 촬영",
    "photocopy": "복사기 사본",
    "fax": "팩스 · 흑백 2치화",
    "aged": "오래된 종이",
    "random": "무작위 (깨끗한 원본 제외)",
}

DEGRADED = [k for k in PROFILES if k != "clean"]


def sample_params(profile: str, rng: random.Random,
                  dpi: Optional[int] = None) -> Dict[str, Any]:
    """프로파일에 맞는 열화 값을 뽑는다."""
    if profile == "random":
        profile = rng.choice(DEGRADED)
    if profile not in PROFILES:
        raise ValueError(f"알 수 없는 프로파일: {profile}")
    params = PROFILES[profile](rng)
    params["profile"] = profile
    if dpi:
        params["dpi"] = dpi
    return params


def apply(image, params: Dict[str, Any], rng: random.Random):
    """뽑아 둔 값을 정해진 순서로 입힌다."""
    _require_pillow()
    out = image.convert("RGB")
    if params.get("paper_tint"):
        out = _paper_tint(out, tuple(params["paper_tint"]))
    if params.get("bleed"):
        out = _bleed_through(out, params["bleed"])
    if params.get("blotches"):
        out = _blotches(out, params["blotches"], rng)
    if params.get("fold"):
        out = _fold(out, rng, params["fold"])
    if params.get("shadow"):
        out = _shadow(out, params["shadow"], rng)
    if params.get("vignette"):
        out = _vignette(out, params["vignette"])
    if params.get("perspective"):
        out = _perspective(out, params["perspective"], rng)
    if params.get("rotate"):
        out = _rotate(out, params["rotate"])
    if params.get("resample"):
        out = _resample(out, params["resample"])
    if params.get("blur"):
        out = _blur(out, params["blur"])
    if params.get("noise"):
        out = _noise(out, params["noise"], rng)
    out = _enhance(out, params.get("contrast", 1.0), params.get("brightness", 1.0))
    if params.get("speckle"):
        out = _speckle(out, params["speckle"], rng)
    if params.get("streaks"):
        out = _streaks(out, params["streaks"], rng)
    if params.get("bitonal"):
        out = _bitonal(out, params["bitonal"])
    if params.get("border"):
        out = _scan_border(out, params["border"], rng.randint(0, 60))
    if params.get("jpeg"):
        out = _jpeg(out, params["jpeg"])
    return out


def scan(pdf_data: bytes, profile: str = "office_scan",
         rng: Optional[random.Random] = None,
         dpi: Optional[int] = None) -> Tuple[List[Any], Dict[str, Any]]:
    """(열화된 페이지 이미지 목록, 적용한 값)을 돌려준다."""
    rng = rng or random.Random()
    params = sample_params(profile, rng, dpi)
    pages = rasterize(pdf_data, params["dpi"])
    return [apply(page, params, rng) for page in pages], params


def images_to_pdf(images: List[Any], target) -> None:
    """열화된 이미지를 다시 한 개의 PDF 로 묶는다. 텍스트 층이 없는 스캔본이 된다."""
    if not images:
        raise ValueError("이미지가 없습니다.")
    head, rest = images[0], images[1:]
    head.convert("RGB").save(target, format="PDF", save_all=True,
                             append_images=[i.convert("RGB") for i in rest])
