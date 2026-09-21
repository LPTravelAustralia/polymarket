# polybot

A maker-side Polymarket trading bot, plus a toolkit for profiling the wallets
that actually make money — so strategy decisions come from measured behaviour
rather than from leaderboard screenshots.

```bash
pip install -e ".[dev]"
cp .env.example .env

polybot economics --price 0.5      # why the strategy is shaped the way it is
polybot research --top 5           # profile the top wallets (needs network)
polybot markets --limit 20         # what the bot would quote
polybot run --dry-run --cycles 5   # the quoting loop, sending nothing
```

**The intended order of operations**, because the bot is not supposed to be
switched on first:

```bash
polybot record --duration 86400 --odds      # 1. collect a day of books + odds
polybot calibrate --data data/<session>     # 2. measure adverse selection
polybot backtest --data data/<session>      # 3. replay the strategy over it
polybot run --sports --dry-run              # 4. quote on a real model, no money
```

Step 2 replaces the single most dangerous default in the config with a
measurement. Step 1 is time-critical in a way the others are not: Polymarket
serves no deep book history and odds APIs sell no useful archive, so the
dataset you will eventually need is the one you start recording today.

---

## What the research actually says

### 1. Winning on Polymarket is extremely concentrated

Roughly 84% of wallets lose money. Depending on the study, somewhere between
0.5% and 1% of wallets capture about half of all profit. This is not a market
where a median participant with a decent idea does fine — it is one where a
small group with better pricing, better execution and better cost discipline
takes the pool.

### 2. The single most predictive trait is maker vs taker

The most useful finding, and the one the whole bot is built on, comes from
academic work on Polymarket order flow (an LBS/Yale paper, and an SSRN study
by Akey, Grégoire, Harvie and Martineau):

> Successful traders **provide** liquidity using limit orders. Unsuccessful
> traders **take** liquidity using market orders.

That is not a personality difference. It is arithmetic, which brings us to:

### 3. Fees are the mechanism

Polymarket's 2026 taker fee is:

```
fee = shares × rate × p × (1 − p)
```

A bell curve peaking at p = 0.50. Cross-checked against published examples:
100 shares at 0.50 costs $1.00 at a 4% rate and $1.75 at 7% — which matches
the quoted "$1.00–$1.75 per 100 shares" exactly.

What that means in practice, at mid prices with a 5% rate:

| | Cost |
|---|---|
| Taker, one way | 1.25¢/share |
| Taker round trip | **2.5¢/share — 5% of a 50¢ position** |
| Maker | **$0, plus 15–25% of the taker fee pool as rebate** |

So a taker needs more than 2.5¢ of genuine edge per round trip just to break
even. Almost nobody has that repeatably. A maker starts at zero and gets paid
to be there. "Makers win, takers lose" is largely this table.

Two corollaries the bot exploits:

- **The tails are cheap.** The `p(1−p)` term means a trade at 0.95 costs about
  a fifth of one at 0.50. Tail mispricing is disproportionately where the
  fee-adjusted money is — which is also why the devig method matters (below).
- **Some categories are free.** Geopolitics and world events carry no taker
  fee, so a mispricing that isn't tradeable in crypto is tradeable there.
  `find_complement_arb` picks this up automatically from the live rate.

### 4. The top accounts are not doing one thing — and only one is copyable

Public reporting on the highest-PnL accounts describes three unrelated
strategies:

| Account | Profit | Shape | Copyable? |
|---|---|---|---|
| **Theo4** (and Fredi9999, PrincessCaro, Michie, RepTrump1 — one operator, "Théo") | ~$22M, ~100% politics | ~18 positions, >$1M average. Few trades, huge size, deep off-platform research | **No** |
| **swisstony** | ~$7.8M, ~97% sports | 150k–200k positions, ~$45 average. Automated pricing slightly better than consensus | **Yes** |
| **kch123 / others** | varies | mixed | depends |

