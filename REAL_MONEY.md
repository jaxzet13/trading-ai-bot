# Trading NEAR 15-minute markets with real money

This guide covers `python -m kalshi15m real`. It is a small program that trades **one** strategy on your
own Kalshi account, using your own API key, on your own computer. Read the whole page before you use real money.

> **You can lose money.** The evidence below is promising but short. Start on the demo exchange, then
> trade real money with $1–2 bets, and keep going only if the real results hold up.

---

## 1. What it does

Every 15 minutes Kalshi lists a market: *"Will NEAR's price be at or above $X at the end of these
15 minutes?"* (series `KXNEAR15M`). YES pays $1 if it is, NO pays $1 if it isn't.

About half a second after each minute starts, the program:

1. reads the market's best prices from Kalshi, and NEAR's price and recent volatility from Coinbase;
2. works out a "fair" chance that NEAR finishes above the target (a standard lognormal model);
3. checks minutes 2 to 13 of each market. It buys only if YES or NO is selling at least **12 cents below** that
   fair chance, and only on the **first** minute that happens;
4. places **one** order in that market: a limit buy at the price it saw, marked *immediate-or-cancel*. The
   order takes whatever is available at that price or better, right away. Anything that doesn't fill is
   cancelled, so no order is ever left sitting on the book;
5. records what **actually** filled, then collects the result from Kalshi when the market settles.

The rule is the same one the paper-trading bot runs (`fair_value`, start 2, end 13, edge 0.12). The
real runner reuses the paper bot's code to calculate the signals, and a test checks that both programs
pick the same trades. The rule is frozen: the program refuses to start if `kalshi15m/real.json` changes it.

## 2. The honest evidence

| Test | Result |
|---|---|
| 15-day locked holdout (Oct 17 – Nov 1 2026), never used for tuning | +$1,307 on 811 trades, **t = 2.53** |
| Blind test on Kalshi's Jul–Aug archive | +$3,099 on 1,782 trades, **t = 3.83** |
| Live paper trading (real-time quotes, no money) | about 66 settled trades, roughly **+$3 per $5 bet** |

The bad news:

* **The live record is short.** 66 trades can easily look good by luck. Results come in bunches: whole
  days can be losing days.
* **Speed is everything.** The edge comes from Kalshi's price trailing NEAR's real price for less than a
  minute. In backtests, acting **one minute later wipes out the edge**. A slow or unreliable connection
  will cost you.
* **Real fills will be worse than paper.** Paper trading assumes you get the full order at the price shown.
  NEAR order books are thin, often well under 100 contracts at the best price. Real orders will sometimes
  fill partly or not at all, and bigger bets make this worse. Other traders chase the same lag.
* **A backtest t-statistic of 2.5–3.8 is good, not proof.** Many strategies were searched to find this one.

The realistic hope is a modest edge at small size, not paper-sized profits.

## 3. Before you start: Kalshi eligibility and taxes

* Kalshi is a US exchange regulated by the **CFTC**. You need a verified Kalshi account (identity
  check/KYC). Kalshi decides who is eligible (country, state, age). Check its site for the current rules.
* Profits are taxable. Kalshi can send tax forms, and the right treatment depends on your situation. Keep
  the log file (`data/kalshi15m/real_log.jsonl`) and ask a tax professional.

## 4. Create your API key

You need **two** keys: one for the demo exchange (fake money) and one for the real exchange. Keys don't
work across the two.

1. Log in at **https://demo.kalshi.co** (demo) or **https://kalshi.com** (real).
2. Open your **Account / Profile settings** (`kalshi.com/account/profile`) and find **API Keys**. Click
   **Create New API Key**. Either key type works (Ed25519 or RSA).
3. Copy the **Key ID** shown on screen (it looks like `a952bcbe-ec3b-4b5b-...`).
4. The **private key file downloads only once.** Kalshi does not keep a copy. Move it somewhere private,
   for example `~/.kalshi/demo.pem` and `~/.kalshi/live.pem` (Windows: `C:\Users\you\.kalshi\live.pem`).
5. **Keep the private key secret.** Anyone who has it can trade your account. Never email it, paste it
   into a chat, or put it inside this project folder. The repo's `.gitignore` excludes `*.pem`/`*.key`
   anyway. If the key ever leaks, delete it on Kalshi's API Keys page right away.

The program reads the key **only** from two environment variables and never prints or logs it.

