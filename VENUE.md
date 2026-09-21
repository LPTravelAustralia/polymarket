# Should we be on a different venue?

Short answer: **crypto perps, probably Hyperliquid. Not equities.**

The reasoning is not "crypto is hot". It's that the complete-set strategy
failed on exactly two gates — fee drag and capital velocity — and those are
the two dimensions where crypto perps are strongest and equities are closed
to us entirely.

---

## Why crypto, specifically

### It fixes Gate 3 (fees), which is what killed us

| | Cost per round trip |
|---|---|
| **Polymarket (measured, our data)** | **0.92% of capital deployed** |
| Crypto perps taker (OKX/Binance) | 0.05% |
| Crypto perps maker (OKX/Bybit) | **0.02%** |
| MEXC spot maker | **0%** |
| Kraken elite maker ($1B+/mo) | **−0.006% (they pay you)** |

**That is an 18–46× reduction in the cost that destroyed the strategy.**

The 1¢/share structural edge we measured wasn't too small. It was fine. The
fee was too big. Move the same edge to a venue charging 0.02% and it survives
comfortably.

### It fixes Gate 4 (capital velocity), which was worse

Polymarket: median open position sits **36 days past its resolution date**,
capital frozen, earning nothing, not even showing as a loss.

Crypto perps: **positions close instantly, 24/7.** There is no resolution to
wait for. Capital recycles as fast as you can find trades. Gate 4 stops being
a constraint and becomes a non-issue.

### Hyperliquid also preserves the research work

The original ask — reverse-engineer the top accounts — depended on Polymarket
publishing every wallet's trades. Most venues don't. **Hyperliquid does:**
fully on-chain, free, no API key, a public leaderboard returning address, PnL,
ROI and volume, across 1.6M+ tracked wallets.

So `research/fingerprint.py` — the archetype classifier, the maker/taker
measurement, the hold-time and concentration analysis, ~400 lines — points at
a new venue rather than being thrown away. The `polybot research` workflow
survives the move. On a CEX it would not.

---

## Why not equities

Bluntly: **the parts of this codebase that are good are microstructure, and
retail microstructure trading in equities is closed.**

- Market making requires exchange membership and registration. You cannot
  simply post two-sided quotes and collect rebates.
- Retail order flow is sold to wholesalers (PFOF). The flow you'd want to
  interact with never reaches the public book.
- You'd be competing directly with Citadel Securities and Virtu on their home
  ground, with their latency and their rebate tiers.
- Real-time L2 data carries meaningful cost, where crypto venues give it away.

Retail edges in equities are real but they live at a *longer horizon* —
factor exposure, fundamentals, event-driven. None of what we built serves
that. The fill simulator, the markout calibration, the inventory-skewed
quoter, the fee engine: all pointless at a multi-day horizon.

Pivoting to equities means starting over. Pivoting to crypto perps means
swapping the venue adapter.

---

## The honest counterweight

**Lower fees cut both ways.** Polymarket's 0.92% fee was a barrier to entry as
much as a cost — it kept competition out. At 0.02%, everyone can afford to
compete, so edges are correspondingly thinner and disappear faster. Crypto
perps market making is among the most professionalised arenas in trading:
you'd be up against firms with colocation, dedicated connectivity and years of
accumulated microstructure knowledge.

So the move does **not** convert a losing strategy into a winning one by
itself. What it does is remove the two structural blockers, so that *if* we
find an edge, we get to keep it instead of handing it to the venue.

The edge problem is unchanged and remains the hard part. It was always the
hard part.

---

## What actually transfers

Audited by counting venue-specific references per module.

### Portable as-is — zero venue coupling (~1,200 lines)

| Module | Lines | Why it transfers |
|---|---|---|
| `simulation/fills.py` | 190 | Queue-position fill modelling. Every CLOB works this way. **The most valuable asset here.** |
| `simulation/markout.py` | 214 | Adverse-selection measurement is standard market-making practice everywhere. |
| `backtest/engine.py` | 227 | Replay harness driving the live strategy. |
| `backtest/scoring.py` | 162 | Brier/log-loss/calibration — applies to any probabilistic forecast. |
| `execution/risk.py` | 143 | Position tracking, limits, kill switch. |
| `execution/order_manager.py` | 126 | Order lifecycle, requote thresholds, queue preservation. |
| `strategy/maker.py` | 150 | Inventory-skewed two-sided quoting is *the* standard MM approach. |

### Portable with small edits (~970 lines)

`clients/http.py`, `marketdata/store.py`, `marketdata/recorder.py`,
`config.py`, `strategy/structural.py`, `strategy/fair_value.py` — each has
one or two venue references. The recorder and store need a new data source;
the logic is unchanged.

`economics.py` (194) needs its fee *function* swapped — `p(1−p)` is
Polymarket-specific — but the framework around it (net-edge gating,
breakeven, minimum profitable taker price) is exactly what you need on any
venue, and arguably matters more when fees are small enough to be dismissed
carelessly.

### Needs rewriting (~690 lines)

`clients/clob.py`, `clients/data_api.py`, `clients/gamma.py` — venue
adapters, which is precisely the part that *should* be venue-specific.

### Only useful if we keep doing sports (~530 lines)

`models/odds_feed.py`, `models/matching.py`, `models/sports.py`. The
devigging maths stays useful for any sports-betting work, on any venue.

### Roughly half the codebase moves unchanged.

That is not an accident — risk gating was deliberately kept independent of
strategy, and strategy independent of venue, which is the same design choice
that makes the port cheap.

---

## What I'd do

1. **Point `research/fingerprint.py` at Hyperliquid's leaderboard.** Small
   adapter. It answers the original question — *what do the top accounts
   actually do* — on a venue where the answer is also *actionable*, because
   fees and capital velocity don't disqualify the answer before you start.
2. **Re-run the same nine gates** from `STRATEGY.md` on whatever that
   profiling surfaces. The framework doesn't change; only the inputs do.
3. **Do not port the trading bot yet.** Porting it is a week of work and
   we still have no edge. Establish the edge first, then build to it. Building
   first is the mistake that produced the previous bot in this repo.

Funding-rate and basis arbitrage are the obvious first structural candidates
on perps — same shape as complete-set arb (a price identity that must hold),
but with instant capital recycling and 20–45× lower fees.
