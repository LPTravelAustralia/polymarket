# Memecoins, copy trading and Axiom: full teardown

Research commissioned on axiom.trade, pump.fun, copy trading and Robinhood
memecoins. Three parallel research agents, cross-checked against the cost
measurements this project has already made on Polymarket and Hyperliquid.

**The short version: every one of these fails the same gate, for the same
reason, by a wider margin than anything previously tested here.**

---

## 1. The one number that explains the entire industry

A study of **770 call-channel calls** across **2,411,719 trade records**
tested the physically impossible best case — buy at the *exact instant* of
the call, sell 30 seconds later:

> **Mean: +552.2%.  Median: −4.0%.**

The typical trade loses money *with zero latency*. The mean is carried
entirely by a handful of outliers.

Every screenshot, every "I turned $500 into $40k" post, every affiliate
review is a draw from that right tail. The distribution's centre is
negative, and the marketing apparatus of this entire sector is the gap
between those two statistics.

Enter 30 seconds after the call — faster than any human can act — and the
median is **−27.6% at the five-minute mark**.

---

## 2. Cost, which is where all of this dies

This project has now measured the cost structure of four venues. Ranked:

| Venue | All-in cost, per side | Verdict |
|---|---|---|
| Hyperliquid maker | **0.0013%** | measured here |
| Hyperliquid perps taker | 0.045% | published |
| **Polymarket** | **0.92%** | measured here — **we proved this fatal** |
| **Axiom spot** | **~1.68%** | DefiLlama-derived |
| **Solana memecoin snipe** | **4.2–6.2%** | bot fee + priority + slippage + MEV |

We already established that **0.92% destroyed the Polymarket strategy** — a
structural edge of ~1.01% net to roughly 0.1% after fees. Axiom spot is
nearly twice that cost per side. A contested memecoin snipe is **five to
seven times** it.

**Axiom's fee, verified two ways.** Headline is 1.00% per swap, flat, no
maker/taker split, charged on both the buy and the sell. The independent
check: DefiLlama 30-day figures show **$23.36M protocol revenue on $2.325B
volume = 1.005% realised take rate**. The headline is real and it is
applied to gross notional.

The full stack: $39.04M fees against $23.36M revenue implies a further
**0.67% of volume** in priority fees, Jito tips, referral payouts and
cashback — hence ~1.68% all-in per side, **~1.9% per round trip** at entry
tier.

Grinding from the entry tier to the top tier saves **0.20% per side**. The
volume thresholds to get there are **not published**, so you cannot model
your own cost curve in advance.

**Now put that against the holding period.** Median Solana memecoin hold
time is **58 seconds** (2026), down from ~100 seconds in 2025 and ~1 day in
2024. A trader turning capital 20 times a day pays on the order of **40% per
day in explicit fees alone.**

There is no edge in this asset class large enough to survive that. This is
the dominant term and nothing else is close.

---

## 3. Copy trading: mechanically impossible, and measured

The strongest single piece of evidence in this entire project.

A replay study took a **genuinely profitable** pump.fun wallet and simulated
copying it **one slot behind — 400 milliseconds**:

| | Result |
|---|---|
| The trades at the leader's prices | **+2.402 SOL** |
| The same trades, 400ms later | **−5.930 SOL** |
| **Cost of one slot of latency** | **8.33 SOL** — 5× total fees paid |
| Entries filled worse than the leader | **67 of 68** |
| Median entry degradation | **13.5% higher market cap** |
| Risk-parameter combinations tested | **All 80 lost money** |

The author's conclusion: *"this is an execution-latency problem, not a
risk-parameter problem."*

Independently corroborated: a second study over **15,467 token paths** found
expected value **flips from positive to negative between 0ms and 500ms** —
roughly one slot.

**Why it is mechanical, not a skill gap.** Pump.fun uses a constant-product
bonding curve. Every buy raises the price for the next buyer *by
construction*. The wallet you copy has already moved the price against you
before your transaction can exist. You cannot observe a trade before it
happens, so you cannot fix this with better wallet selection, tighter stops,
or smarter sizing.

**The academic literature treats copier predation as its premise.** A
peer-reviewed **ACM Web Conference 2026** paper (UCL) states adversaries
"deploy manipulative bots to front-run trades, conceal positions, and
fabricate sentiment, **systematically extracting value from naïve copiers at
scale**." That is the paper's starting assumption, not its finding.

Three decades of peer-reviewed work on *traditional, regulated, low-latency*
copy trading reaches the same verdict. Dorfleitner et al. (*Journal of
Banking & Finance*): naively copying the highest-return traders "leads to
high losses," and **no strategy produced positive abnormal returns after
transaction costs**. Apesteguia et al. (*Management Science*, 2020) found
one-click copy interfaces **increase risk-taking independent of signal
quality** — the UI itself is the harm.

