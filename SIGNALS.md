# Signals: what can be seen, and what it is worth

Every feature a trader might watch, tested against what actually happened
next. The question was the one that matters for decisions: **is there a buy
or sell trigger in here?**

**Short answer: nothing we can observe predicts which way BTC or ETH moves
next — not momentum, not RSI, not the 200-day trend, not funding, not
flows. What *is* predictable is how violent the next month will be, and
two simple risk rules built on that held up out of sample.**

---

## How it was tested

The discipline matters more than the list. This is the exercise that
produces most of the false "patterns" in trading, so:

1. **The feature list was fixed before any result was seen.** Seventeen
   features, below. Nothing was added after a look at the answers.
2. **Everything is strictly trailing.** A feature on day *t* uses data up to
   *t*'s close; the outcome starts the next day. A test in the suite plants a
   feature that peeks one day ahead and checks the machinery would catch it.
3. **Overlapping windows are not independent.** 3,000 daily 30-day returns
   are about 100 independent observations. Correlations are averaged over
   every start offset but judged on the non-overlapping count.
4. **Discovery and confirmation use different years.** A feature must be
   significant in the years before 2024, after a Benjamini–Hochberg
   correction across all 102 tests, then show the same sign and p < 0.05 in
   2024–26, which it never saw.
5. **Significance is not money.** Rules are backtested net of 0.1% per
   switch, against simply holding, with cash earning 4%.

The score is the **information coefficient (IC)**: the rank correlation
between the feature today and the outcome that followed. For crypto, 0.05
that survives out of sample is respectable; 0.2 would be remarkable.

Reproduce with the code in `src/polybot/research/signals.py`.

## What can be seen

| Feature | Source | What it measures | History from |
|---|---|---|---|
| Momentum 7 / 30 / 90 / 365 days | Coinbase daily | Recent trend | 2016 |
| Gap to 200-day average | Coinbase daily | Long-term trend | 2016 |
| RSI (14) | Coinbase daily | Overbought / oversold | 2016 |
| Realised volatility (30d) | Coinbase daily | Recent turbulence | 2016 |
| Drawdown from 1-year high | Coinbase daily | How far off the top | 2017 |
| Volume spike (30d z-score) | Coinbase daily | Unusual activity | 2016 |
| Perp funding, 7d and 30d | Deribit | Leverage demand | 2021 |
| Hyperliquid funding, 7d | Hyperliquid | Leverage demand | 2023 |
| 3-month locked rate (basis) | Deribit futures | Leverage demand, priced | 2020 |
| Implied volatility (DVOL) | Deribit options | Expected turbulence | 2021 |
| Implied minus realised vol | Deribit + Coinbase | Fear premium | 2021 |
| Stablecoin supply growth (30d) | DefiLlama | Money entering crypto | 2017 |
| Coinbase premium (7d) | Coinbase vs Deribit index | US spot demand | 2021 |

Each tested for BTC and ETH against three outcomes: the next week's
return, the next month's return, and the next month's volatility.

---

## 1. Direction: nothing survives

**0 of 68 tests.** No feature predicted the next week's or month's return
after correction. The ones that looked best in the early years are the
instructive part:

| Feature → next 30 days | Before 2024 | 2024–26 |
|---|---|---|
| BTC drawdown from 1-year high | +0.18 | **−0.09** |
| BTC 90-day momentum | +0.16 | **−0.06** |
| BTC gap to 200-day average | +0.14 | **−0.05** |
| ETH gap to 200-day average | +0.14 | **−0.13** |
| BTC RSI (14) | +0.14 | +0.06 |

Each would have been sold as a strategy on the left-hand column. Each
changed sign or faded on data it had not seen. Funding extremes, stablecoin
inflows and the Coinbase premium never reached significance at all.

**The one near-miss:** the 3-month locked rate against next week's return
kept its sign in both periods (BTC +0.14 → +0.15, ETH +0.15 → +0.16) but did
not clear the correction in the discovery years (q ≈ 0.3). It is worth
watching, not trading.