## 5. Step by step

### 5.1 Install (once)

You need Python 3.10 or newer and this repo on your computer.

```bash
cd trading-ai-bot
python3 -m venv .venv
.venv/bin/pip install -r kalshi15m/requirements.txt          # Windows: .venv\Scripts\pip install -r kalshi15m\requirements.txt
```

`scripts/run_real.sh` (Mac/Linux) and `scripts\run_real.bat` (Windows) do this for you on first run.

### 5.2 Watch the signals first (no key, no orders)

```bash
.venv/bin/python -m kalshi15m real --dry-run --minutes 30
```

This prints one line per minute and `WOULD BUY ...` when the rule fires. It uses live public data and
sends nothing.

### 5.3 Set the environment variables

**Mac / Linux** (for the current terminal; add the lines to `~/.zshrc` or `~/.bashrc` to keep them):

```bash
export KALSHI_KEY_ID="your-key-id"
export KALSHI_PRIVATE_KEY_PATH="$HOME/.kalshi/demo.pem"      # demo key while testing on demo
```

**Windows PowerShell** (current window):

```powershell
$env:KALSHI_KEY_ID = "your-key-id"
$env:KALSHI_PRIVATE_KEY_PATH = "C:\Users\you\.kalshi\demo.pem"
```

To keep them for every new window, use `setx KALSHI_KEY_ID "your-key-id"` and
`setx KALSHI_PRIVATE_KEY_PATH "C:\Users\you\.kalshi\demo.pem"`, then open a new window.
In the old `cmd.exe`, the per-window form is `set KALSHI_KEY_ID=your-key-id`.

When you move from demo to real money, point both variables at your **real** key ID and key file.

### 5.4 Check the connection (places no orders)

```bash
.venv/bin/python -m kalshi15m real check --demo       # with the demo key
.venv/bin/python -m kalshi15m real check --live       # with the real key
```

This logs in and prints your balance, your open positions and the current NEAR market. It ends with
`check OK (no orders placed)`.

### 5.5 Run on demo for at least a day

```bash
bash scripts/run_real.sh            # Mac/Linux, defaults to --demo
scripts\run_real.bat                # Windows
```

Demo uses fake money, but the order books on demo are usually **empty**. Most demo orders will come back
"not filled (0 contracts)", which is expected. What demo proves is that login, order format, logging,
restarts and the stop switch all work on your machine. Run it for a day, then look at
`python -m kalshi15m real-report` and check for errors in `data/kalshi15m/real_console.log`.

### 5.6 Go live with $1–2 bets

The default bet is **$2** (`stake_usd` in `kalshi15m/real.json`). For $1, set it to `1.0`. Then:

```bash
bash scripts/run_real.sh --live
```

It asks you to type `I UNDERSTAND THIS USES REAL MONEY` exactly. Nothing can skip this step, so a
restart after a hard crash also waits for you. (Ordinary errors restart inside the program without
asking again.)

Keep at least `min_balance_usd` + about $25 in the account. The program stops if your balance falls
below `min_balance_usd`.

### 5.7 Read the report

```bash
.venv/bin/python -m kalshi15m real-report             # from the log
.venv/bin/python -m kalshi15m real-report --live      # also cross-checks Kalshi's settlement records
```

It shows, per UTC day: orders sent, orders that filled, settled markets, wins, money spent, fees, and
P&L. At the bottom are the **average P&L per trade**, a t-statistic, the win rate and the **fill rate**.
P&L counts only real fills and Kalshi's settlement records. It never assumes an order filled.

### 5.8 How to stop

* **Ctrl+C** in the window: the program finishes the current step and exits cleanly.
* **Kill switch:** create a file named `STOP` in the repo folder (`touch STOP`, or on Windows make a new
  empty file called `STOP`). The program places no new orders and exits within about a second. The
  launcher does not restart it while `STOP` exists. Delete the file to run again.
* Positions you already hold settle on their own when their 15 minutes end, whether or not the
  program is running.

## 6. Safety limits (`kalshi15m/real.json`)

