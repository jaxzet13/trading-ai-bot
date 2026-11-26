# Tennis parlays: no edge. A parlay multiplies the edge of its legs, and the legs have almost none.

Nov 26 2026. Question (account holder): "for tennis maybe u can start backtesting parlays to see if there's
profitable ways of doing parlays aswell".

**Verdict: no profitable parlay.** Built from the same bets the lab tests, a parlay's return is the product of its
legs' returns. Where the legs lose (most pools), parlays lose faster: 2 legs lose about twice as much per dollar,
3 legs about three times. The one pool with slightly positive legs (Challenger favourites 90-96c, +0.65% a bet,
t 0.5) gives parlays of +1 to +3%, all with t under 0.8. Picking the best pool and parlay size on earlier days only
(walk-forward, 50 test days) lost 7.8% a dollar (t -1.25). Nothing to trade.

## Kalshi's own combos cannot be backtested

Kalshi sells parlays as "combos" (collection `KXMVESPORTSMULTIGAMEEXTENDED`, which accepts Challenger and ITF match
legs, and also soccer, esports, crypto and others). A combo market is created only when somebody asks for a quote, and
the price comes from market makers at that moment. On Nov 26 there were 37 such markets open, 4 with a tennis leg,
none with any volume, and no settled ones listed: there is no price history to test. Market makers usually charge
more than the product of the leg prices for a combo; if anything, that makes combos worse than building the
parlay yourself. Testing it would mean requesting live quotes going forward; not done.

## How the self-built parlay was tested (`study.py`, full output in `results.txt`)

* Data: 64 days (Sep 23 - Nov 25 2026), 14,703 settled matches (`data/tennis/hist`), 1-minute Kalshi quotes.
* Legs: the lab's band rule with its usual honest fills: decided on one minute's mid, filled the next minute at that
  minute's worst ask, Kalshi's taker fee. Back the favourite at 60 (or 30) minutes before the scheduled start in a
  price band. One leg per match.
