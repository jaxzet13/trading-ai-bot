"""Tennis on Kalshi: a separate app from the crypto bot (kalshi15m), sharing no code paths with it.

Account holder, Nov 23: arbitrage / consistent-profit tennis betting, tested the same way as the 15-minute crypto
strategies (forward tests on real Kalshi data, fills decided by what actually traded), then real money, with the
real-money runner behaving exactly like the tests. Kalshi only; risk-free arbs and value bets tested separately.

    python -m tennis collect      24/7 recorder of every open tennis match's top of book (data/tennis/books/)
    python -m tennis arbs         risk-free arbs found in the recorded books, with the profit after fees
    python -m tennis markets      the open tennis match markets right now
"""
