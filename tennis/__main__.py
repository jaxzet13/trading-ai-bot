import sys


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    cmd = a[0] if a else ""
    if cmd == "collect":
        from . import collect
        collect.run(once="once" in a)
    elif cmd == "arbs":
        from . import arb
        arb.scan()
    elif cmd == "markets":
        from . import collect
        rows = collect.snapshot()
        ev = {}
        for r in rows:
            ev.setdefault((r["series"], r["event"]), []).append(r)
        print(f"{len(rows)} open match markets in {len(ev)} matches")
        for (s, e), ms in list(ev.items())[:20]:
            print(f"  {s:22s} " + "  vs  ".join(f"{m['player']} {m['yes_bid']}/{m['yes_ask']}" for m in ms))
    else:
        sys.exit("usage: python -m tennis collect [once] | arbs | markets")


if __name__ == "__main__":
    main()
