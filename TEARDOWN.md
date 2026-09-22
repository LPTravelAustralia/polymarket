# Top Polymarket accounts: what they actually do

The question this answers: *of the people making serious money on Polymarket,
what is the mechanism, and which mechanisms can we reproduce?*

**Read the confidence markers.** Polymarket's APIs are blocked from the
environment this was compiled in, so none of the per-account numbers below
were pulled directly. They come from crypto media, analytics sites and
on-chain write-ups, which contradict each other on specifics. Every claim is
tagged:

- **[MEASURED]** — arithmetic or primary documentation, verified here
- **[REPORTED]** — a specific figure from published analysis, plausible but unverified
- **[INFERRED]** — my reasoning from the above

`polybot research --top 5` re-derives all of it from the chain. Run it. This
document is the starting hypothesis, not the finding.

---

## The headline correction

An earlier draft of this repo's README described swisstony — the largest
account — as running "automated models pricing sports slightly better than
consensus." **That appears to be wrong, and the real answer matters a lot
more.**

> The algorithm capitalizes on the time lag between live sports events and
> their broadcast, which can range from 15 to 40 seconds. By receiving
> real-time data directly from stadiums via API, the bot executes trades
> before the market adjusts to the actual game events. **[REPORTED]**

That is not a modelling edge. It is an **information and latency edge**: you
know the goal was scored, and the market is still pricing off a delayed
broadcast. And it means the largest account is a **taker**, crossing the
spread to hit stale quotes — the opposite posture from the bot in this repo.

This is reconcilable with the academic "makers win, takers lose" result, and
the reconciliation is the single most useful idea here:

> Taking liquidity is unprofitable **unless you have information the market
> does not.** A round trip at mid prices costs ~2.5¢/share **[MEASURED]**.
> Ordinary momentum or news-reaction trading does not clear that. A goal in a
> tied match moves the price 10–30¢ **[INFERRED]**, which dwarfs it entirely.

So the fee is not what separates makers from takers. It is what separates
takers *with* an information edge from takers without one. Almost everyone is
in the second group.

---

## MEASURED: swisstony, pulled from the chain

The rest of this document was written from published reporting. **This
section is different — it is measured.** Pulled 2026-09-21 via
`polybot profile`, 40,000 fills over 4 days plus a 10,000-fill detailed
sample.

| Metric | Value |
|---|---|
| Fills | 40,000 in **4 days**, across 4,426 markets |
| Volume | $5.88M over those 4 days |
| Posture | **75.6% taker / 24.4% maker** |
| Rate | ~373 fills/hour; **28.6% of consecutive fills land in the same second**; median gap 2s |
| Size | median **$12**, mean $147, max $48,572 |
| Side mix | **100% BUY. Zero sells in 10,000 consecutive fills.** |
| Mean entry price | 0.521 — the exact point where the fee curve peaks |
| Concentration | HHI 0.004 — extraordinarily diversified |
| Markets | Obscure ones: ITF women's tennis, Korean league O/U, Saudi league, exact-score markets |

### What is established

1. **It is a machine, and a fast one.** 373 fills/hour with 28.6% of fills
   sharing a timestamp second is not a person, and not a slow model either.
2. **It is predominantly a taker.** 75.6% aggressive. That refutes the
   "systematic maker" reading this repo originally shipped, and it means the
   account is paying the taker fee on three quarters of its entries —
   at a mean entry price of 0.521, i.e. the most expensive point on the fee
   curve. It is doing that *deliberately*, which means the edge per trade
   must comfortably exceed the fee.
3. **It never sells.** Zero SELL fills in 10,000. Positions are not exited;
   they are held to resolution.
4. **It frequently owns more than one outcome of the same market** — 43.2% of
   markets traded. Example: bought both Lea Boskovic ($131.92) *and* Tahlia
   Kokkinis ($372.58) in the same tennis match.

### What is NOT established

I tested whether the multi-outcome buying is complete-set arbitrage — buying
all outcomes for under $1 and collecting the difference at resolution. **The
data does not support that cleanly:**

- 472 multi-outcome baskets, of which 48.9% sum to under $1.00
- **Median basket sums to $1.0002**, mean $1.0296