This is the most important finding for a bot project, and it is easy to get
backwards. **Theo4's edge is not reproducible by software.** It was private
research plus the balance sheet to sit through drawdown. Copying those fills
is worse than useless: by the time a $1M position is visible on-chain, their
own buying has already moved the price, so you buy the top of their move and
carry their risk without their information.

**swisstony's edge is exactly what a bot is for.** Tiny edge per trade, no
opinion about any individual game, compounded across a hundred thousand fills,
made viable by never paying a taker fee. That is the pattern this bot
implements.

Note the win rate: one profile puts swisstony at **53.6%** correct. That is
the whole point. A small, persistent, correctly-priced edge applied at volume,
not brilliance on any single market.

### 5. Classic latency arbitrage is dead

The median arbitrage window has compressed from ~12.3s in 2024 to ~2.7s, with
roughly 73% of arbitrage profit going to sub-100ms bots. A Python process
polling REST will mostly see opportunities that are already gone.

So the arbitrage module here is deliberately **opportunistic and
detection-only** — it logs rather than auto-fires. The checks are nearly free,
and genuinely wide mispricings do still appear in illiquid multi-outcome
markets the fast bots ignore. But it is not the strategy, and multi-leg
execution where one leg misses isn't arbitrage, it's an accidental naked
position.

---

## What the bot does

Built to reproduce the **systematic maker** archetype:

- **Quotes both sides passively** around a fair value, never crossing. Every
  order is `post_only`; a "maker" order that crosses is a taker order paying
  the taker fee, silently converting positive edge into negative.
- **Requires explicit edge** before quoting: `fair − bid − adverse_selection ≥
  min_edge`. If the required band doesn't fit inside the book, it declines.
- **Quotes no tighter than its own uncertainty.** Quoting inside your error
  bar is how a maker gets picked off.
- **Skews on inventory** to bleed positions back toward flat.
- **Does not short.** Selling a token you don't own requires minting a
  complete set first — a different strategy with different risk.
- **Refuses markets near resolution**, where the model is worst and adverse
  selection is highest.
- **Holds queue position.** Orders are only replaced when the price has moved
  past a threshold, because re-posting every cycle surrenders the queue
  priority that is most of the value of quoting passively.

### The edge: the sports model

`MicropriceModel` is the default and it has **no informational edge** — it
gives you spread capture and rebates, not swisstony's edge. It exists to
verify plumbing.

`SportsFairValue` is the real one: a devigged consensus of sportsbook odds,
matched to Polymarket markets. `polybot run --sports` wires it up, or:

```python
from polybot.models import SportsFairValue, TheOddsAPI
from polybot.strategy.fair_value import ExternalModel

sports = SportsFairValue(TheOddsAPI(), sport_keys=["basketball_nba"])
sports.register(markets)
runner = BotRunner(settings, fair_value_model=ExternalModel(sports.probability_fn))
```

Three details it gets right that are commonly got wrong:

- **Devig each book, then average** — not the reverse. Averaging raw implied
  probabilities across books mixes together different margins and produces a
  number that is no book's actual opinion.
- **`devig_power`, not proportional.** Proportional devigging leaves longshots
  overpriced, and the `p(1−p)` fee curve makes the tails the cheapest place to
  trade — so that is exactly where you cannot afford the error.
- **Sharp books weighted higher.** Pinnacle moves first and retail follows;
  weighting them equally throws away the signal.

Matching is the dangerous part, so it is paranoid: both outcomes must map to
distinct teams, the match must beat the runner-up by a margin (a repeated
fixture is refused rather than guessed), event time must be near market
resolution, and anything below the confidence floor returns nothing. It also
**stops quoting 15 minutes before tip-off**, because pre-game odds are
worthless in-play and this has no live feed.

### Proving it before trading it

`polybot backtest` replays the *real* `MakerStrategy` — not a reimplementation
— over recorded books. The fill model is the part that decides whether a
backtest tells the truth, so it models **queue position** explicitly: you join
the back of the queue at your price, and traded volume consumes that queue
before it consumes you. The naive "price touched my bid so I filled" shortcut
invents most of a market-making strategy's apparent profit, and invents it
precisely in the cases where the price then moved your way.

