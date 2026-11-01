"""CLI:  python -m kalshi15m {download|backtest|serve|bot} ..."""
import argparse
import functools
import http.server
import json

from . import bot, data, report


def main():
    ap = argparse.ArgumentParser(prog="kalshi15m")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="fetch historical Kalshi + spot data")
    d.add_argument("--series", nargs="+", default=list(data.SERIES))
    d.add_argument("--days", type=int, default=45)
    d.add_argument("--force", action="store_true")
    b = sub.add_parser("backtest", help="run sweeps and build the dashboard")
    b.add_argument("--series", nargs="+", default=list(data.SERIES))
    b.add_argument("--stake", type=float, default=10.0)
    s = sub.add_parser("serve", help="open the dashboard at http://localhost:8050")
    s.add_argument("--port", type=int, default=8050)
    t = sub.add_parser("bot", help="run the trading loop (paper by default)")
    t.add_argument("--series", default="KXBTC15M")
    t.add_argument("--strategy", default="fair_value")
    t.add_argument("--params", default=None, help='JSON, e.g. \'{"edge":0.1}\'; default = best from backtest')
    t.add_argument("--stake", type=float, default=5.0)
    t.add_argument("--max-daily-loss", type=float, default=50.0)
    t.add_argument("--live", action="store_true", help="send REAL orders (needs API key env vars)")
    t.add_argument("--demo", action="store_true", help="use Kalshi's demo exchange")
    a = ap.parse_args()

    if a.cmd == "download":
        data.download(a.series, a.days, a.force)
    elif a.cmd == "backtest":
        report.build(a.series, a.stake)
    elif a.cmd == "serve":
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(report.OUT))
        print(f"dashboard: http://localhost:{a.port}")
        http.server.ThreadingHTTPServer(("", a.port), h).serve_forever()
    elif a.cmd == "bot":
        params = json.loads(a.params) if a.params else None
        if params is None:
            try:
                r = json.loads((report.OUT / "results.json").read_text())
                params = r["series"][a.series]["strategies"][a.strategy]["best_params"]
                print("using backtest-best params:", params)
            except Exception:
                params = {}
        bot.run(a.series, a.strategy, params, a.stake, a.live, a.demo, a.max_daily_loss)


if __name__ == "__main__":
    main()