**Axiom charges the full 1% on every leg the lead wallet takes**, with no
discount. A high-churn leader transfers fees to Axiom at a multiple of your
own trading rate. It is the worst-expectancy product on the platform for the
user and the best for the house.

---

## 4. Who actually wins, and it is documented

**Infrastructure.** Not traders.

- **Axiom: $200M+ in fees with fewer than 10 employees** (Galaxy Research,
  which names Axiom directly). Fastest Y Combinator company to $100M revenue.
- **pump.fun: $1.222B cumulative revenue** by August 2026; $971.37M in 2025
  alone.

Every dollar came out of trader flow.

**Deployer-funded insiders.** Pine Analytics traced direct SOL transfers from
deployer to sniper wallet *before* the snipe — a conservative criterion that
excludes merely-fast public snipers:

- **Over 50% of tokens are bought in the exact block they are created**,
  before the mint is discoverable via public RPC.
- One month: **15,000+ launches, 4,600+ sniper wallets, 10,400+ deployers,
  >15,000 SOL extracted.**
- **87% of these insider snipes were profitable.**
- **85% liquidated within five minutes.**

That 87% is not a strategy. It is a relationship — knowing the mint address
before it exists.

**Latency shops.** **93 of the top 100 pump.fun wallets by volume are bots**,
several active >18 hours a day at inhuman cadence.

**And everyone else.** On tokens that actually migrate, an average of
**36.5% of supply is already in coordinated hands** disguised as unrelated
addresses (MELT dataset, 41,470 launches).

---

## 5. Who loses, across four independent datasets

| Population | Outcome |
|---|---|
| **Solana memecoin traders**, 90-day window, n=304,161 | **~94% lost money.** Median loss **$120**. Among winners, 88% made under $100. **Only 25 wallets made over $10,000.** Aggregate losses **~$1.26bn** |
| **pump.fun**, any given month | **~96% either lost money or made under $500** — stable across every dataset since 2024 |
| **pump.fun**, all time, n=13.55M wallets | **293 wallets (0.002%)** ever realised $1M. 0.4% ever realised $10k |
| **Robinhood Chain memecoins**, n=164,538 wallets | **63% losing.** Winners +$164.3M, losers −$162.4M. **Net across the entire ecosystem: $1.87M** — about $11 a wallet, before fees |

That Robinhood figure deserves a second look. Gains and losses are within 1%
of each other. It is a near-perfect zero-sum transfer with a fee skim on
top — and only **46 traders made over $1M** while **five lost over $10M**.

**And 98.6% of 7M+ pump.fun tokens fell below $1,000 in liquidity**
(Solidus Labs). Whether you call that fraud or indifference is a definitional
argument that makes no difference to a trader: the token died either way.

### The "2026 recovery" does not survive its own footnotes

CoinGecko reports 73.3% of active wallets profitable in April 2026, up from
30.1% in June 2025. This is being widely amplified. CoinGecko's *own*
published caveats:

1. **Realized PnL only** — wallets that bought and never sold are **excluded
   entirely**. That is the single most common retail failure mode. CoinGecko
   states outright that "losses are likely understated."
2. **Not filtered for bots or wash trading** — and 93 of the top 100 wallets
   are bots.
3. The active wallet base had already **fallen 65%**, from 5.2M to 1.8M, as
   losers left.

It measures the win rate of the survivors of a two-year cull, including the
machines that ate them. A competing Dune dashboard over ~1.4M wallets found
**49–50.6% losing** in the same month.

What both agree on is the number that has not moved since 2024: **~96% make
under $500 or lose.**

---

## 6. Axiom specifically: the disqualifying risk

Beyond the fee, one finding should end the conversation for anyone running a
systematic strategy.

**ZachXBT investigation, 26 February 2026** — independently covered by
CoinDesk, DL News, The Defiant, Forbes and others:

> A senior Business Development employee and associates allegedly abused
> Axiom's internal **"god mode" admin dashboards** to view non-public user
> data and insider-trade on it, **for roughly ten months**. Alleged proceeds
> **over $400,000**.

The data exposed to a *business development* role included **a user's entire
wallet list, the wallets that user was tracking, full transaction history,
wallet nicknames, and linked accounts.** ZachXBT: there was **"little to no
monitoring or access controls in place."**

