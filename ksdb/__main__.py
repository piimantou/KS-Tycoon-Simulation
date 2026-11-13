"""Umpire database CLI.

    python -m ksdb check   [GAME]        validate tables, list unfilled data
    python -m ksdb advance GAME [-n N]   resolve the next N ticks, append to the ledger
    python -m ksdb replay  GAME          recompute the whole ledger from setup
    python -m ksdb report  GAME          regenerate REPORT.md
    python -m ksdb new     NAME          scaffold an empty game
"""
from __future__ import annotations

import argparse
import sys

from . import engine, report, store


def _new(name: str, start: str) -> None:
    path = store.DB / "games" / name
    if path.exists():
        sys.exit(f"{path} already exists")
    ref = store.load_ref()
    (path / "setup").mkdir(parents=True)
    (path / "game.toml").write_text(
        f'name = "{name}"\nstart = "{start}"\nseed = 1\npromotion_months = [5, 11]\n\n[params]\n')
    store.write_csv(path / "setup/population.csv", ["class", "stock"],
                    [{"class": c, "stock": 0} for c in ref.classes])
    store.write_csv(path / "setup/buildings.csv", ["building", "owner", "size", *ref.capital, "note"], [])
    store.write_csv(path / "exogenous/population.csv", ["tick", "until", "class", "variable", "value", "note"], [])
    store.write_csv(path / "exogenous/buildings.csv",
                    ["tick", "building", "owner", "variable", "value", "source", "note"], [])
    store.write_csv(path / "exogenous/goods.csv", ["tick", "until", "scope", "variable", "value", "note"], [])
    print(f"created {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ksdb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("game", nargs="?")
    a = sub.add_parser("advance")
    a.add_argument("game")
    a.add_argument("-n", type=int, default=1)
    sub.add_parser("replay").add_argument("game")
    sub.add_parser("report").add_argument("game")
    n = sub.add_parser("new")
    n.add_argument("game")
    n.add_argument("--start", default="1920-01")
    args = ap.parse_args(argv)

    if args.cmd == "new":
        _new(args.game, args.start)
        return 0
    ref = store.load_ref()
    game = store.load_game(args.game, ref) if args.game else None
    errors, gaps = store.check(ref, game)
    for e in errors:
        print(f"ERROR  {e}")
    if args.cmd == "check":
        for g in gaps:
            print(f"gap    {g}")
        print(f"{len(errors)} error(s), {len(gaps)} gap(s)")
        return 1 if errors else 0
    if errors:
        return 1
    if args.cmd in ("advance", "replay"):
        done = engine.advance(ref, game, getattr(args, "n", 1), replay=args.cmd == "replay")
        print(f"resolved {done[0]} .. {done[-1]}" if len(done) > 1 else f"resolved {done[0]}")
        for w in engine.read_ledger(game, "warnings"):
            if w["tick"] in done:
                print(f"warn   {w['tick']}  {w['message']}")
    (game.path / "REPORT.md").write_text(report.build(ref, game), encoding="utf-8")
    print(f"wrote {game.path / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
