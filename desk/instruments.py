"""Instrument specs. Costs are a round trip (spread + commission + a little slippage) in price units, set to what a
prop-firm CFD account typically charges. min_risk skips signal candles too small to trade through the spread."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    name: str
    symbol: str          # Dukascopy symbol
    cost: float          # round-trip cost, price units
    min_risk: float      # smallest stop worth trading, price units
    futures: str         # the futures contract that trades the same thing
    sessions: tuple      # (label, NY start hhmm, NY end hhmm) sessions worth testing


INSTRUMENTS = {
    "NAS100": Instrument("NAS100", "USATECHIDXUSD", 1.0, 5.0, "NQ / MNQ", (("ny", 930, 1600),)),
    "US30": Instrument("US30", "USA30IDXUSD", 3.0, 12.0, "YM / MYM", (("ny", 930, 1600),)),
    "US500": Instrument("US500", "USA500IDXUSD", 0.5, 1.5, "ES / MES", (("ny", 930, 1600),)),
    "XAUUSD": Instrument("XAUUSD", "XAUUSD", 0.35, 1.0, "GC / MGC", (("london", 300, 1100), ("ny", 830, 1600))),
    "EURUSD": Instrument("EURUSD", "EURUSD", 0.00012, 0.0005, "6E / M6E", (("london", 300, 1100), ("ny", 800, 1600))),
    "GBPUSD": Instrument("GBPUSD", "GBPUSD", 0.00015, 0.0007, "6B / M6B", (("london", 300, 1100), ("ny", 800, 1600))),
}
