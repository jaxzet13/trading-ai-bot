"""CLI:  python -m kalshi15m {download|backtest|serve|bot} ..."""
import argparse
import functools
import http.server
import json

from . import bot, data, report


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("real", "real-report"):   # own argument parsers
        from . import real
        raise SystemExit(real.main(sys.argv[2:]) if sys.argv[1] == "real" else real.report(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "record-pyth":              # own argument parsing (--once, --minutes N)
        from . import record_pyth
        raise SystemExit(record_pyth.main(sys.argv[2:]))
    ap = argparse.ArgumentParser(prog="kalshi15m")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="fetch historical Kalshi + spot data")
    d.add_argument("--series", nargs="+", default=list(data.SERIES))
    d.add_argument("--days", type=int, default=45)
    d.add_argument("--force", action="store_true")
    d.add_argument("--no-history", action="store_true", help="skip Kalshi's archive (before ~2 months ago)")
    d.add_argument("--since", default="2026-04-01", help="earliest archive date to fetch")
    d.add_argument("--every", type=int, default=2, help="fetch every Nth archive market")
    b = sub.add_parser("backtest", help="run sweeps and build the dashboard")
    b.add_argument("--series", nargs="+", default=list(data.SERIES))
    b.add_argument("--stake", type=float, default=10.0)
    b.add_argument("--folds", type=int, default=6)
    b.add_argument("--out", default=None, help="output folder (default: dashboard/)")
    b.add_argument("--solo", nargs="*", default=[], help="also show these coins on their own, e.g. KXSOL15M")
    s = sub.add_parser("serve", help="open the dashboard at http://localhost:8050")
    s.add_argument("--port", type=int, default=8050)
    lb = sub.add_parser("lab", help="search every strategy x coin x order type, judge on a locked holdout")
    lb.add_argument("--series", nargs="+", default=None)
    lb.add_argument("--workers", type=int, default=4)
    l2 = sub.add_parser("lab2", help="blind archive / fresh tests of the frozen fair_value rule + variants")
    l2.add_argument("args", nargs="*", help="download-archive [SERIES:EVERY ...] | download-fresh [SERIES ...] | probe | run")
    l3 = sub.add_parser("lab3", help="new strategy families vs the live ones on the locked holdout (+ archive)")
    l3.add_argument("--workers", type=int, default=2, help="worker processes (capped at 2: the bots share the machine)")
    l3.add_argument("--families", nargs="+", default=None, help="only these family ids (default: all)")
    l3.add_argument("--quick", type=int, default=0, help="pipeline test: only every Nth config of each grid")
    l3.add_argument("--out", default=None, help="output file (default data/lab/lab3_results.json)")
    l3.add_argument("--diagnose", action="store_true", help="only re-run the diagnostics on an existing results file")
    l4 = sub.add_parser("lab4", help="golden hunt on FX / yields / indices / commodities + cross-market (see lab4.py)")
    l4.add_argument("args", nargs="*", help="survey | download [SERIES ...] | models [QUICK] | xmkt | range | judge")
    l5 = sub.add_parser("lab5", help="execution variants (sizing/exits/re-entry/maker legs) of the best lab3 rules (see lab5.py)")
    l5.add_argument("args", nargs="*", help="download | run [WORKERS]")
    l4p = sub.add_parser("lab4p", help="lab4 re-run with Pyth (Kalshi's settlement source) as the price anchor (see lab4p.py)")
    l4p.add_argument("args", nargs="*", help="probe | validate | models [WORKERS] | judge | hermes")
    rp = sub.add_parser("record-pyth", help="forward recorder: Pyth prices + Kalshi bid/ask of open non-crypto 15-min markets, every minute",
                        add_help=False)
    rp.add_argument("args", nargs=argparse.REMAINDER, help="[--once] [--minutes N]")
    sub.add_parser("live-report", help="refresh the dashboard with the live paper-trading log")
    rl = sub.add_parser("real", help="REAL-MONEY runner for KXNEAR15M fair_value (see REAL_MONEY.md); --demo by default",
                        add_help=False)
    rl.add_argument("args", nargs=argparse.REMAINDER, help="[check] [--demo|--live] [--dry-run] [--minutes N]")
    rr = sub.add_parser("real-report", help="P&L of the real-money runner from its log (+ Kalshi settlements)",
                        add_help=False)
    rr.add_argument("args", nargs=argparse.REMAINDER, help="[--demo|--live] to cross-check with Kalshi")
    hr = sub.add_parser("hourly", help="hourly crypto markets: download, walk-forward search, locked holdout")
    hr.add_argument("--series", nargs="+", default=None)
    hr.add_argument("--days", type=int, default=45)
    hr.add_argument("--workers", type=int, default=4)
    hr.add_argument("--skip-download", action="store_true")
    t = sub.add_parser("bot", help="run the trading loop (paper by default)")
    t.add_argument("--series", nargs="+", default=["KXSOL15M"], help="one or more coins; each runs in its own thread")
    t.add_argument("--strategy", default="auto",
                   help="a strategy name, or 'auto' = each coin's latest pick from the backtest")
    t.add_argument("--params", default=None, help='JSON, e.g. \'{"edge":0.1}\'; default = best from backtest')
    t.add_argument("--stake", type=float, default=5.0)
    t.add_argument("--max-daily-loss", type=float, default=50.0)
    t.add_argument("--execution", choices=["taker", "maker"], default="taker",
                   help="taker = cross the spread now; maker = rest a limit order at the bid")
    t.add_argument("--wait", type=int, default=2, help="maker: minutes to leave the order resting")
    t.add_argument("--config", default=None, help="JSON file listing {series, strategy, execution, params}; overrides the rest")
    t.add_argument("--live", action="store_true", help="send REAL orders (needs API key env vars)")
    t.add_argument("--demo", action="store_true", help="use Kalshi's demo exchange")
    a = ap.parse_args()

    if a.cmd == "download":
        data.download(a.series, a.days, a.force, not a.no_history, a.since, a.every)
    elif a.cmd == "backtest":
        report.build(a.series, a.stake, a.folds, a.out, a.solo)
    elif a.cmd == "serve":
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(report.OUT))
        print(f"dashboard: http://localhost:{a.port}")
        http.server.ThreadingHTTPServer(("", a.port), h).serve_forever()
    elif a.cmd == "lab":
        from . import lab
        lab.main(a.series, a.workers)
    elif a.cmd == "lab2":
        from . import lab2
        lab2.main(a.args)
    elif a.cmd == "lab3":
        from . import lab3
        lab3.diagnose_file(a.out) if a.diagnose else lab3.main(a.workers, a.families, a.quick, a.out)
    elif a.cmd == "lab4":
        from . import lab4
        lab4.main(a.args)
    elif a.cmd == "lab5":
        from . import lab5
        lab5.main(a.args)
    elif a.cmd == "lab4p":
        from . import lab4p
        lab4p.main(a.args)
    elif a.cmd == "record-pyth":
        from . import record_pyth
        raise SystemExit(record_pyth.main(a.args))
    elif a.cmd == "hourly":
        from . import hourly
        hourly.main(a.series, a.workers, a.days, a.skip_download)
    elif a.cmd == "real":
        from . import real
        raise SystemExit(real.main(a.args))
    elif a.cmd == "real-report":
        from . import real
        raise SystemExit(real.report(a.args))
    elif a.cmd == "live-report":
        from . import live_report
        live_report.build()
    elif a.cmd == "bot":
        import threading
        try:
            res = json.loads((report.OUT / "results.json").read_text())
        except FileNotFoundError:
            res = {}
        jobs = []
        from .lab import _register_sessions
        _register_sessions()  # session-limited variants like fair_value@asia
        if a.config:
            cfg = json.loads(open(a.config).read())
            for e in cfg["strategies"]:
              pooled = isinstance(e["series"], list)
              for ser in (e["series"] if pooled else [e["series"]]):
                sid = f"{e.get('id', 'ALL')}|{ser}" if pooled else e.get("id")
                print(f"{sid or ser}: {e['strategy']} / {e['execution']} {e['params']}")
                jobs.append(threading.Thread(target=bot.run, daemon=True, kwargs=dict(
                    series=ser, strategy=e["strategy"], params=e["params"], stake=cfg.get("stake", a.stake),
                    live=a.live, demo=a.demo, max_daily_loss=cfg.get("max_daily_loss", a.max_daily_loss), max_trades_per_day=cfg.get("max_trades_per_day", 40),
                    execution=e["execution"], wait=e.get("wait", a.wait), poll=e.get("poll", 5), sid=sid,
                    sizing=e.get("sizing"), exit_rule=e.get("exit"), golden_rule=e.get("golden_rule"))))
        for series in ([] if a.config else a.series):
            strategy, execution = a.strategy, a.execution
            params = json.loads(a.params) if a.params else None
            if strategy == "auto":
                pick = ((res.get("portfolio") or {}).get("coins", {}).get(series) or {}).get("current")
                if not pick or not pick.get("strategy"):
                    print(f"{series}: no strategy cleared the bar in the backtest, sitting out")
                    continue
                strategy, execution, params = pick["strategy"], pick["execution"], pick["params"]
            elif params is None:
                scope = res.get("scopes", {}).get(series.replace("KX", "").replace("15M", "") + " only") \
                    or next(iter(res.get("scopes", {"": res}).values()), {})
                params = (((scope.get("strategies") or {}).get(strategy) or {}).get("runs", {})
                          .get(execution, {}).get("final_params", {}))
            print(f"{series}: {strategy} / {execution} {params}")
            jobs.append(threading.Thread(target=bot.run, daemon=True, kwargs=dict(
                series=series, strategy=strategy, params=params, stake=a.stake, live=a.live, demo=a.demo,
                max_daily_loss=a.max_daily_loss, execution=execution, wait=a.wait)))
        for j in jobs:
            j.start()
        try:
            for j in jobs:
                while j.is_alive():
                    j.join(1)
        except KeyboardInterrupt:
            print("stopped")

if __name__ == "__main__":
    main()
