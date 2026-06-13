"""Command-line driver for the engine (a stand-in until the web UI lands).

    python -m kstycoon.cli new   state.json          # write the SK 1924 scenario
    python -m kstycoon.cli tick  state.json [-o next.json]   # resolve one FY
    python -m kstycoon.cli report state.json          # tick and print the handoff

The CLI is intentionally thin: all logic lives in the engine.
"""

from __future__ import annotations

import argparse
import sys

from . import report as report_mod
from . import serialize
from .resolve import tick
from .scenarios import south_korea_y0


def _cmd_new(args: argparse.Namespace) -> int:
    serialize.save(south_korea_y0.build(), args.path)
    print(f"wrote South Korea 1924 scenario -> {args.path}")
    return 0


def _cmd_tick(args: argparse.Namespace) -> int:
    state = serialize.load(args.path)
    res = tick(state)
    out = args.out or args.path
    serialize.save(res.state, out)
    print(report_mod.render(res))
    print(f"\n(next state -> {out})", file=sys.stderr)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    state = serialize.load(args.path)
    res = tick(state)
    print(report_mod.render(res))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kstycoon")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="write the South Korea 1924 scenario")
    p_new.add_argument("path")
    p_new.set_defaults(func=_cmd_new)

    p_tick = sub.add_parser("tick", help="resolve one financial year")
    p_tick.add_argument("path")
    p_tick.add_argument("-o", "--out", help="path for the resulting state")
    p_tick.set_defaults(func=_cmd_tick)

    p_report = sub.add_parser("report", help="resolve and print the handoff report")
    p_report.add_argument("path")
    p_report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