## 2. Risk: volatility is predictable

| Feature → next month's volatility | Before 2024 | 2024–26 |
|---|---|---|
| **BTC implied volatility (DVOL)** | **+0.61** | **+0.46 (p = 0.007) — survives** |
| ETH implied volatility | +0.73 | +0.13 |
| BTC realised volatility (30d) | +0.43 | +0.25 |
| ETH realised volatility (30d) | +0.46 | +0.01 |
| BTC 1-year momentum | +0.44 | +0.26 |

Volatility clustering is one of the most robust facts in finance, and the
early years show it plainly. The 2024–26 window has only 32 independent
months, so several of these are positive without clearing the bar; only BTC
implied volatility does. **High implied vol means a rough month is likely.
It says nothing about which direction** — a reason to hold less, never a
reason to sell.

## 3. Two risk rules that held up

These were fixed in advance as the classic versions, not tuned.

**The 200-day trend rule** — hold only while price is above its 200-day
average, otherwise sit in cash:

| | Period | Annual return | Worst drawdown | Switches |
|---|---|---|---|---|
| BTC hold | 2016–23 | +79.2% | −84% | — |
| BTC trend rule | 2016–23 | +79.0% | **−71%** | 43 |
| BTC hold | 2024–26 | +27.4% | −53% | — |
| BTC trend rule | 2024–26 | +25.3% | **−32%** | 29 |
| ETH hold | 2016–23 | +123.1% | −94% | — |
| ETH trend rule | 2016–23 | +144.6% | **−79%** | 39 |
| ETH hold | 2024–26 | +5.6% | −68% | — |
| ETH trend rule | 2024–26 | +24.0% | **−38%** | 21 |

It did not predict returns (section 1), yet it cut the worst drawdown in
every case, by around 40% in the years it never saw. That is not a
contradiction: the rule does not know where the market is going; it steps
aside during the long declines that make up crypto's worst losses, and pays
for it in whipsaws.

**Is 200 special? No, which is the point.** Re-run at 50, 100, 150, 250 and
300 days, in both periods, for both coins, the rule reduced the worst
drawdown against holding in **all 24 cases** — in 2024–26, BTC's −53% became
−26% to −36% whatever the window, ETH's −68% became −38% to −52%. Returns
were mixed: sometimes above holding, sometimes below. A result that only
appeared at exactly 200 days would be a fitted accident; one that appears at
every window is a property of trend-following. Shorter windows switch far
more often (15–25 times a year at 50 days), which matters for tax.

**Volatility targeting** — hold less when trailing volatility is high
(exposure = 50% ÷ 30-day vol, capped at 100%), 2024–26: BTC +28.1% vs +27.4%
holding, same drawdown (BTC rarely exceeded the target); ETH +14.8% vs +5.6%,
drawdown −60% vs −68%.

**For an Australian entity, read this before using either.** Every switch
is a disposal. Holding under 12 months forfeits the 50% CGT discount, and the
trend rule switched roughly 6–11 times a year. After tax the drawdown protection may
still be worth it, but that is your accountant's arithmetic, not this repo's.

---

## Decision card

| Question | What to look at | What it has meant |
|---|---|---|
| Is carry paying? | sUSDe yield, funding, 3-month locked rate — the regime monitor (`REGIME.md`) | Persistent: +0.75 / +0.51 / +0.83 month to month |
| How rough will the next month be? | Implied volatility (DVOL), shown in the monitor | High DVOL → high volatility next month; hold less |
| Should I be in at all? | Price vs 200-day average, shown in the monitor | Halved drawdowns out of sample; not a return forecast |
| Should I buy / sell now? | — | Nothing tested predicts direction |

## What was not tested

- **On-chain flows** (exchange inflows, whale wallets): no free, reachable
  source with history.
- **Open interest and liquidation history:** Hyperliquid serves neither
  historically.
- **Options skew history:** only the current surface is served.
- **Social sentiment:** no reachable source.
- **Altcoins:** BTC and ETH only — and both are survivors, which flatters
  every "hold" row above.