It also models **price-through** fills — the market running clean past your
level — because that is the fill you did not want, and ignoring it flatters
the strategy enormously.

`polybot.backtest.scoring` answers the question that decides everything:
does the model beat the market price on resolved markets? A Brier skill score
at or below zero means no edge, and the tool says so in those words rather
than finding something encouraging to report. It also refuses to call
anything conclusive below 200 resolved markets, since prediction-market
outcomes are correlated and the effective sample is smaller than the count.

---

## The research toolkit

`polybot research --top 5` pulls the top wallets, walks each one's full public
trade history, and produces a behavioural fingerprint. Design notes that
matter:

- **Maker/taker ratio is recovered by differencing.** The Data API has no
  maker/taker field, so the profiler queries `/trades` with `takerOnly=true`
  and again with `takerOnly=false`, and differences the counts. This is the
  most important statistic and it is not directly exposed.
- **Income is decomposed before it is judged.** `REWARD` events (liquidity
  mining) and `SPLIT`/`MERGE` events (structural arb) look like trading profit
  on a leaderboard but are not. A wallet whose income is really a subsidy is
  classified `REWARD_FARMER`, not `SYSTEMATIC_MAKER` — because subsidies get
  cut, and a strategy that depends on one dies with it.
- **Leaderboard failure is not fatal.** `/leaderboard` isn't part of the
  documented v2 surface and has moved before, so there's a bottom-up fallback
  that discovers whales from the holder lists of high-volume markets. Harder
  to game, too: a wallet that is a top holder across 40 resolved markets is
  doing something systematic whatever the leaderboard says.

Each wallet is classified into one of: `CONVICTION_WHALE` (not replicable),
`SYSTEMATIC_MAKER` (the template), `STRUCTURAL_ARB`, `REWARD_FARMER`,
`MOMENTUM_TAKER` (flagged: do not copy without proof of edge), or
`UNCLASSIFIED`. Each verdict comes with its reasoning and an explicit
**bot translation** — what, if anything, to actually build from it.

---

## Layout

```
src/polybot/
├── economics.py           Fee model. Everything routes through here.
├── config.py              Settings and risk limits (conservative by default)
├── runner.py              The trading loop
├── cli.py                 Command line
├── clients/
│   ├── http.py            Retry, backoff, token-bucket rate limiting
│   ├── gamma.py           Market metadata and selection
│   ├── data_api.py        Wallet history, positions, leaderboard
│   └── clob.py            Order books and order placement
├── research/
│   ├── fingerprint.py     Behavioural metrics + archetype classification
│   ├── profiler.py        Fetch orchestration
│   └── report.py          Markdown rendering
├── strategy/
│   ├── fair_value.py      Fair-value models and devigging
│   ├── maker.py           The quoting strategy
│   └── structural.py      Complement and neg-risk arbitrage detection
├── models/
│   ├── odds_feed.py       Sportsbook odds, devigged to a consensus
│   ├── matching.py        Polymarket market <-> event matching (paranoid)
│   └── sports.py          The sports fair-value model
├── marketdata/
│   ├── recorder.py        Collect books, trades and odds to disk
│   └── store.py           Gzipped JSONL snapshot format
├── simulation/
│   ├── fills.py           Queue-aware fill model
│   └── markout.py         Adverse-selection measurement + calibration
├── backtest/
│   ├── engine.py          Replay the live strategy over recordings
│   └── scoring.py         Brier / log loss / calibration vs the market
└── execution/
    ├── risk.py            Limits and kill switch
    └── order_manager.py   Order lifecycle and reconciliation
```

Risk gating is deliberately separate from strategy: a bug in a fair-value
model should cost a bounded amount of money, and the only way to guarantee
that is for the bounding code to know nothing about the model.

---

## Safety

Defaults are timid on purpose — `$250` per market, `$2,500` total, `$250`
daily loss limit, dry-run mode. Three modes: `dry_run` (computes, sends
nothing), `paper`, `live`. Live mode requires an interactive confirmation.
An unrecognised `POLYBOT_MODE` falls back to `dry_run`, so a typo can never
become live trading.

