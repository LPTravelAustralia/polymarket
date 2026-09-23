# Buy the house's side — and only when it pays

Twelve strategies were measured in this repo and the best of them earned
roughly cash. This document is about two things those measurements missed,
and the monitor built because of them.

1. **Every test asked "can we run this?" None asked "can we buy it?"** The
   conclusion everywhere was that the house wins. On Hyperliquid you can own
   a share of the house, and the funding carry is sold as a token.
2. **Everything was measured in the quietest year in the available history.** The same
   carry that earns cash today paid 17.5% in 2024.

**Current reading (23 Sep 2026): QUIET.** Nothing below pays meaningfully
more than cash right now — including the rate you can lock on Deribit for
three months (4.4%). That is why every strategy looked marginal.

Reproduce with `polybot regime`.

---

## 1. Buying the house: HLP

HLP is Hyperliquid's own vault. It makes markets and takes over liquidated
positions, and anyone can deposit USDC into it. Measured from Hyperliquid's
API, with deposits and withdrawals stripped out (time-weighted; the method
reproduces the protocol's own reported APR over the last month to within a
point):

| Period | Return |
|---|---|
| 2023 | +83.4% |
| 2024 | +79.1% |
| 2025 | +19.0% |
| 2026 to 23 Sep | +7.9% |
| Last 12 months | **+18.3%** |
| Last two quarters | −0.4%, +0.7% — **below cash** |
| Since May 2023 | ×4.2, max drawdown −5.8% at fortnightly resolution |

Over the last twelve months that is roughly ten times what the best
do-it-yourself strategy in this repo earned above cash, with no operation.

**Three things make it much less attractive than that table:**

- **It is paid by crashes.** The fortnight of 1–15 October 2025 alone
  returned +9.7%, and 21 January–4 February 2026 returned +7.0%. Nearly every
  other fortnight in between was flat. HLP earns when leveraged traders are
  liquidated en masse and earns roughly nothing otherwise.
- **Its clean record includes a rescue.** On 26 March 2025 a trader
  manipulated the thin JELLY market and left HLP holding a short with a
  $12–13.5M paper loss. Validators — then mostly controlled by the Hyper
  Foundation — voted within minutes to delist JELLY and settle it at a price
  that turned the loss into a $703k profit. That was a discretionary
  intervention, it drew heavy criticism, delisting has since moved to
  on-chain validator voting, and nothing guarantees it happens again.
- **The big years are gone.** 83% was earned while the vault was small. It
  is now $184M and returns have fallen every year.

And the drawdown figure is a floor: the history is sampled every 14 days, so
anything that happened and recovered inside a fortnight is invisible.

## 2. Buying the carry: sUSDe

Ethena's sUSDe is the funding harvest from `FUNDING.md`, run at $1.3B scale
with better execution than any retail operator, sold as a token. Its yield
is the market's own price for that trade:

| | Mean yield |
|---|---|
| 2024 | **17.5%** (peak month 37.7%) |
| 2025 | 6.5% |
| 2026 to date | **4.1%** — cash |

The professionals running this trade are currently earning what a term
deposit pays. That agrees with `FUNDING.md` from the other direction.

Staking the spot leg (stETH 2.2%, jitoSOL 4.9%) adds yield to a
do-it-yourself carry, but Ethena already does it and still pays about cash.

## 3. The regime is the whole story

Hyperliquid's BTC funding rate, annualised, by half-year:

| 2023 H1 | 2023 H2 | 2024 H1 | 2024 H2 | 2025 H1 | 2025 H2 | 2026 H1 | 2026 H2 |
|---|---|---|---|---|---|---|---|
| 20.5% | 15.9% | **30.1%** | 18.2% | 10.1% | 11.1% | **3.1%** | 8.9% |

`FUNDING.md` measured the carry over September 2025 to September 2026: the
bottom of this table. These payoffs are cyclical. They are close to worthless
in quiet markets and pay four to seven times cash in euphoric ones.

That turns "is this a good trade?" into "is this a good trade *right now*?"
— which a scheduled job can answer.

## 4. Which signals actually predict anything

A monitor is only useful if today's reading says something about the weeks
ahead. Tested before building on it:

| Signal | Predicts the next period? |
|---|---|
| sUSDe 30-day yield → next 30 days | **Yes: +0.75** (30 non-overlapping months) |
| Hyperliquid funding, trailing 30d → next 30d | **Yes: +0.51** (989 coin-months, `FUNDING.md`) |
| HLP trailing 90d → next 90d | **No: +0.03** (12 non-overlapping windows) |

