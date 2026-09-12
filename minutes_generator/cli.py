# -*- coding: utf-8 -*-
"""명령행 진입점."""

import argparse
import json
import os
import random
import sys

from . import __version__, sample
from .agenda import GENERATORS

FORMATS = ["text", "json", "pdf", "html", "both", "all"]


def _expand(fmt: str):
    if fmt == "both":
        return {"text", "json"}
    if fmt == "all":
        return {"text", "json", "pdf", "html"}
    return {fmt}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="minutes_generator",
        description="모의 이사회 의사록을 무작위로 생성한다.",
    )
    p.add_argument("-n", "--count", type=int, default=1, help="생성할 문서 수 (기본 1)")
    p.add_argument("-s", "--seed", type=int, default=None,
                   help="기준 시드. 지정하면 결과가 재현된다.")
    p.add_argument("-o", "--out", default=None,
                   help="출력 디렉터리. 생략하면 표준출력으로 한 건만 출력한다.")
    p.add_argument("-f", "--format", choices=FORMATS, default="both",
                   help="저장 형식 (기본 both = text + json, all = 전부)")
    p.add_argument("--agenda", default=None,
                   help="의안 종류를 쉼표로 지정한다. 예: borrowing,third_party_issue")
    p.add_argument("--n-agenda", type=int, default=None, help="의안 개수를 고정한다.")
    p.add_argument("--prefix", default="minutes", help="파일명 접두사 (기본 minutes)")
    p.add_argument("--list-kinds", action="store_true", help="지원하는 의안 종류를 출력한다.")
    p.add_argument("--scan", default=None,
                   help="스캔 열화본을 함께 만든다. 프로파일 이름 또는 random.")
    p.add_argument("--scan-dpi", type=int, default=None, help="스캔본 해상도를 고정한다.")
    p.add_argument("--scan-format", choices=["pdf", "png", "jpg"], default="pdf",
                   help="스캔본 저장 형식 (기본 pdf)")
    p.add_argument("--list-scan-profiles", action="store_true",
                   help="스캔 열화 프로파일 목록을 출력한다.")
    p.add_argument("--check-fonts", action="store_true",
                   help="PDF 출력에 쓸 한글 글꼴을 찾을 수 있는지 확인한다.")
    p.add_argument("--ui", action="store_true", help="브라우저 UI를 연다.")
    p.add_argument("--port", type=int, default=8765, help="--ui 의 포트 (기본 8765)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_kinds:
        for k in sorted(GENERATORS):
            print(k)
        return 0

    if args.list_scan_profiles:
        from .scan import PROFILE_LABELS, PROFILES
        for key in list(PROFILES) + ["random"]:
            print(f"{key:14s} {PROFILE_LABELS.get(key, '')}")
        return 0

    if args.check_fonts:
        from . import fonts
        print(fonts.describe())
        try:
            import reportlab
            print(f"reportlab : {reportlab.Version}")
        except ImportError:
            print("reportlab : 없음 (pip install reportlab)")
        for module, why in (("PIL", "인영 이미지"), ("pypdfium2", "스캔 열화본")):
            try:
                __import__(module)
                print(f"{module:10s}: 있음 ({why})")
            except ImportError:
                pkg = "pillow" if module == "PIL" else module
                print(f"{module:10s}: 없음 ({why}) -> pip install {pkg}")
        return 0

    if args.ui:
        from .ui import serve
        return serve(port=args.port)

    kinds = None
    if args.agenda:
        kinds = [k.strip() for k in args.agenda.split(",") if k.strip()]
        unknown = [k for k in kinds if k not in GENERATORS]
        if unknown:
            print(f"알 수 없는 의안 종류: {', '.join(unknown)}", file=sys.stderr)
            print("--list-kinds 로 지원 목록을 확인하세요.", file=sys.stderr)
            return 2

    wanted = _expand(args.format)
    if args.scan:
        from .scan import PROFILES
        if args.scan != "random" and args.scan not in PROFILES:
            print(f"알 수 없는 스캔 프로파일: {args.scan}", file=sys.stderr)
            print("--list-scan-profiles 로 목록을 확인하세요.", file=sys.stderr)
            return 2
    base = args.seed if args.seed is not None else random.randrange(1 << 30)

    if not args.out:
        if wanted & {"pdf"} or args.scan:
            print("PDF 와 스캔본은 --out 디렉터리가 필요합니다.", file=sys.stderr)
            return 2
        text, gt = sample(base, agenda_kinds=kinds, n_agenda=args.n_agenda)
        if "text" in wanted:
            sys.stdout.write(text)
        if "html" in wanted:
            from .generator import build_minutes
            from .html_render import render_html
            sys.stdout.write(render_html(
                build_minutes(base, agenda_kinds=kinds, n_agenda=args.n_agenda), base))
        if "json" in wanted:
            if len(wanted) > 1:
                sys.stdout.write("\n")
            sys.stdout.write(json.dumps(gt, ensure_ascii=False, indent=2) + "\n")
        return 0

    os.makedirs(args.out, exist_ok=True)
    width = max(4, len(str(args.count)))
    pdf_error = None
    for i in range(args.count):
        seed = base + i
        text, gt = sample(seed, agenda_kinds=kinds, n_agenda=args.n_agenda)
        stem = os.path.join(args.out, f"{args.prefix}_{i + 1:0{width}d}")
        if "text" in wanted:
            with open(stem + ".txt", "w", encoding="utf-8") as fh:
                fh.write(text)
        if args.scan and pdf_error is None:
            try:
                gt["scan"] = _write_scan(seed, kinds, args, stem)
            except Exception as exc:       # noqa: BLE001
                pdf_error = str(exc)
        if "json" in wanted:
            with open(stem + ".json", "w", encoding="utf-8") as fh:
                json.dump(gt, fh, ensure_ascii=False, indent=2)
        if wanted & {"pdf", "html"}:
            from .generator import build_minutes
            minutes = build_minutes(seed, agenda_kinds=kinds, n_agenda=args.n_agenda)
            if "html" in wanted:
                from .html_render import render_html
                with open(stem + ".html", "w", encoding="utf-8") as fh:
                    fh.write(render_html(minutes, seed))
            if "pdf" in wanted and pdf_error is None:
                try:
                    from .pdf import render_pdf
                    render_pdf(minutes, stem + ".pdf", seed)
                except Exception as exc:       # noqa: BLE001
                    pdf_error = str(exc)

    print(f"{args.count}건 생성 완료 -> {args.out} (기준 시드 {base})")
    if pdf_error:
        print(f"PDF 또는 스캔본 출력 실패: {pdf_error}", file=sys.stderr)
        return 1
    return 0


def _write_scan(seed, kinds, args, stem):
    """스캔 열화본을 저장하고 적용한 값을 돌려준다."""
    import random as _random

    from .generator import build_minutes
    from .pdf import pdf_bytes
    from .scan import images_to_pdf, scan

    minutes = build_minutes(seed, agenda_kinds=kinds, n_agenda=args.n_agenda)
    pages, params = scan(pdf_bytes(minutes, seed), args.scan,
                         _random.Random(seed ^ 0x5CA4), args.scan_dpi)
    if args.scan_format == "pdf":
        images_to_pdf(pages, stem + "_scan.pdf")
    else:
        ext = "jpg" if args.scan_format == "jpg" else "png"
        for i, page in enumerate(pages, start=1):
            page.save(f"{stem}_scan_p{i}.{ext}")
    params["pages"] = len(pages)
    return params


if __name__ == "__main__":
    raise SystemExit(main())