Before going live: run in `dry_run` for a few days and read the skip reasons.
If the bot almost never quotes, your model isn't better than the book — which
is information worth having for free.

---

## Honest limitations

- **No live data was pulled when this was built.** The environment it was
  written in blocks all `polymarket.com` domains at the network proxy, so the
  research toolkit is written and unit-tested but has **not been run against
  the live API**. Run `polybot research --top 5` from an unrestricted machine
  first; expect to fix response-shape details, particularly on `/leaderboard`.
- **The trader profiles above are secondhand.** Profit figures and strategy
  descriptions for Theo4, swisstony and others come from crypto media and
  analytics sites, not from data pulled here. The structural findings (fee
  formula, maker/taker result, profit concentration) are better sourced than
  the per-account numbers. Treat the per-account figures as directional and
  re-derive them with the toolkit.
- **Category fee rates are a fallback only.** They have changed repeatedly.
  The bot fetches the authoritative per-token rate from the CLOB `/fee-rate`
  endpoint at runtime and only falls back to the hardcoded table on failure.
- **`adverse_selection_per_share` ships as a placeholder.** The default 0.4¢
  is a guess. `polybot calibrate` replaces it with a measurement — run that
  before trusting any PnL projection. If it is wrong low, the bot quotes too
  tightly and bleeds slowly enough to look like variance for weeks.
- **Rebates are not credited at decision time.** They're paid pro-rata from a
  pool days later, and treating them as certain income is how market makers
  talk themselves into negative-edge quotes. `expected_maker_rebate()` exists
  for accounting separately.
- **The fill simulator ignores your own market impact.** It replays a book
  recorded without your orders in it, so it cannot model other participants
  reacting to your quotes. This matters more the larger you size.
- **The trade tape from a REST recorder is incomplete.** A burst of trades
  between polls is missed. That makes the simulator *more* pessimistic (the
  queue drains slower than it really did), which is the safe direction, but
  it is a real limitation. A websocket feed would fix it.
- **The sports model is not backtested yet.** `polybot record --odds` now
  captures odds alongside books so this becomes possible, but joining
  recorded odds to recorded books and scoring against resolutions is not
  built. Until then, `scoring.py` is the tool and you supply the
  observations.
- **Live/in-play markets are out of scope.** The sports model stops quoting
  before kickoff by design.

## Tests

```bash
python -m pytest        # 191 tests, no network required
```

The fee model is tested against Polymarket's published worked examples rather
than against itself, and `min_profitable_taker_price` is verified by
substituting its output back into the net-edge equation rather than trusting
the algebra.

## Sources

- [Who Wins and Who Loses In Prediction Markets? (Akey, Grégoire, Harvie, Martineau, SSRN)](https://papers.ssrn.com/sol3/Delivery.cfm/6443103.pdf?abstractid=6443103&mirid=1)
- [A tiny group is winning on Polymarket (CoinDesk)](https://www.coindesk.com/markets/2026/04/29/a-tiny-group-is-winning-on-polymarket-as-under-1-of-wallets-take-half-the-profits)
- [Maker Rebates Program (Polymarket docs)](https://docs.polymarket.com/programs/maker-rebates) · [Trading Fees (Polymarket Help)](https://help.polymarket.com/en/articles/13364478-trading-fees)
- [Top Polymarket traders use three distinct strategies (KuCoin)](https://www.kucoin.com/news/flash/top-polymarket-traders-use-three-distinct-strategies-to-earn-millions) · [Odaily](https://www.odaily.news/en/post/5210641)
- [The fredi9999 account (Rajiv Sethi)](https://rajivsethi.substack.com/p/the-fredi9999-account)
- [Arbitrage Analysis in Polymarket NBA Markets (arXiv)](https://arxiv.org/pdf/2605.00864)
- [Polymarket Data API reference](https://data-api.polymarket.com/v2/docs) · [agent-skills/market-data.md](https://github.com/Polymarket/agent-skills/blob/main/market-data.md)
