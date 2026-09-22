# Funding-rate harvest: measured

The last untested candidate from `STRATEGY.md`. Perps have no expiry, so a
periodic payment tethers them to spot: when the perp trades rich, longs pay
shorts. Short the perp, buy the spot, hold no price exposure, collect the
payment.

Measured over **365 days of hourly funding prints from 25 Hyperliquid perps**
(8,511 hours where all names overlap), with execution and basis charged.

**Verdict (revised after measuring execution from live order books — see
section 6): the carry works, and it has a hard capacity ceiling. At about
$60k of capital it beats cash by ~1.3% a year at a 0.10% spot fee — roughly
$800 a year. Scale it up and the excess disappears: at ~$300k it needs a
spot fee under 0.085%, and at ~$1.5M it loses to cash even with free spot
trading. Measured in dollars, the most this trade earns above a term
deposit is on the order of $1,000–2,000 a year.**

An earlier version of this document concluded that the excess lived only in
names you cannot hedge. That was a judgement about spot listings and it was
wrong: 22 of the 23 names in the universe can be hedged at $10k a leg. The
binding constraint is order-book depth as size grows, not whether a market
exists.

Reproduce with `polybot funding --coins BTC,ETH,SOL --days 365`, and the
measured-cost version with `polybot hedge-cost`.

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

### The names that pay are the names you cannot hedge — superseded

> **Superseded by section 6.** This subsection excluded seven names on the
> judgement that they had no deep spot market. Measured against Coinbase's
> live books, all seven are listed and six of them fill at $10k per leg. The
> table below is kept as the record of the assumption that was tested and
> failed; section 6 replaces its conclusion.

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

- **Capacity.** Measured in section 6: the excess over cash shrinks as size
  grows and is gone by ~$1.5M of capital at any fee.
- **Compensation for risk.** On the order of $1,000–2,000 a year above a term
  deposit, at best, for cross-venue custody, perp liquidation risk, and
  continuous operational attention.

This is not a fee problem like Polymarket or an adverse-selection problem
like the maker book. It is the first candidate tested here that *works* and
simply does not pay enough.

---

## 6. Measured: hedge execution from live order books

Sections 3 and 4 assumed slippage. This section measures it, by walking the
real books: buy `notional` on Coinbase spot (ask side) and sell `notional` on
Hyperliquid perps (bid side), at three sizes, five snapshots a minute apart,
median kept. Cost is measured against the mid, so it includes the
half-spread. Reproduce with `polybot hedge-cost`.

### Cost per leg, spot + perp, in basis points

| Coin | $10k | $50k | $250k |
|---|---|---|---|
| BTC | 0.1 | 0.4 | 1.6 |
| ETH | 0.3 | 1.7 | 4.3 |
| SOL | 1.5 | 2.6 | 5.8 |
| XRP | 2.2 | 4.8 | 12.2 |
| HYPE | 2.7 | 6.5 | — |
| DOGE | 4.9 | 10.7 | 19.3 |
| LINK | 4.9 | 11.8 | — |
| ZEC | 6.9 | 9.4 | 19.6 |
| kPEPE | 13.2 | 30.9 | 66.7 |
| PUMP | 20.4 | 48.7 | — |
| **FARTCOIN** | **27.2** | — | — |
| XPL | 31.9 | — | — |
| VVV | — | — | — |

— = the size exhausted the visible book in at least one snapshot. Full table
for all 23 names in the command output. XMR and LIT have no Coinbase spot
market.

Two corrections fall out immediately. The majors cost **far less** than the
10bp stress case assumed: BTC and ETH are under half a basis point at $10k.
The names carrying the return cost **far more** than the 2bp base case:
FARTCOIN, a quarter of the gross carry, costs 27bp a leg at $10k.

### Carry on measured costs: top 5, monthly rebalance

| Capital | Names fillable | Net APR at 0.10% spot fee | vs 4.08% cash | Break-even spot fee |
|---|---|---|---|---|
| ~$62k ($10k/name) | 22 of 23 | +5.40% | **+1.32%** (≈ +$825/yr) | **0.262%** |
| ~$312k ($50k/name) | 15 of 23 | +3.97% | −0.11% | **0.085%** |
| ~$1.56M ($250k/name) | 7 of 23 | +0.61% | −3.47% | **none** |

At small size this is better than section 4 suggested, for two reasons: the
high-carry names turn out to be hedgeable at $10k, and under a monthly
rebalance the expensive names are held continuously, so their high cost is
paid about twice a year rather than every month. At $10k per name, every
month was positive at spot fees up to 0.10%.

It does not scale. As size grows the thin names drop out of the fillable
universe — FARTCOIN is gone by $50k — the remaining carry falls from 9.4% to
3.6% gross, and at ~$1.5M the strategy loses to cash even with free spot
trading. Even with **zero** spot fees, the best case in dollars is about
**$1,340 a year** at $62k and **$1,960 a year** at $312k above a term deposit.
That is the ceiling on this trade for a single operator on these venues.

### The fee is yours to look up

The break-even column is reported instead of a verdict at one fee because
the spot fee is the input that depends on you. Coinbase's schedule varies by
region and volume tier, and its published fee page returned 403 to automated
fetches from this environment, so which schedule an Australian entity gets
could not be confirmed. Secondary reporting from September 2026 describes
entry-tier taker fees from roughly 0.10% to over 1% depending on region.
**If your taker fee is above 0.262%, this trade loses to cash at every
size.**

---

## Honest limitations

- **The universe is survivorship-selected.** The 25 coins are today's top
  perps by volume. Names delisted during the window are absent, which biases
  every number here optimistic.
- **Slippage is measured over one short window.** Section 6 walks live books,
  but five snapshots across five minutes at one time of day (about 9am in
  Sydney) is a thin sample of how depth varies. Sections 3–4 still use the
  assumed figures.
- **Larger sizes are priced as a single sweep.** Hyperliquid's `l2Book` shows
  20 levels a side, so "unfillable" at $50k and $250k means the visible book
  ran out. Slicing orders over time would do better and add legging risk;
  those rows are pessimistic in that specific sense.
- **Coinbase is one venue.** Binance, usually the deepest spot book, returns
  451 (a US geoblock on this environment's egress). Deeper venues available
  to an Australian entity could lower the thin-name costs.
- **One year is one regime.** Funding was predominantly positive over the
  window. A sustained bear market flips the sign, and the selection rule as
  written holds the top N even when the top N pays negative.
- **Ten monthly periods is a small sample.** The 7-day rebalance gives 46
  periods and agrees, which is the main reason to believe the shape.
- **The spot fee is unverified for Australia.** See section 6; the result is
  given as a break-even fee for that reason.
