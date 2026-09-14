"""한글 PDF 출력을 위한 ReportLab 폰트 등록 헬퍼.

ReportLab의 ``TTFont``은 TrueType 아웃라인(``glyf`` 테이블)만 읽는다.
macOS 기본 한글 폰트인 ``AppleSDGothicNeo.ttc`` 처럼 PostScript/CFF 아웃라인을
쓰는 OpenType 폰트를 넘기면 다음과 같이 실패한다::

    TTFError: TTC file "/System/Library/Fonts/AppleSDGothicNeo.ttc":
              postscript outlines are not supported

이 모듈은 후보 폰트를 순서대로 시도하면서 그런 폰트를 만나면 조용히 건너뛰고,
쓸 수 있는 TrueType 한글 폰트가 하나도 없으면 ReportLab 내장 CID 폰트로
폴백한다. CID 폰트는 글꼴을 PDF에 임베드하지 않고 뷰어의 한글 폰트에
의존하므로, 임베드가 필요하면 ``fonts/`` 디렉터리에 TTF를 동봉할 것.

사용법::

    from fonts import register_korean_font

    font_name = register_korean_font()
    style = ParagraphStyle("KR", fontName=font_name, fontSize=11, leading=16)

굵은 글씨까지 쓰려면::

    regular, bold = register_korean_font_family()
"""

from __future__ import annotations

import logging
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFError, TTFont

logger = logging.getLogger(__name__)

#: 프로젝트에 동봉한 폰트를 두는 곳. 여기 있는 폰트가 항상 1순위다.
FONT_DIR = Path(__file__).resolve().parent / "fonts"

#: 내장 CID 폰트 이름. 폰트 파일을 하나도 못 찾았을 때 쓴다.
FALLBACK_CID_FONT = "HYSMyeongJo-Medium"
FALLBACK_CID_FONT_BOLD = "HYGothic-Medium"

#: ``(경로, subfontIndex)`` 후보 목록. 앞에 있는 것부터 시도한다.
#: ``.ttc`` 는 여러 폰트를 담고 있어 ``subfontIndex`` 로 고른다.
REGULAR_CANDIDATES: list[tuple[Path, int]] = [
    # 프로젝트 동봉 (플랫폼과 무관하게 동일한 결과를 내므로 1순위)
    (FONT_DIR / "NanumGothic.ttf", 0),
    (FONT_DIR / "NotoSansKR-Regular.ttf", 0),
    # macOS — AppleGothic 은 TrueType 이다.
    # (AppleSDGothicNeo.ttc 는 CFF 라서 일부러 넣지 않았다.)
    (Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"), 0),
    (Path("/Library/Fonts/AppleGothic.ttf"), 0),
    (Path("/Library/Fonts/NanumGothic.ttf"), 0),
    # Windows — 맑은 고딕
    (Path("C:/Windows/Fonts/malgun.ttf"), 0),
    (Path("C:/Windows/Fonts/gulim.ttc"), 0),
    # Linux
    (Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), 0),
    (Path("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"), 0),
    (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), 1),
]

BOLD_CANDIDATES: list[tuple[Path, int]] = [
    (FONT_DIR / "NanumGothicBold.ttf", 0),
    (FONT_DIR / "NotoSansKR-Bold.ttf", 0),
    (Path("/Library/Fonts/NanumGothicBold.ttf"), 0),
    (Path("C:/Windows/Fonts/malgunbd.ttf"), 0),
    (Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"), 0),
    (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"), 1),
]


def _try_register(name: str, candidates: list[tuple[Path, int]]) -> str | None:
    """후보를 차례로 등록해 보고 처음 성공한 이름을 돌려준다.

    CFF 아웃라인처럼 ReportLab 이 읽지 못하는 폰트는 ``TTFError`` 를 내므로
    잡아서 다음 후보로 넘어간다. 모두 실패하면 ``None``.
    """
    for path, subfont_index in candidates:
        if not path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=subfont_index))
        except (TTFError, OSError) as exc:
            # PostScript 아웃라인, 깨진 파일, 읽기 권한 없음 등
            logger.debug("폰트를 등록하지 못해 건너뜀: %s (%s)", path, exc)
            continue
        logger.info("한글 폰트 등록: %s -> %s", name, path)
        return name
    return None


def register_korean_font(name: str = "KoreanFont") -> str:
    """한글 본문용 폰트를 등록하고 ``fontName`` 으로 쓸 이름을 돌려준다.

    TrueType 후보를 전부 실패하면 내장 CID 폰트를 등록하고 그 이름을 돌려주므로,
    어떤 환경에서도 예외 없이 쓸 수 있는 이름이 나온다.
    """
    registered = _try_register(name, REGULAR_CANDIDATES)
    if registered is not None:
        return registered

    logger.warning(
        "쓸 수 있는 TrueType 한글 폰트를 찾지 못해 내장 CID 폰트(%s)로 폴백합니다. "
        "글꼴이 PDF에 임베드되지 않으니 %s 에 NanumGothic.ttf 를 넣어 주세요.",
        FALLBACK_CID_FONT,
        FONT_DIR,
    )
    pdfmetrics.registerFont(UnicodeCIDFont(FALLBACK_CID_FONT))
    return FALLBACK_CID_FONT


def register_korean_font_family(
    name: str = "KoreanFont",
    bold_name: str = "KoreanFont-Bold",
) -> tuple[str, str]:
    """본문용과 굵은 글씨용 폰트를 등록하고 ``(regular, bold)`` 이름을 돌려준다.

    굵은 폰트를 못 찾으면 본문 폰트 이름을 그대로 굵은 자리에 돌려주므로,
    ``<b>`` 태그가 있는 ``Paragraph`` 도 예외 없이 렌더링된다.
    """
    regular = register_korean_font(name)

    if regular == FALLBACK_CID_FONT:
        # CID 폴백 상태에서는 굵은 글씨도 CID 폰트로 맞춘다.
        pdfmetrics.registerFont(UnicodeCIDFont(FALLBACK_CID_FONT_BOLD))
        bold = FALLBACK_CID_FONT_BOLD
    else:
        bold = _try_register(bold_name, BOLD_CANDIDATES) or regular

    # Paragraph 안의 <b> 가 자동으로 bold 폰트를 쓰도록 매핑해 둔다.
    pdfmetrics.registerFontFamily(regular, normal=regular, bold=bold, italic=regular, boldItalic=bold)
    return regular, bold


if __name__ == "__main__":  # 수동 확인용
    logging.basicConfig(level=logging.INFO)
    print(register_korean_font_family())
