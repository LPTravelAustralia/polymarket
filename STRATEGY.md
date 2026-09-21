# Evaluating this as a trader would

Not "can we build it" — that question is nearly always yes and nearly always
irrelevant. The question is whether there is a durable, positive-expectancy,
capacity-bearing edge after every cost, and whether the risks that kill it
are ones we can survive.

This document is the process I'd run on any strategy, ordered so the cheapest
tests that can kill it come first, then that process applied to what we
measured on Polymarket.

---

## Part 1: The process

Order matters. Each gate is cheaper than the one after it, so run them in
sequence and stop at the first failure. Most retail strategy work inverts
this — builds the system first, checks expectancy last — which is why most
of it dies expensively rather than cheaply.

### Gate 1 — What is the source of edge, in one sentence?

If you can't name *who is on the other side and why they are willing to lose*,
you don't have an edge, you have a backtest. Legitimate answers on a
prediction market:

- **Information** — you know something sooner or more precisely (a live feed
  vs a delayed broadcast).
- **Structure** — prices violate an identity (a complete set must cost $1).
- **Liquidity provision** — you're paid to absorb others' urgency.
- **Behavioural** — a persistent, documented bias (favourite-longshot).

"The model says so" is not a source. It's a description.

### Gate 2 — Magnitude, measured in the unit you trade

Get the edge into **currency per unit** — cents per share, not percentages
and not Sharpe. Percentages hide fee interaction; at Polymarket's `p(1−p)`
fee curve, the same percentage edge is profitable at 0.90 and loss-making at
0.50.

### Gate 3 — Net expectancy after *all* costs

`Expectancy = (Win% × AvgWin) − (Loss% × AvgLoss)`, with fees, slippage,
and the spread you actually cross included. This gate kills more strategies
than every other gate combined, and it's arithmetic — it costs an afternoon.

**The discipline: subtract measured costs, not assumed ones.** Pull them from
real fills.

### Gate 4 — Capital velocity

Per-trade edge is meaningless without knowing how often capital recycles. A
1% edge is superb at 50 turns a year and pointless at 2.

On a prediction market this is **time to resolution**, and it's the variable
retail analysis forgets entirely. Capital is locked from entry to settlement.
A 1% lock that resolves in 3 days compounds to something enormous; the same
1% locked for 9 months is worse than a savings account.

### Gate 5 — Capacity

At what size does your own trading destroy the edge? Measure the depth
available at profitable prices, not the headline volume. Many real edges have
capacity of a few hundred dollars per opportunity — fine as a hobby,
irrelevant as a business, and you want to know which you're building *before*
you build it.

### Gate 6 — Variance and ruin

Expectancy tells you the mean; it says nothing about whether you survive to
collect it. You need the distribution: hit rate, worst-case drawdown, and
whether losses correlate. **On prediction markets, correlation is the trap** —
one news event resolves hundreds of markets simultaneously, so "diversified
across 4,000 markets" can be one bet wearing a disguise.

Then size with fractional Kelly (quarter-Kelly is the usual professional
compromise), because full Kelly assumes you know your edge exactly, and you
don't.

### Gate 7 — Tail and structural risk

What kills you that isn't price? Here: oracle failure, platform failure,
regulatory action, stuck capital, smart-contract risk.

### Gate 8 — Decay and competition

Who else is doing this, and what happens when they scale? Is the venue
hostile to it? An edge the exchange is actively engineering against has a
known expiry date, whatever the backtest says.

### Gate 9 — Only now: build, paper trade, measure against prediction

Paper trade until you have a meaningful sample of live signals, then compare
realised against predicted. The comparison is the point — if realised
materially undershoots predicted, your cost model is wrong, and deploying
capital just buys the same lesson at a higher price.

---

## Part 2: Applying it to complete-set accumulation

The strategy measured on swisstony: buy one leg of a market cheap, complete
the set before the chance evaporates, hold to resolution where the set pays
exactly $1.

### Gate 1 — Source of edge ✅ PASS

**Structural.** A complete set must be worth exactly $1.00 at resolution.
When the legs are separately available for less, the identity is violated.
Counterparty: someone with directional urgency on one leg who doesn't care
that the other side has drifted. That's a real, nameable reason for them to
be on the other side.

### Gate 2 — Magnitude ⚠️ THIN

Measured, 472 two-leg baskets: median entry sum **$0.9900** → a **1¢/share**
gross lock.

But size-weighted across all fills the same baskets median **$1.0002**.
Opening fills are good; follow-on fills are worse. **Take the thinner
number as the honest one** — roughly 0 to 1¢/share.

### Gate 3 — Net expectancy ❌ **THIS IS THE GATE IT FAILS**

Measured from their own open positions: **entry fees of $198 on a $21,388
cost basis = 0.92% of capital deployed.**

Against a gross edge of ~1.01% ($0.99 → $1.00), that leaves roughly
**0.1%**, and that's before slippage or any missed second leg.

> **The fee consumes essentially the entire structural edge.**

This is the single most important number in this repo, and it is measured,
not modelled. It also explains why their mean entry price is 0.521: at the
peak of the `p(1−p)` fee curve, they're paying the maximum possible fee. A
strategy that lives at mid prices and crosses the spread 76% of the time is
paying the worst fee available on the venue.