For a discretionary trader that is an outrage. **For a systematic trader it
is disqualifying.** Your edge is your only asset, and that is precisely the
dataset that reconstructs it — your wallet graph, what you watch, and every
trade you have made. The remediation is an unaudited promise of "zero-trust
architecture." No third-party security audit or SOC report exists.

**Other Axiom-specific findings:**

- **No official API.** Community SDKs authenticate by driving **headless
  Chrome through Cloudflare Turnstile**, **scraping OTPs out of an IMAP
  inbox**, and **spoofing Chrome's TLS fingerprint**. No key issuance, no
  rate limits, no versioning, no deprecation policy, plausibly no permission.
  The engineering posture makes the intent clear: they are actively keeping
  non-browser clients out.
- **No published copier outcome data.** Axiom, GMGN, Photon, Trojan, BullX
  and Maestro all publish volume and revenue. **Not one publishes aggregate
  copier PnL.** They have the data, and it would be the most persuasive
  marketing asset available. The silence is informative.
- **Semi-custodial in practice.** Turnkey enclave signing with **email-OTP
  recovery** means email compromise ≈ fund loss, unless you export the seed
  and self-custody.
- **Declining franchise.** From ~72% peak share of Solana bot volume to
  ~44.6% in June 2026 to **third place behind Fomo and GMGN** by August —
  while charging top-of-market fees.
- **Geoblocks the US**, its own country of incorporation. A US-incorporated,
  YC-backed company blocking US users tells you how its own counsel reads the
  product.

### The affiliate pollution is measurable

The referral programme pays **30% / 3% / 2%** across three levels, uncapped,
in SOL. The referred user gets **10% off**.

This has produced a content network that systematically misstates that
discount — claimed figures of 10%, 15%, 20% and 30% across different
affiliate sites. As one source correctly explains: *"That number is the
referrer's Level 1 commission, not the discount you receive as a trader."*

The same network publishes outright false claims — e.g. that "Axiom is
rebranded Photon" (Photon is a separate BVI company founded in 2022).

**Practical rule: treat every "Axiom review" in crypto media as affiliate
content unless proven otherwise.** Roughly two-thirds of search results for
any query in this space are vendor marketing with no methodology.

---

## 7. Legal exposure is now live

***Aguilar v. Baton Corporation Ltd. d/b/a Pump.Fun***, No. 1:25-cv-00880
(S.D.N.Y.). **Judge Colleen McMahon's ruling, 31 August 2026:**

- Securities claims: **dismissed** (the SEC stated in Feb 2025 that memecoins
  "do not involve the offer and sale of securities").
- Solana Labs and Solana Foundation: **dismissed** as defendants.
- **Civil RICO claims survive** against Baton Corporation and founders Alon
  Cohen, Dylan Kerler and Noah Tweedale. The court found adequately pleaded:
  a racketeering enterprise, **wire fraud predicated on pump.fun's "fair
  launch" marketing**, and **operation of an unlicensed money transmitting
  business**.

Separately: **IOSCO FR/06/2025** (May 2025) is now the authoritative
international finding on copy trading — predominantly short-term, higher-risk,
concentrated in crypto, with "erosion of returns due to high transaction fees
from frequent trading." **ESMA's 2023 briefing** holds that copy trading can
constitute investment advice or portfolio management under MiFID II.

Notably: **no enforcement action anywhere has been brought specifically
against a Solana copy-trading bot.** They operate outside the perimeter
entirely.

---

## 8. The pattern, across everything this project has tested

Four venues, one structure:

1. **The venue publishes its revenue and never its users' outcomes.**
   Polymarket, Hyperliquid, Axiom, pump.fun — all instrument everything, all
   disclose volume and fees, none disclose aggregate user PnL. In a business
   this measured, that absence is a decision.
2. **The winners are structurally advantaged, not skilled.** Polymarket's top
   account had a 20-second broadcast-lag edge. Pump.fun's 87%-win-rate cohort
   knew the mint address before it existed. Neither is a strategy you can
   adopt.
3. **Leaderboards are survivorship filters.** Hyperliquid displayed
   $285M profit on $0 volume. Pump.fun leaderboards draw from 293 wallets out
   of 13.55M. Transfers between a trader's own wallets count as profit.
   Unrealised bags inflate win rates. Selecting on displayed returns is
   empirically the **worst** selection method (Dorfleitner et al.).
4. **Cost per round trip exceeds any plausible edge.** This has been the
   binding constraint at every single venue tested, without exception.
5. **The marketing is the right tail of a negative-median distribution.**
   +552% mean, −4% median.

---

## 9. Verdict

**Expected value is negative before you make a single decision, and the
negative expectation is dominated by fees and adverse selection rather than
by bad token picks.** No amount of selection skill on the token dimension
overcomes it.

