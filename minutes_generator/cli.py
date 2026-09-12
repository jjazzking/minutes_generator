# -*- coding: utf-8 -*-
"""명령행 진입점."""

import argparse
import json
import os
import random
import sys

from . import __version__, sample
from .agenda import GENERATORS


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
    p.add_argument("-f", "--format", choices=["text", "json", "both"], default="both",
                   help="저장 형식 (기본 both)")
    p.add_argument("--agenda", default=None,
                   help="의안 종류를 쉼표로 지정한다. 예: borrowing,third_party_issue")
    p.add_argument("--n-agenda", type=int, default=None, help="의안 개수를 고정한다.")
    p.add_argument("--prefix", default="minutes", help="파일명 접두사 (기본 minutes)")
    p.add_argument("--list-kinds", action="store_true", help="지원하는 의안 종류를 출력한다.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_kinds:
        for k in sorted(GENERATORS):
            print(k)
        return 0

    kinds = None
    if args.agenda:
        kinds = [k.strip() for k in args.agenda.split(",") if k.strip()]
        unknown = [k for k in kinds if k not in GENERATORS]
        if unknown:
            print(f"알 수 없는 의안 종류: {', '.join(unknown)}", file=sys.stderr)
            print("--list-kinds 로 지원 목록을 확인하세요.", file=sys.stderr)
            return 2

    base = args.seed if args.seed is not None else random.randrange(1 << 30)

    if not args.out:
        text, gt = sample(base, agenda_kinds=kinds, n_agenda=args.n_agenda)
        if args.format in ("text", "both"):
            sys.stdout.write(text)
        if args.format in ("json", "both"):
            if args.format == "both":
                sys.stdout.write("\n")
            sys.stdout.write(json.dumps(gt, ensure_ascii=False, indent=2) + "\n")
        return 0

    os.makedirs(args.out, exist_ok=True)
    width = max(4, len(str(args.count)))
    for i in range(args.count):
        seed = base + i
        text, gt = sample(seed, agenda_kinds=kinds, n_agenda=args.n_agenda)
        stem = os.path.join(args.out, f"{args.prefix}_{i + 1:0{width}d}")
        if args.format in ("text", "both"):
            with open(stem + ".txt", "w", encoding="utf-8") as fh:
                fh.write(text)
        if args.format in ("json", "both"):
            with open(stem + ".json", "w", encoding="utf-8") as fh:
                json.dump(gt, fh, ensure_ascii=False, indent=2)
    print(f"{args.count}건 생성 완료 -> {args.out} (기준 시드 {base})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