**Conclusion: this does not work as a taker strategy at mid prices.** For it
to clear, at least one of:
- One leg must be a **maker** fill (zero fee), roughly halving the cost
- Trade in **fee-free categories** (geopolitics, world events)
- Trade away from 0.50, where the fee curve collapses

### Gate 4 — Capital velocity ❌ **FAILS WORSE THAN EXPECTED**

I expected sports to recycle capital in days. Measured across 139 open
positions:

| | days to resolution |
|---|---|
| p25 | **−54** |
| median | **−36** |
| p75 | +16 |

**Negative.** The median open position is **36 days past its stated
resolution date and still unresolved.** 

This is the "zombie position" effect the whale study described, and it is
worse than a bookkeeping quirk — it's a capital-efficiency disaster. Money
committed to a 1% lock that should free up in 3 days, but sits stuck for 40+,
collapses the annualised return by an order of magnitude. And it's silent:
the position doesn't show as a loss, it just never comes back.

**Caveat, stated plainly:** open positions are survivorship-biased. The clean
winners resolved and were redeemed; what remains is disproportionately the
problem children. The true average is better than −36 days. But the tail is
real and it is long, and a strategy whose returns depend on fast recycling
must model it.

### Gate 5 — Capacity ⚠️ LOW

Median fill **$12**. Median trade size is the tell: they're taking whatever
is available at the good price, which means the good price has almost no
depth. Their $5.88M of 4-day volume comes from 40,000 fills, not from size.

This scales by **frequency, not by size** — which means it's an
infrastructure problem, and infrastructure is exactly where a Python REST bot
is weakest.

### Gate 6 — Variance ✅ FAVOURABLE (the genuinely good news)

A complete set pays $1 **regardless of which way the market resolves.** Once
both legs are held, directional risk is gone. Hit rate approaches 100% on
completed sets; the real risk isn't losing the bet, it's failing to complete
the second leg and being left naked.

**So the risk to manage is execution risk, not market risk** — and that's a
much more tractable problem. It also means correlation across markets, which
is normally the killer here, largely doesn't apply.

### Gate 7 — Tail risk ⚠️ MIXED, with one important insight

**UMA oracle failure is real.** Documented cases include a governance attack
resolving a Ukraine minerals market to "Yes" with no agreement reached,
paying out $7M on a false resolution, and a $60M+ dispute in which Polymarket
itself confirmed UMA reached the wrong outcome and Yes-holders went to zero.
A whale voting 25% of a dispute round can simply overrule the truth.

**But — and this matters — a complete-set holder is structurally immune to
resolution *direction*.** You hold both sides; whichever way it resolves, you
collect $1. Oracle manipulation destroys *directional* traders. It does not
touch a hedged set.

What does still hurt you: markets **voided** or refunded unusually, and
**capital frozen** through a long dispute (which compounds Gate 4).

So the tail risk here is milder than for any directional strategy on this
venue. That's a genuine point in this strategy's favour.

### Gate 8 — Decay ❌ HOSTILE VENUE

Polymarket has already deployed dynamic taker fees **explicitly to kill
latency arbitrage**, reaching ~3.15% on a 50¢ contract on short-term crypto
markets — the company's stated intent being to exceed typical arbitrage
margin. Sports is 42% of volume and the obvious next target.

You would be building on a strategy whose economics the venue has publicly
committed to destroying, using the exact mechanism (fees at mid prices) that
already fails Gate 3.

---

## Verdict

**Do not deploy capital on this.** It fails Gate 3 on measured numbers and
Gate 4 badly, in a venue actively engineering against it.

That is not a pessimistic reading of thin data — it's arithmetic on fees
pulled from real fills.

**But it fails in a specific, addressable way**, and that's worth more than a
vague "no". Gates 1, 6 and 7 pass, and pass well: the edge source is real,
the variance profile is excellent, and it's structurally immune to this
venue's worst tail risk. Only the *cost side* fails.

So the strategy isn't wrong. **The execution posture is wrong.** Everything
hinges on eliminating the fee, which means the same conclusion the fee
arithmetic pointed at from the very beginning: **be the maker, not the taker.**

The version worth testing:

| Their version | Ours |
|---|---|
| 76% taker | **Maker on at least one leg** |
| Mean entry 0.521 (max fee) | **Away from 0.50, or fee-free categories** |
| Any resolution horizon | **Only markets resolving inside N days** |
| Speed-scaled | **Selectivity-scaled** |

That is a *narrower* strategy with far fewer opportunities. That's the
correct trade: few good trades beat many break-even ones, and break-even
trades on a venue with fees are losing trades.

---

## What I'd do next, in order

1. **Measure which leg is the maker fill.** Decidable from data already
   pulled. If the cheap leg is reliably a maker fill, the fee halves and Gate
   3 may pass. If both legs are taker, this is dead and we stop — one query.
2. **Re-run the basket analysis restricted to fee-free categories and to
   prices outside 0.35–0.65.** If the edge survives there, that's the
   tradeable subset. Also cheap.
3. **Measure true time-to-resolution on *closed* positions**, not open ones,
   to strip the survivorship bias out of Gate 4.
4. Only if 1–3 pass: paper trade with the existing harness, and compare
   realised fills against predicted. Do not skip this.
5. Only if 4 matches prediction: deploy at quarter-Kelly of a deliberately
   small bankroll.

Steps 1–3 cost an hour and can kill the strategy. That is the whole point of
the ordering.