HLP swings +2.5% → +30.5% → +18.1% → +5.9% with no pattern, because
crashes do not announce themselves. A monitor that let HLP's trailing return
trigger alerts would flag it as attractive immediately after each payday —
exactly backwards. **So HLP is reported for context and never sets the
regime.** Only sUSDe and funding do.

## 5. Would the alerts have meant anything?

Classifying each month by its trailing sUSDe reading, then looking at what
the *following* month actually paid:

| Reading | Months | Following month paid (mean) | Range |
|---|---|---|---|
| **RICH** | 10 | **15.8%** | 4.7% – 32.6% |
| WARMING | 4 | 7.9% | 5.9% – 12.1% |
| **QUIET** | 16 | **4.8%** | 3.5% – 8.9% |

A RICH reading has been followed by roughly three times the yield of a
QUIET one, and QUIET has meant approximately cash. **This table is
in-sample** — the thresholds were chosen on the same history — so read it as
a sanity check that the signal is not noise, not as a forecast. The
correlations in section 4 do not depend on any threshold.

## 6. The rate you can lock: Deribit dated futures

Funding and sUSDe pay tomorrow's rate. A dated future pays today's: buy
spot, sell the quarterly future at its premium, and the two converge at
expiry. The premium, annualised, is known on day one. Reconstructed from
every BTC and ETH quarterly since late 2020 (Deribit's own daily closes,
including expired contracts, against Coinbase spot), as a constant ~3-month
rate:

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| BTC, mean | 14.4% | 1.6% | 5.3% | 12.2% | 7.0% | 3.1% |
| ETH, mean | 15.0% | 0.0% | 4.2% | 11.7% | 5.9% | 1.9% |

It is the best regime signal found here:

| | |
|---|---|
| This month's rate predicts next month's | **+0.83** (70 months) |
| Moves with sUSDe yield | **+0.93** (BTC, 32 months) |
| In sUSDe's QUIET / WARMING / RICH months | **4.5% / 7.4% / 13.2%** |
| History | six years, including the 2021 bull and 2022 bear |

**Daily readings are unusable for alerts.** Thin daily closes on the
quarterlies make the raw series jump: replayed day by day it would have
changed level ~130 times a year, and a 7-day median still 19–28 times. The
monitor uses the 30-day mean of the BTC/ETH average, which changes level
about four times a year and reads RICH on 58% of 2021 and 51% of 2024,
QUIET on every day of 2022 and of 2026.

**Today: 4.4% (BTC 4.8%, ETH 3.9%) — QUIET**, in line with the other two.

## 7. The Hyperliquid–Deribit gap

The live snapshot on 23 September showed Hyperliquid funding near 9.5%
against a Deribit locked rate near 5.2%. Tested over every non-overlapping
quarter since Hyperliquid's history begins:

| Short Hyperliquid perp, long Deribit future | BTC | ETH |
|---|---|---|
| Quarters the floating leg beat the locked rate | **12 of 13** | **13 of 13** |
| Mean spread, annualised, gross | **+7.5%** (t = 3.3) | **+10.4%** (t = 4.3) |
| Same test against Deribit's own perpetual | −1.6% (9 of 23) | −1.9% (8 of 23) |

The control row explains it. Against Deribit's perpetual there is no gap.
Hyperliquid's funding formula carries a fixed interest component — 0.01% per
8 hours, 10.95% a year — that holds funding at that level whenever the perp
trades near fair value; Deribit's has no such floor. So in calm markets
Hyperliquid funding sits near 11% while the lockable rate sits near cash.

**It is real, and it is smaller than those means.** Some of the per-quarter
spread was luck: entries in late 2023 caught funding rising into the 2024
bull. The same-month gap — funding and locked rate measured over the same
period — averaged +11.9% (BTC) in 2024 and **+1.5% to +3.5% in 2025–26**.
Before fees (~0.8% a year for the legs at quarterly rolls), margin posted
at two venues, and the fact that ADL targets exactly the profitable short
in a crash, that is roughly a cash return today. It is a RICH-regime trade,
not a standing arbitrage — so the monitor shows the gap as context, not as a
trigger (its month-to-month persistence is only +0.3 to +0.4).

---

## The monitor

`.github/workflows/regime-monitor.yml` runs `polybot regime` every six hours
on GitHub's servers. Nothing runs on your machine.

