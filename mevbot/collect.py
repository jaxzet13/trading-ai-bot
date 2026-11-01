"""Record every new Solana pool as it launches (unbiased sniper backtest sample).

GeckoTerminal's new_pools feed only covers the last few minutes, so we poll it
and append unseen pools, together with their stats at first sight, to a JSONL file.

    python -m mevbot.collect --minutes 90
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import gecko

OUT = Path(__file__).resolve().parent.parent / "data" / "mev" / "launches.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=90)
    ap.add_argument("--pages", type=int, default=3)
    args = ap.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if OUT.exists():
        seen = {json.loads(l)["address"] for l in OUT.read_text().splitlines() if l.strip()}
    end = time.time() + args.minutes * 60
    while time.time() < end:
        for page in range(1, args.pages + 1):
            try:
                pools = gecko.new_pools(page)
            except Exception as e:  # keep collecting through transient failures
                print("error", e, flush=True)
                continue
            now = datetime.now(timezone.utc).isoformat()
            fresh = 0
            with OUT.open("a") as f:
                for p in pools:
                    a = p["attributes"]
                    if a["address"] in seen:
                        continue
                    seen.add(a["address"])
                    fresh += 1
                    f.write(json.dumps({
                        "address": a["address"],
                        "name": a["name"],
                        "dex": p["relationships"]["dex"]["data"]["id"],
                        "base_token": p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1],
                        "quote_token": p["relationships"]["quote_token"]["data"]["id"].split("_", 1)[1],
                        "created_at": a["pool_created_at"],
                        "seen_at": now,
                        "reserve_usd": float(a.get("reserve_in_usd") or 0),
                        "fdv_usd": float(a.get("fdv_usd") or 0),
                        "tx_m5": a["transactions"]["m5"],
                        "volume_m5": float(a["volume_usd"]["m5"] or 0),
                        "price_usd": float(a.get("base_token_price_usd") or 0),
                    }) + "\n")
            print(now, "page", page, "new", fresh, "total", len(seen), flush=True)


if __name__ == "__main__":
    main()