| Setting | Default | Meaning |
|---|---|---|
| `stake_usd` | 2 | money per bet (contracts = stake ÷ price, rounded down) |
| `max_contracts_per_order` | 50 | hard cap per order |
| `max_daily_loss_usd` | 20 | stop for the rest of the UTC day once settled losses plus money still at risk reach this |
| `max_trades_per_day` | 120 | orders per UTC day |
| `max_open_positions` | 1 | positions in markets that are still open |
| `min_balance_usd` | 10 | exit if your Kalshi balance falls below this |
| `min_price` / `max_price` | 0.03 / 0.95 | never pay less or more than this per contract |
| `max_data_age_s` / `max_decision_lag_s` | 5 / 5 | skip if prices are over 5 s old, or the decision comes over 5 s after the minute |

It also bets **once per market**, even across restarts (it rebuilds this from its own log). On a network
error while sending an order, it **looks the order up** instead of sending it again. If it still can't
confirm the order, it doesn't retry. It works the order out later from Kalshi's fills and settlements.
The program refuses to start in `--live` if any of these limits is missing.

## 7. Raising the size, and when to quit

* **Don't raise anything for the first 200 real trades** (about 2–4 weeks).
* After that, raise `stake_usd` **only if** the average real P&L per trade is clearly positive, the fill
  rate is good (over ~70%), and the average fill price is close to the quoted price. Raise it in steps, at
  most doubling, with another 100+ trades between steps. Raise `max_daily_loss_usd` by the same factor.
* Expect partial fills to grow once a bet is more than a few tens of contracts. NEAR books are thin.
* **Stop trading** (create `STOP`) if any of these happens:
  * after 200 real trades, the average P&L is below **+$0.20 per $2 bet** (+10% of stake);
  * the daily loss cap is hit **3 or more times in two weeks**;
  * the fill rate drops a lot, or fills are often at worse prices than the paper bot sees.
* Don't re-tune the rule from live results. A rule changed to fit recent losses loses its test record.

## 8. Where to run it

The edge lasts seconds, so run the program on an **always-on machine with a fast, stable connection**,
ideally a small cloud server in **US East** (Kalshi's servers are in the US). A laptop that sleeps or
drops Wi-Fi will miss trades. The Mac launcher keeps the Mac awake, but a closed lid still sleeps.
Check the clock too: your computer's clock must be accurate (automatic time sync on). Signatures carry a
timestamp, and decisions are timed to the minute.

## 9. Files

| File | What |
|---|---|
| `kalshi15m/real.py` | the runner (Kalshi API v2 client, signals, risk limits, report) |
| `kalshi15m/real.json` | strategy (frozen) and limits |
| `scripts/run_real.sh`, `scripts/run_real.bat` | launchers (install, default to demo, restart after crashes) |
| `data/kalshi15m/real_log.jsonl` | every decision, order, fill and settlement (JSON lines; separate from the paper log) |
| `data/kalshi15m/real_console.log` | screen output |
| `tests/test_real.py` | offline tests (`python tests/test_real.py`) |

## Starting with $10

`kalshi15m/real.json` assumes more than $10 in the account (it stops if the balance falls under $10). For a
$10 test use `kalshi15m/real_10.json`: same frozen NEAR rule, $1 per bet, at most $4 lost per day, and it
stops for good if the balance drops under $4. Add `--config kalshi15m/real_10.json` to every command:

```bash
.venv/bin/python -m kalshi15m real check --live --config kalshi15m/real_10.json
bash scripts/run_real.sh --live --config kalshi15m/real_10.json
```

## All 9 coins: fair value + fair value v2

`kalshi15m/real_all9.json` runs the two pooled strategies that passed the strict holdout bar
(`fair_value` with vol_mult 0.8 and `fair_value_v2` with 60-min vol, prices 20-80c) on BTC, ETH, SOL, XRP,
HYPE, BNB, NEAR, DOGE and ZEC. One runner per coin; on each 15-minute market the first rule that fires
places the only bet (the two rules never stack or take opposite sides in one market, which Kalshi would
net into one position). Limits are per coin: $1 a bet, $2 daily loss per coin, one open bet per coin.
It logs to `data/kalshi15m/real_all9_log.jsonl`.

Run it on the demo exchange first (fake money):

```bash
.venv/bin/python -m kalshi15m real check --demo --config kalshi15m/real_all9.json
bash scripts/run_real.sh --demo --config kalshi15m/real_all9.json
.venv/bin/python -m kalshi15m real-report --demo --log data/kalshi15m/real_all9_log.jsonl
```

Note: on their own, SOL, BNB and ZEC failed their backtests; the pass is for the 9 coins as a group.