**What it watches**

| Signal | Sets the regime | Warm | Rich |
|---|---|---|---|
| sUSDe 30-day yield | yes | 6.5% | 10% |
| BTC/ETH 30-day funding (gross) | yes | 15% | 25% |
| BTC/ETH 3-month locked rate (Deribit, 30-day mean) | yes | 8% | 11% |
| HLP trailing 90-day return | no — context only | — | — |
| Hyperliquid minus Deribit gap | no — context only | — | — |

The funding thresholds sit well above 11% deliberately. Hyperliquid funding
includes an interest component that annualises to **10.95%** — what a perp
pays when it trades at fair value. On the day this was built the 7-day
BTC/ETH average read 11.57%: a threshold near 11% would be alerting about an
ordinary market.

**Why 30 days, and why a buffer.** The first version used a 7-day funding
window. Replayed six-hourly over the last year with a threshold placed
inside the signal's range, it changed level **15–36 times a year** — an
open/close email every couple of weeks. A 30-day window is the horizon the
persistence in section 4 was measured at, and with a one-point buffer on the
way down it changed level **4–7 times a year** under the same test. The
sUSDe signal needs neither: its 30-day average changed level 8 times in 2.5
years of history.

**How you hear about it**

- A GitHub issue titled `[regime] WARMING …` or `[regime] RICH …` opens and
  mentions you. GitHub emails you.
- If the regime changes, the issue gets a comment (another email).
- When it returns to QUIET, the issue comments and closes itself.
- At the same level, the issue body refreshes silently — no notification.
- Replayed day by day from March 2024 with all three regime signals and the
  one-point buffer, it would have sent **11 notifications in 2.5 years
  (4.4 a year)**: RICH from March 2024, WARMING that August, RICH again from
  October to March 2025, a few WARMING flickers in mid-2025, and QUIET since
  October 2025.

**Guarantees, each pinned by a test**

- A data source going down can escalate an alert but can never downgrade or
  close one. An outage must not read as "the market went quiet".
- QUIET never opens anything.
- HLP can never open, escalate or close an alert.
- An open alert is held until its reading is more than one percentage point
  below the threshold that raised it. Rises are never delayed.

**Settings** — repository *Settings → Secrets and variables → Actions*:

| Name | Kind | What |
|---|---|---|
| `REGIME_HURDLE` | variable | The cash rate shown in the *vs cash* column, e.g. `4.5`. Defaults to the 4.08% US T-bill. Every yield here is in US dollars, so US cash is the like-for-like comparison; an AUD term-deposit rate only compares fairly if the currency is hedged (see *Currency* below). Changes the report, never when alerts fire. |
| `REGIME_SUSDE_WARM` / `_RICH`, `REGIME_FUNDING_WARM` / `_RICH`, `REGIME_BASIS_WARM` / `_RICH` | variable | Threshold overrides, e.g. `8` for 8% |
| `REGIME_WEBHOOK_URL` | secret | Optional Slack or Discord webhook for a push notification |

Run it by hand from the repository's **Actions** tab → *Regime monitor* →
*Run workflow*, or locally with `polybot regime`.

**It only runs from the default branch.** GitHub schedules workflows from
`main`, so it starts once this is merged. In a public repository GitHub also
pauses scheduled workflows after 60 days without repository activity; the
Actions tab shows a banner to re-enable it.

## What a RICH alert is not

It is a statement about what the market is paying, not advice to take the
risk that earns it. Three risks were not measured when this monitor was
built, and each is large enough to matter more than the yield.

### The exchange can take your hedge away mid-crash

On **10 October 2025**, the largest single-day liquidation event on record
(about $19bn across venues), Hyperliquid triggered cross-margin
**auto-deleveraging (ADL)** for the first time in over two years:
~35,000 ADL events across ~20,000 users and 161 markets inside about five
minutes. ADL closes *profitable* positions on the other side to cover
accounts that went bankrupt.

The funding carry in `FUNDING.md` is, by construction, a short perp against
long spot. In a crash that short is exactly the profitable position ADL
selects. It gets closed at the exchange's chosen price, and what was
delta-neutral becomes a naked long spot position at the worst possible
moment. Every carry number in this repo assumes the hedge holds; on that day,
for those users, it did not.

