# Funding-rate harvest: measured

The last untested candidate from `STRATEGY.md`. Perps have no expiry, so a
periodic payment tethers them to spot: when the perp trades rich, longs pay
shorts. Short the perp, buy the spot, hold no price exposure, collect the
payment.

Measured over **365 days of hourly funding prints from 25 Hyperliquid perps**
(8,511 hours where all names overlap), with execution and basis charged.

**Verdict: the carry is real and it is not a business. It pays roughly the
T-bill rate for names you can actually hedge, and the excess return is
concentrated in names you cannot.**

Reproduce with `polybot funding --coins BTC,ETH,SOL --days 365`.

---

## 1. First, the quoted number is wrong

Earlier work here recorded a "median 11.0% APR baseline across all coins."
That figure was a snapshot of the live `funding` field, and 11.0% is
Hyperliquid's **floor rate** — 0.0000125/hour, which annualises to 10.95%.
It is what the venue charges when the premium is approximately zero. It is a
constant, not a market signal, and at any moment most of the book sits on it.

Over a full year of history the real number is:

| | Across 25 perps |
|---|---|
| Median gross funding APR | **+6.19%** |
| Mean | +6.26% |
| Range | −24.31% (VVV) to +28.81% (XMR) |
| Coins with positive carry | 23 of 25 |

So the starting material is about **6%, not 11%**.

---

## 2. What sits between 6% and the bank balance

**Execution, four legs.** The position is two instruments, opened and closed:
two perp fills and two spot fills. At Hyperliquid's 0.045% perp taker, a
0.10% spot taker at an external venue, and 2bp of slippage a leg, that is
**0.37% of notional per round trip**. Against 6% gross the position must
survive **~22 days** just to repay its own execution.

**Basis drift, which turns out not to matter.** Enter when the perp is cheap
and exit when it is rich and you hand back the carry. Measured across all 25
coins over the full year, median basis drift is **−0.07% of notional** —
essentially nothing. This is the term everyone warns about and it is not the
problem here.

**Capital, not notional.** The spot leg is bought outright and the perp leg
needs margin. Every number below is divided by a 1.25× capital multiplier,
which assumes 4× leverage on the hedge — already aggressive when the spot
collateral sits at a different venue and cannot rescue a liquidation.

---

## 3. Three shapes, and only one survives contact

### Timing the carry destroys it

Enter when trailing funding exceeds 10% APR, exit when it drops below 2%:

| | |
|---|---|
| Median net APR on capital | **−0.81%** |
| Coins where it made money | 11 of 25 |
| Median round trips per year | 26 |

Twenty-six round trips costs **9.6% of notional a year** against roughly 5%
of gross funding. Execution came to **125% of gross** on BTC. The rule is
sound and the trade is right; paying to express it that often is what loses.

### Always on is better and still not enough

Short every coin, hold the whole year, pay execution once:

| | |
|---|---|
| Equal-weight net APR on capital | **+3.72%** |
| Median | +4.41% |
| Worst coin | −19.75% (VVV) |
| Positive | 21 of 23 |

Against a **4.08%** 3-month T-bill, the passive version of this trade earns
**less than cash** while carrying liquidation and custody risk.

### Selection is where the edge actually is

Funding is persistent, and that is a genuine measurable signal:

> **corr(trailing 30-day funding, forward 30-day funding) = 0.512**
> over 989 coin-months. Top-quartile trailing funding of +11.57% was
> followed by **+10.35% realised**.

Holding the richest 5 names on trailing funding, rebalanced monthly:

| Slippage a leg | Net APR on capital | vs 4.08% cash |
|---|---|---|
| 2bp | +6.08% | **+2.00%** |
| 10bp | +4.71% | +0.63% |
| 25bp | +2.14% | −1.94% |
| 50bp | −2.14% | −6.22% |

Rebalancing beats timing because names carried across a rebalance pay no
execution — only the difference trades. That is the whole structural
advantage, and it is worth about 7 points of APR over the timing rule.

---

## 4. Why it still fails

### The return is one memecoin perp

| Name | Share of gross carry |
|---|---|
| **FARTCOIN** | **27%** |
| Top 3 names combined | **51%** |

FARTCOIN was selected in **9 of 10 months**. Strip it out and the strategy is
ordinary.

### The names that pay are the names you cannot hedge

Restricting to coins with deep, liquid spot markets on major venues drops the
universe from 23 to 16 — removing FARTCOIN, HYPE, PUMP, VVV, XPL, ZEC and
kPEPE. At a realistic 10bp slippage:

| Universe (top N perps by volume) | Net APR | vs cash |
|---|---|---|
| 8 | +2.65% | **−1.43%** |
| 12 | +1.86% | **−2.22%** |
| 16 | +2.76% | **−1.32%** |
| 20 | +3.05% | **−1.03%** |
| 23 (all, incl. the illiquid tail) | +4.71% | +0.63% |

**The excess return over cash appears only when the illiquid tail is
included.** That is the finding. The tail is precisely where 2bp of slippage
is a fantasy, and at 25bp the whole thing goes negative.

Month by month on the hedgeable universe at 10bp: **5 of 11 months came in
below cash**, mean +4.54% against 4.08% risk-free.

### And there is no hedge on Hyperliquid itself

The one version with no transfer, no second custodian and no second set of
credentials would be to hold both legs on Hyperliquid. Twelve of the 23 perps
do have a spot pair. Their 24-hour spot volume:

| Pair | 24h volume |
|---|---|
| UBTC, UETH, USOL, UAVAX, UENA, UWLD, PEPE | **$0** |
| UXPL | $24 |
| PUMP | $20 |
| HYPE | $769 |
| TAO1 | $260,810 |
| UZEC | $355,142 |

There is no intra-venue hedge. Every position requires a second venue, a
transfer, and collateral that cannot rescue the other leg.

---

## 5. Verdict against the nine gates

The carry passes the gates that killed everything else — it has a real
structural cause (perp-spot tethering), a measurable and persistent signal
(0.512 autocorrelation), and fees that do not consume it outright. It fails
on the two that matter most here:

- **Capacity.** The edge is in names whose spot books cannot absorb a hedge
  at the assumed cost.
- **Compensation for risk.** ~0.2–0.6% over T-bills for cross-venue custody,
  perp liquidation risk, and continuous operational attention.

This is not a fee problem like Polymarket or an adverse-selection problem
like the maker book. It is the first candidate tested here that *works* and
simply does not pay enough.

---

## Honest limitations

- **The universe is survivorship-selected.** The 25 coins are today's top
  perps by volume. Names delisted during the window are absent, which biases
  every number here optimistic.
- **Slippage is assumed, not measured.** No book data was recorded for these
  names. It is the single largest uncertainty, which is why the sweep exists
  rather than a point estimate.
- **One year is one regime.** Funding was predominantly positive over the
  window. A sustained bear market flips the sign, and the selection rule as
  written holds the top N even when the top N pays negative.
- **Ten monthly periods is a small sample.** The 7-day rebalance gives 46
  periods and agrees, which is the main reason to believe the shape.
- **Spot depth is proxied by perp volume.** Binance and Coinbase spot APIs
  return 403 from this environment's egress policy, so hedgeability was
  approximated from Hyperliquid's own spot books and a perp-volume cutoff
  sweep. Adding those domains to the environment allowlist would let the
  hedge cost be measured rather than assumed — and that is the number the
  whole verdict turns on.
