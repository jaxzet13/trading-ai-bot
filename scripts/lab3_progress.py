"""Turn a running `python -m kalshi15m lab3` log into data/lab/lab3_progress.json for the dashboard banner.
    python scripts/lab3_progress.py LOGFILE        (run every minute or so while the hunt runs)"""
import json, re, sys, time
from pathlib import Path

log = Path(sys.argv[1]).read_text(errors="ignore")
out = {"updated": int(time.time())}
m = re.search(r"(\d+) families, (\d+) configs per coin", log)
if m:
    out["families"], out["configs_per_coin"] = int(m.group(1)), int(m.group(2))
s = re.findall(r"search (\d+)/(\d+)", log)
if s:
    a, b = map(int, s[-1])
    out["pct"] = round(100 * a / b, 1)
else:
    out["pct"] = 0.0
out["done"] = bool(re.search(r"holdout|finals|final exam|wrote", log.split("search " + "/".join(s[-1]) if s else "")[-1], re.I)) if s and s[-1][0] == s[-1][1] else False
dst = Path(__file__).resolve().parent.parent / "data" / "lab" / "lab3_progress.json"
dst.write_text(json.dumps(out))
print(out)