The same hour is the other side of section 1. HLP's own history shows
$41.5M of profit in the fortnight of 1–15 October 2025, on a $427M vault —
the +9.7% in the table — and reports put roughly **$40M** of it in that one
hour. HLP earns in the crash precisely because other users' positions are
being closed.

### The yield products that died are not in the data

HLP and sUSDe were measured because they exist. The products that paid
comparable yields last cycle and then failed are, by definition, not in any
live dataset:

| Product | What it paid | What happened |
|---|---|---|
| Anchor Protocol (Terra) | ~19.5% on UST deposits | UST depegged and collapsed, May 2022 |
| Celsius | high single to double digits | Froze withdrawals, bankrupt July 2022 |
| BlockFi | up to ~9% on stablecoins | Bankrupt November 2022, after FTX |
| FTX | yield on balances | Collapsed November 2022 |

High yield in a RICH market is also when these structures break, because the
yield is being paid to someone for carrying the risk that eventually
arrives. The in-sample table in section 5 contains no failures because it
only contains survivors.

### Currency

Every yield in this repo is earned in US dollars. For an Australian entity,
measured over the last ten years of AUD/USD daily closes:

| | |
|---|---|
| Annualised volatility | **9.7%** |
| Median 12-month move | 5.3% |
| 12-month windows moving more than 5% | **52%** |
| Worst / best 12 months | −16.1% / +26.7% |

Half the time, the exchange rate alone moves more in a year than the 1–2%
excess any strategy here earned. Hedging removes that risk, and by interest
rate parity it costs roughly the gap between US and Australian cash rates,
which is why US cash is the fair comparison for these yields.

### And the rest

- **HLP:** crash exposure by construction, the JELLY precedent, a single
  venue, and returns that have not repeated their early years.
- **sUSDe:** a synthetic dollar — depeg, custody and smart-contract risk, and
  Ethena restricts some jurisdictions; check your entity is eligible.
- **Tax.** Vault income and funding are likely ordinary income rather than
  discounted capital gains in Australia. That is a question for your
  accountant, not this repo.
- **A RICH market is also the one most likely to produce the next cascade.**
  The yield is high because the risk is.

## Limitations

- **Two regimes of sUSDe history.** It launched in February 2024, so the
  record holds one rich year and one and a half quiet ones. The persistence
  result rests on 30 months.
- **HLP is sampled every 14 days**, so its drawdowns are understated and
  single-fortnight events dominate its returns.
- **Thresholds are calibrated in-sample**, as noted in section 5.
- **Funding by half-year is BTC only.** ETH and SOL were rate-limited during
  collection; the monitor itself reads BTC and ETH.
- **One data provider** (DefiLlama) for sUSDe. If it fails, that signal is
  marked unavailable and the monitor refuses to downgrade on the remainder.

## Sources

- [OneKey: lessons from the JELLY incident](https://onekey.so/blog/ecosystem/hyperliquid-jelly-incident-lessons/)
- [Halborn: the Hyperliquid incident, March 2025](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-march-2025)
- [OAK Research: JELLY attack context and team response](https://oakresearch.io/en/analyses/investigations/hyperliquid-jelly-attack-context-vulnerability-team-solution)
- [Cryptopolitan: validator changes after the JELLY delisting](https://www.cryptopolitan.com/hyperliquid-makes-validator-changes-jelly/)
- [CoinGecko: HLP vault analysis](https://www.coingecko.com/learn/hyperliquid-hlp-vault-analysis)
- [Hyperliquid activates cross-margin ADL for the first time](https://wublock.substack.com/p/hyperliquid-activates-cross-margin)
- [ZeroHedge: ADL after October's liquidation day](https://www.zerohedge.com/crypto/after-octobers-liquidation-day-collapse-adl-are-3-most-important-letters-crypto)
- [edgeX: the $19bn liquidation event and ADL risks](https://pro.edgex.exchange/en-US/news/article/crypto-auto-deleveraging-risks)
- [Gate: Hyperliquid vs Binance auto-deleveraging](https://www.gate.com/learn/articles/adl-the-final-line-of-defense/12960)
- [Autodeleveraging as online learning, arXiv 2602.15182](https://arxiv.org/abs/2602.15182)
- AUD/USD daily closes, 2016–2026, Yahoo Finance (`AUDUSD=X`).
- Hyperliquid info API (`vaultDetails`, `fundingHistory`); DefiLlama yields
  API (`yields.llama.fi`), pools for Ethena sUSDe, Lido stETH, Jito jitoSOL.
