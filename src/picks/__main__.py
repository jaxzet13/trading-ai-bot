"""CLI: python -m src.picks [--props] [--today] [--top N] [--json]"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from .odds import OddsAPI, OddsAPIError
from .parlays import build_parlays
from .scanner import only_today, scan_all


def _fmt_american(n: int) -> str:
    return f"{n:+d}"


def _print_singles(picks, top: int) -> None:
    print(f"\n=== Top {min(top, len(picks))} Singles ===")
    if not picks:
        print("  (nothing cleared the edge threshold)")
        return
    header = f"{'#':>2}  {'Edge':>6}  {'Price':>7}  {'Fair%':>6}  {'Books':>5}  {'Kelly':>6}  {'Sport':<22}  Selection"
    print(header)
    print("-" * len(header))
    for i, p in enumerate(picks[:top], 1):
        print(
            f"{i:>2}  {p.edge*100:>5.2f}%  {_fmt_american(p.best_price):>7}  "
            f"{p.fair_prob*100:>5.1f}%  {p.books_count:>5}  {p.kelly_frac*100:>5.2f}%  "
            f"{p.sport:<22}  {p.selection} ({p.market}) [{p.best_book}] — {p.event}"
        )


def _print_parlays(parlays) -> None:
    print(f"\n=== Top {len(parlays)} Parlays ===")
    if not parlays:
        print("  (no uncorrelated +EV parlays found)")
        return
    for i, par in enumerate(parlays, 1):
        print(
            f"{i}. {_fmt_american(par.combined_american)}  "
            f"edge={par.edge*100:.2f}%  fair={par.fair_prob*100:.2f}%"
        )
        for leg in par.legs:
            print(f"     - {leg.selection} ({leg.market}) {_fmt_american(leg.best_price)} "
                  f"[{leg.best_book}] — {leg.event}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m src.picks",
        description="Scan every sport, line-shop across books, and rank top +EV picks.",
    )
    ap.add_argument("--props", action="store_true", help="Include player props (uses more API quota).")
    ap.add_argument("--today", action="store_true", help="Only include games starting today (UTC).")
    ap.add_argument("--top", type=int, default=15, help="How many singles to show.")
    ap.add_argument("--min-edge", type=float, default=0.01, help="Minimum edge (0.01 = 1%%).")
    ap.add_argument("--min-books", type=int, default=3, help="Min books quoting the market.")
    ap.add_argument("--sports", nargs="*", help="Restrict to specific sport keys (e.g. basketball_nba).")
    ap.add_argument("--no-parlays", action="store_true")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        api = OddsAPI()
    except OddsAPIError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    picks = scan_all(
        api,
        include_props=args.props,
        min_books=args.min_books,
        min_edge=args.min_edge,
        sports_filter=args.sports,
    )
    if args.today:
        picks = only_today(picks)

    parlays = [] if args.no_parlays else build_parlays(picks)

    if args.json:
        payload = {
            "singles": [asdict(p) for p in picks[:args.top]],
            "parlays": [
                {
                    "combined_american": par.combined_american,
                    "combined_decimal": round(par.combined_decimal, 4),
                    "fair_prob": par.fair_prob,
                    "edge": par.edge,
                    "legs": [asdict(l) for l in par.legs],
                }
                for par in parlays
            ],
        }
        json.dump(payload, sys.stdout, indent=2, default=str)
        print()
        return 0

    _print_singles(picks, args.top)
    if not args.no_parlays:
        _print_parlays(parlays)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