* Parlays, built day by day in the order the legs are decided:
  * **rolled**: leg 2 is only taken after leg 1 settled (Kalshi's settlement time), so the stake really can be rolled
    over; this is what one account can do on its own.
  * **combo**: any k legs of the day in order (timing ignored), what a combo at the product price would pay.
* Return per dollar = product of (payout / (price + fee)) over the legs, minus 1. t uses days as the unit.

## Results (return per dollar staked; t; "product" = what multiplying the single-leg return predicts)

| legs from | singles | 2 legs rolled | 3 legs rolled | 2 legs combo | 3 legs combo |
|---|---|---|---|---|---|
| Challenger favourites 90-96c, 60 min before (3.4 a day) | +0.65% (t 0.5) | +1.1% (0.4) | -5.7% (-0.7) | +1.1% (0.3) | +3.1% (0.7) |
| Challenger favourites 90-96c, 30 min before | -2.1% (-1.0) | -1.7% (-0.4) | -14.8% (-1.3) | -2.2% (-0.6) | -4.2% (-0.6) |
| Challenger favourites 80-90c | -2.0% (-1.0) | -3.7% (-0.7) | -12.8% (-1.2) | -5.5% (-1.2) | -12.6% (-1.7) |
| Challenger favourites 70-80c | -6.2% (-2.2) | -23.6% (-3.5) | -34.4% (-2.3) | -16.1% (-3.0) | -21.4% (-2.4) |
| ITF favourites 90-96c | -2.5% (-1.0) | -8.8% (-0.8) | +11.8% (7 parlays) | -3.0% (-0.5) | -1.7% (-0.2) |
| ITF favourites 80-90c | -13.7% (-2.9) | -41.6% (-3.0) | -14.3% (-0.7) | -25.8% (-2.5) | -18.5% (-1.4) |
| ATP/WTA favourites 80-96c (2.2 a day) | +0.8% (0.3) | +7.6% (28 parlays, 1.0) | +28.9% (10 parlays) | -0.7% (-0.1) | -1.3% (-0.1) |
| Any favourite 80-96c (14.7 a day) | -2.6% (-2.1) | -2.3% (-0.7) | -3.9% (-0.7) | -5.0% (-2.0) | -9.2% (-2.2) |
| Any favourite 60-80c (20.4 a day) | -6.6% (-3.3) | -19.5% (-2.6) | -43.8% (-3.7) | -10.5% (-2.7) | -20.1% (-3.1) |

The few positive parlay cells rest on 7 to 28 parlays, flip sign between the rolled and combo versions of the same
legs, and do not hold up when chosen walk-forward:

| walk-forward choice (50 test days) | bets | return per dollar | t | halves |
|---|---|---|---|---|
| any pool, any number of legs | 71 | -7.8% | -1.25 | -7.7 / -7.9 |
| singles only | 125 | -4.4% | -2.05 | -11.1 / -0.2 |
| rolled parlays only | 84 | -4.3% | -0.61 | -6.3 / -0.9 |

## Why parlays cannot create an edge

A parlay at the product price is the same as betting leg 1 and putting every cent of the winnings on leg 2. Its
expected return is (1 + r)^k - 1, where r is a leg's return: about k times r. Positive legs make a parlay a bigger,
riskier version of the same small edge; negative legs (the spread plus Kalshi's fee on every leg) make it lose k
times faster. The only way a parlay beats its legs is a combo priced below the product of the legs, which is the
opposite of how combo market makers price.

## Side note on the live tennis auto-better

In this run the Challenger 90-96c singles, 60 minutes before the start, earned +0.65% a bet (t 0.5) and the same band
30 minutes before lost 2.1%. That is weaker than the "+2c a bet, t 1.7" from the earlier lab run (different minutes
and a different sample of strategies). The auto-better's record so far (23 bets, 21 won, +$1.25) is consistent with
either. Still unproven; no change made.

## Wider search (Nov 26, `search.py`, output in `search_results.txt`)

Asked for more strategies, every rule of the lab's grid became parlay legs: 13,308 rules with at least 30 bets (price
bands at every 10 minutes from 3 h before to 3 h into play, in-play swing rules, pre-match drift rules, five tour
scopes), each as singles, combos of 2 / 3 / 4 and rolled parlays of 2 / 3: about 80,000 candidates.

* **Same-day correlation of leg results: none** (Challenger 90-96c favourites -0.05 over 443 pairs; favourites
  80-90c +0.02 over 3,021; 60-70c +0.005 over 4,615). Legs on the same day are independent, so a parlay is worth
  exactly the product of its legs. Positive correlation was the one way a rolled parlay could beat its legs.
* **Best in-sample: t 3.7** (Challenger favourites 90-95c two hours before, 3-leg combos, +11.6% on 60 parlays).
  With 80,000 candidates the best t from luck alone is about 4, so this list is what a search over noise finds.
* **Walk-forward (50 test days, each day's choice made on earlier days only): all negative.**

| choice made on earlier days | bets | return per $1 | t | halves |
|---|---|---|---|---|
| A the best rule and parlay type | 67 | -13.1% | -1.62 | -17.0 / -3.9 |
| B the best single rule, as singles | 59 | -11.0% | -1.29 | -12.5 / -6.9 |
| B the same rule, rolled 2 | 18 | -15.8% | -1.05 | |
| B the same rule, combo 2 / 3 | 23 / 11 | -24.9% / -30.5% | -1.34 / -1.22 | |
| C legs of the day from the 5 best rules, singles | 400 | -2.5% | -0.81 | -9.1 / +2.5 |
| C the same legs, rolled 2 | 103 | -6.1% | -0.77 | -5.0 / -6.8 |
| C the same legs, rolled 3 | 60 | -12.7% | -1.79 | -25.4 / -5.9 |

Every parlay version loses more than the singles of the same legs, as the arithmetic says it must. Nothing to trade.