A median of essentially exactly $1.00 is not arbitrage. It is break-even on
the matched portion. Some baskets are spectacular ($0.3558 on a Saudi league
O/U, a 64c/share lock) and some are badly underwater ($1.77), so the spread
is wide and the centre is fair value.

### The leg-ordering test — and what it refuted

I proposed that they exit by *hedging rather than selling*: take a
directional position, and when it moves favourably, buy the opposing outcome
to lock it in. That theory makes a specific prediction — **waiting longer
before the second leg should produce better baskets**, because you are
waiting for the move.

Ran it on 472 two-leg baskets, using the first fill on each leg as the entry.
**The prediction fails, in the opposite direction:**

| Group | n | median gap | median sum | share under $1 |
|---|---|---|---|---|
| Simultaneous (≤2s) | 4 | — | $0.9900 | 100% |
| Sequential (>2s) | 468 | 1,093s | $0.9900 | 59.4% |
| — fastest quartile | 117 | **141s** | $0.9900 | **72.6%** |
| — slowest quartile | 117 | **5,738s** | $1.0000 | **53.0%** |

Waiting longer makes baskets **worse**, not better. So hedge-after-a-move is
refuted. So is simultaneous arbitrage — only 4 of 472 baskets complete inside
two seconds.

### What actually fits

**Opportunistic complete-set accumulation, with a decaying edge.**

Buy one leg when it is cheap. Then try to complete the set — buy the opposing
outcome — before the opportunity evaporates. Complete it fast and you own a
complete set for about **$0.99**, which pays $1.00 at resolution: roughly a
**1¢/share lock**. Take too long and the price moves against you and you end
up at fair value or worse.

That is why speed matters here, and it is the most important number in this
document: **completing within ~2 minutes succeeds 72.6% of the time; taking
~95 minutes drops that to 53.0%** — barely better than a coin flip.

One honest wrinkle. First-fill entry prices median **$0.9900**, but
size-weighted across *all* fills the same baskets median **$1.0002**. Their
opening fills are good and their follow-on fills are worse — they add to legs
at deteriorating prices. So the 1¢ headline applies to the entry, not to the
whole position, and the realised edge is thinner than $0.99 suggests.

**Why this is the useful finding:** the relevant timescale is **minutes, not
milliseconds**. That is within reach of a Python bot over REST. It is a
completely different proposition from racing a colocated stadium feed.

**What it needs to be real:** the 1¢/share lock is *gross*. Three quarters of
these fills are taker fills, and at their mean entry of 0.521 the taker fee
is roughly 0.75–1.25¢/share depending on category. **That can consume the
entire edge.** Whether this is profitable therefore hinges on which leg is
the maker fill and in which categories — which is the next thing to measure,
and is measurable from this same data.

### What this changes for our bot

- The **maker-only** design does not reproduce this account. Stated plainly.
- The **"never sell, hedge to close"** exit is reproducible *today*, needs no
  data feed, and is probably the single most valuable transferable idea here.
  It avoids a second taker fee and sidesteps thin exit liquidity.
- The entry edge still requires either a latency advantage or a better model.
  That part is not free.

---

## The accounts

Sources disagree on figures, sometimes wildly — swisstony's lifetime profit is
variously reported at $7.8M, $22.7M and $23.6M. Treat magnitudes as
directional and ordering as approximate.

### 1. swisstony — `0x204f72f35326db932158cba6adff0b9a1da95e14`

| | |
|---|---|
| Profit | ~$22.7M–$23.6M **[REPORTED]** |
| Volume | ~$1.75B across ~157,000 markets **[REPORTED]** |
| Avg profit/trade | ~$156 on one sampled subset **[REPORTED]** |
| Category | ~97% sports **[REPORTED]** |
| Mechanism | Broadcast-lag arbitrage + basket/hedge construction **[REPORTED]** |

Also described as "ant moving" style — frequently **buying all outcomes of an
event**, i.e. complete-set and hedge construction, not just directional bets.
Largest single win ~$1.2M **[REPORTED]**.

**Replicable?** Only with a real-time sports data feed and low-latency
execution. See "What Tier 1 costs" below. The *statistical* half of this
account (hedge construction, basket arb) is reproducible without a feed; the
*latency* half is not.