For calibration against work already done here: we killed the Polymarket
complete-set strategy because a **0.92%** fee consumed a **1.01%** structural
edge. Axiom spot costs **~1.68% per side**. A contested memecoin snipe costs
**4.2–6.2%**. There is no structural edge in memecoins remotely comparable to
a complete-set identity — the payoff is pure speculation — and the cost is
two to seven times higher.

**The four seats with demonstrated positive expectancy:**

1. **Infrastructure** — Axiom, pump.fun, bot front-ends. That is a business,
   not a trade.
2. **Deploy-and-snipe** — 87% win rate, and precisely the conduct the SDNY
   wire-fraud theory targets.
3. **Sub-block latency with private orderflow** — what the 93 bots are doing;
   an HFT business competing against other HFT businesses.
4. **Everyone else** — the 94–96%.

**One honest qualification.** Launch-structure selection is real and
measurable: an 832,941-launch survival analysis found a **17.4x graduation
lift** for launches advertising all three social channels versus none (1.919%
vs 0.110%), and MELT-trained models cut realised loss by **56.1%**. That is
a genuine signal. But it moves a ~0.2% base rate to a ~1.9% base rate — it
improves a catastrophic prior into a merely terrible one, and it does nothing
about the fee stack, the 58-second holding horizon, or the fact that half of
all tokens are bought in block zero by someone who knew the address before
you did.

---

## Sources

Key primary and independent sources (affiliate/vendor content excluded
throughout):

- [Copy Trading — Apesteguia, Oechssler & Weidenholzer, *Management Science*](https://pubsonline.informs.org/doi/10.1287/mnsc.2019.3508)
- [To Follow or Not to Follow — Dorfleitner et al., SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3108422)
- [Resisting Manipulative Bots in Meme Coin Copy Trading — ACM WWW'26](https://dl.acm.org/doi/10.1145/3774904.3792635)
- [Quantifying the Threat of Sandwiching MEV on Jito — ACM IMC 2025](https://dl.acm.org/doi/10.1145/3730567.3764493)
- [solana-replay-engine — copy-trading latency replay](https://github.com/dhanoliya-ji/solana-replay-engine)
- [botwiner — execution-aware Solana research, published negative result](https://github.com/obadadallo95/botwiner)
- [Pump.fun graduation survival analysis, n=832,941 — arXiv 2607.02823](https://arxiv.org/abs/2607.02823)
- [MemeTrans / MELT dataset — arXiv 2602.13480](https://arxiv.org/abs/2602.13480)
- [Pine Analytics — Exit Liquidity Machines](https://pineanalytics.substack.com/p/exit-liquidity-machines)
- [Inside the Economics of Pump.fun Call Channels — moneyleavesclues](https://moneyleavesclues.substack.com/p/inside-the-economics-of-pumpfun-call)
- [Solidus Labs — Solana Rug Pulls & Pump-and-Dumps](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance)
- [CoinGecko Research — Pump.fun Traders Are Making a Comeback](https://www.coingecko.com/research/publications/pump-fun-traders-are-making-a-comeback) (and its [methodology caveats](https://x.com/coingecko/status/2052967964538998856))
- [99.6% of Pump.fun traders haven't locked in over $10K — Cointelegraph](https://cointelegraph.com/news/pump-fun-crypto-traders-majority-do-not-realize-profits-dune-data)
- [98% of Tokens on Pump.fun Have Been Rug Pulls — CoinDesk](https://www.coindesk.com/business/2025/05/07/98-of-tokens-on-pump-fun-have-been-rug-pulls-or-an-act-of-fraud-new-report-says)
- [Aguilar v. Baton Corporation — Burwick Law](https://www.burwick.law/active-cases/pump-fun-and-solana-rico-lawsuit-aguilar-v-baton-corporation)
- [IOSCO FR/06/2025 — Online Imitative Trading Practices](https://www.iosco.org/library/pubdocs/pdf/IOSCOPD793.pdf)
- [ESMA guidance on copy trading supervision](https://www.esma.europa.eu/press-news/esma-news/esma-provides-guidance-supervision-copy-trading-services)
- [Solana's H1 2026 earnings: 87% drop — 21Shares](https://www.21shares.com/en-eu/insights/solana-h1-2026-earnings-analysis)
- [Why Robinhood Chain's memecoin boom has 63% of traders losing money](https://www.bitget.com/news/detail/12560605520304)
- [Hyperliquid leaderboards confuse traders — Protos](https://protos.com/hyperliquid-leaderboards-confuse-traders-as-hype-hits-all-time-high/)
