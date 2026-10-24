# NYOpenCandle: the day-trading robot

Trades the NAS100 New York open strategy automatically on MetaTrader 5. One trade a day, decided at 09:35
New York time, always closed by 15:30. Never holds overnight.

## Setup (about 15 minutes)
1. Buy the prop account (recommended: a static-drawdown 2-step such as FundedNext, FundingPips or FTMO). Pick
   MetaTrader 5 as the platform. Check the firm's rules page says Expert Advisors / EAs are allowed (FTMO and
   FundedNext allow them; read your firm's current rule).
2. Install MetaTrader 5 from the firm's download link and log in with the account details they email you.
3. In MT5: File > Open Data Folder > MQL5 > Experts. Copy `NYOpenCandle.mq5` there. Back in MT5, open the
   Navigator, right-click Expert Advisors > Refresh. Double-click the file to open MetaEditor and press Compile (F7).
4. Open a chart of the firm's Nasdaq symbol (US100, NAS100, USTEC or NDX100). Any timeframe.
5. Drag NYOpenCandle onto the chart. In Inputs set **StartBalance** to the account size (e.g. 100000) and leave
   **RiskPct** at 0.75. Tick "Allow Algo Trading". Press the Algo Trading button in the toolbar so it turns green.
6. The computer must be on with MT5 open at 09:30 New York every weekday. Easiest is a cheap Windows VPS
   ($10-20/month; many firms give one free) running MT5 24/7.

The Experts tab logs every decision ("no trade: ...", "BUY 2.40 lots ...", "closed: 15:30 New York").

## Settings worth knowing
| Input | Default | Meaning |
|---|---|---|
| RiskPct | 0.75 | % of the starting balance risked per trade. 0.75 on 100k static-drawdown CFD accounts. |
| StartBalance | 100000 | The firm's account size. Sizing and the drawdown cut use it. |
| MaxLossPct | 10 | The firm's max loss. The robot halves risk at 3% down and quarters it at 6% down. |
| DailyStopPct | 4 | Closes and stops for the day at a 4% loss (firm limit is usually 5%). |
| ServerMinusNY | 0 | Auto-detects New York time live. In the Strategy Tester set it (7 for most "New York close" brokers). |

## Before going live
Run it in the MT5 Strategy Tester on US100 M5 for 2024-2026 with ServerMinusNY set, and on the firm's free
trial for a week. It was written here without access to MetaEditor, so compile errors or broker-specific quirks
(symbol name, filling mode, minimum lot) are possible; the log says what it did and why.