### 2. Théo — Theo4, Fredi9999, PrincessCaro, Michie, RepTrump1

One operator behind ~11 linked wallets, five of which hold top-20 all-time
positions **[REPORTED]**. Theo4 alone: ~$22M from **~18 positions**, ~100%
political, averaging over $1M each **[REPORTED]**.

**Mechanism:** off-platform research. Théo commissioned private "neighbour
polling" during the 2024 US election, believing public polls understated
Trump support **[REPORTED]**.

**Replicable? No — and copying is actively harmful.** By the time a $1M fill
is visible on-chain, their own buying has already moved the price. You buy
the top of their move and carry their risk without their information. This is
not a bot strategy at all; it is a research operation with a balance sheet.

### 3. The $8M lag bot (unnamed)

~$8M in two months **[REPORTED]**. Places >$500k/day, average profit per trade
$100k–$200k **[REPORTED]**. Advantage explicitly attributed to **proximity to
Polymarket's servers** **[REPORTED]**.

Same mechanism as swisstony, executed at larger size. Notable because it
confirms the edge is infrastructure, not insight — the write-ups are explicit
that it makes no predictions and does no market analysis.

### 4. kch123

~$11.78M lifetime **[REPORTED]**. Mechanism not documented in anything I could
reach. **Unknown — profile before drawing conclusions.**

### 5. SeriouslySirius (and the whale cohort generally)

Included not for size but for the most useful finding in the whole teardown.
PANews/BlockBeats analysed **27,000 transactions across the top 10 whales**
and concluded **[REPORTED]**:

- Headline win rates are **inflated by unclosed "zombie" positions** — losing
  bets left open so they never count as losses. SeriouslySirius's *true* win
  rate is ~53.3%, not the far higher number the leaderboard shows.
- **Copy trading does not work**, as a general finding across the cohort.
- Hedging arbitrage, done naively, **loses money**.
- Most "whales" are "surviving gamblers or hardworking day labourers" — the
  real edge sits with a small number of algorithmic operators.

The 53.3% figure is the number to internalise. It is almost exactly
swisstony's reported 53.6%. **Nobody is winning by being right often. They are
winning by being slightly right, very cheaply, very many times.**

This is also why the profiler in this repo computes win rate only over
*decided* positions and reports open inventory separately — the zombie-order
distortion is real and it is the single easiest way to fool yourself.

---

## The three mechanisms, ranked by barrier

| Tier | Mechanism | Edge source | Barrier | Our status |
|---|---|---|---|---|
| **1** | Latency / broadcast-lag arb | Real-time data feed vs delayed market | Paid sports feed, colocation, sub-100ms execution | **Not built** |
| **2** | Maker quoting with a model | Better fair value + zero fees + rebates | An odds feed and patience | **Built** |
| **3** | Momentum / news taking | None | None | **Deliberately not built** |

Tier 3 is what the previous bot in this repo did (`MomentumAgent`,
`AIAgent`, a news monitor). It is the pattern the academic work identifies as
the losing one, and the fee arithmetic explains why **[MEASURED]**.

### What Tier 1 costs

Before anyone gets excited about the $8M number:

- **A real-time sports data feed.** Sportradar, Genius Sports or Opta.
  Enterprise contracts, not self-serve APIs. Pricing is not public; budget in
  the tens of thousands per year at minimum **[INFERRED]**.
- **Low-latency execution**, ideally colocated near Polymarket's
  infrastructure. The $8M bot's advantage is explicitly attributed to server
  proximity **[REPORTED]**.
- **Python is probably too slow** for the fastest tier of this. Published
  work puts ~73% of arbitrage profit with sub-100ms systems **[REPORTED]**.

### And the window is closing

Polymarket has deployed **dynamic taker fees explicitly to kill latency
arbitrage** **[REPORTED]**. On 15-minute crypto markets the fee now scales
with proximity to 50/50 — reaching ~3.15% on a 50¢ contract, which the
company states exceeds typical arbitrage margin and makes the strategy
unprofitable at scale.

That is crypto markets today. Sports is 42% of Polymarket volume
**[REPORTED]** and is the obvious next target for the same treatment. Building
a business on Tier 1 means building on something the venue is actively
engineering against.

---

## What this means for our bot

The bot in this repo implements **Tier 2**, and that remains the right call
for us — but the choice should be made with open eyes rather than by default:

**For Tier 2:** no special data contracts, no colocation, no latency race.
It is the strategy that survives Polymarket's fee engineering, because it is
the strategy Polymarket is *subsidising* through maker rebates. The ceiling is
lower than $22M.

**Against:** it is not what the top account does.

**The realistic hybrid**, and my recommendation: run Tier 2 as the base, and
take the *non-latency* half of swisstony's playbook — hedge and basket
construction across correlated sports markets, which needs no feed. The
structural arb detector in `strategy/structural.py` is the beginning of that.
Revisit Tier 1 only if a sports data feed lands in budget, and price in that
the venue is hostile to it.

**What I would not do:** copy-trade any of these wallets. The whale study
found it ineffective **[REPORTED]**, and the mechanism is clear — with Théo
you are late to a move he caused; with swisstony you are copying fills whose
edge was a 20-second information advantage that expired before the trade was
visible to you.

---

## Verifying all of this

Everything above is secondhand. The toolkit exists to replace it with
measurement:

```bash
polybot research --top 5          # profile the current leaderboard
polybot profile 0x204f72f35326db932158cba6adff0b9a1da95e14   # swisstony
```

What to look for, and what each answer would mean:

| Signal | If true | Implication |
|---|---|---|
| `maker_ratio` < 0.35 on swisstony | Confirms taker posture | Latency-arb thesis supported |
| Median hold measured in seconds/minutes | In-and-out around events | Latency-arb thesis supported |
| High `structural_events` (SPLIT/MERGE) | Basket construction | The replicable half, worth copying |
| High `reward_usd` | Income is partly subsidy | Not a pure trading edge |
| Win rate ~53% on decided positions | Matches the reported figure | Thin-edge-at-volume confirmed |

If swisstony comes back as a *maker* with long holds, the broadcast-lag story
is wrong and the original "better model" reading was right. That single
measurement settles it, and it takes one command.

---

## Sources

Leaderboard and account figures: [Polycopy](https://polycopy.app/best-polymarket-traders),
[Polymarket Analytics](https://polymarketanalytics.com/traders/0x204f72f35326db932158cba6adff0b9a1da95e14),
[Deadspin](https://deadspin.com/prediction-markets/trending/the-most-profitable-traders-ever-on-polymarket/).

Mechanism reporting: [Phemex on broadcast-lag arbitrage](https://phemex.com/news/article/algorithm-exploits-broadcast-lag-to-turn-5-into-37m-on-polymarket-53969),
[Phemex on the $8M lag bot](https://phemex.com/news/article/sports-bot-earns-8-million-on-polymarket-by-exploiting-time-lag-55871),
[KuCoin on the three strategies](https://www.kucoin.com/news/flash/top-polymarket-traders-use-three-distinct-strategies-to-earn-millions),
[Rajiv Sethi on fredi9999](https://rajivsethi.substack.com/p/the-fredi9999-account).

Whale cohort analysis: [PANews](https://www.panewslab.com/en/articles/516262de-6012-4302-bb20-b8805f03f35f),
[BlockBeats](https://m.theblockbeats.info/en/news/60763),
[Gate](https://www.gate.com/learn/articles/inside-polymarkets-top-10-whales-27000-trades-the-illusion-of-smart-money-and-the-real-survival-rules/15440).

Fees and countermeasures: [Finance Magnates on dynamic fees](https://www.financemagnates.com/cryptocurrency/polymarket-introduces-dynamic-fees-to-curb-latency-arbitrage-in-short-term-crypto-markets/),
[Polymarket maker rebates](https://docs.polymarket.com/programs/maker-rebates),
[Polymarket trading fees](https://help.polymarket.com/en/articles/13364478-trading-fees).

Academic: [Akey, Grégoire, Harvie & Martineau (SSRN)](https://papers.ssrn.com/sol3/Delivery.cfm/6443103.pdf?abstractid=6443103&mirid=1),
[CoinDesk on profit concentration](https://www.coindesk.com/markets/2026/04/29/a-tiny-group-is-winning-on-polymarket-as-under-1-of-wallets-take-half-the-profits).
