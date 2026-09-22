"""Behavioural fingerprinting of a Polymarket wallet.

Pure functions over already-fetched history, so they can be tested and
backtested without touching the network.

The point of a fingerprint is to answer one question: *is this wallet's edge
something a bot can reproduce?* A leaderboard rank does not tell you that.
Two wallets with identical PnL can be:

  - a conviction whale who made 18 political bets over two years on the back
    of private polling (not reproducible -- copying it is just leverage on
    someone else's research, months stale by the time you see it), or
  - a systematic maker who priced 150,000 sports markets slightly better than
    consensus and collected the difference (reproducible, and the actual
    template for a bot).

So we decompose income by source, measure maker/taker posture, hold time,
position concentration and price placement, and classify from that.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

# Activity types that are NOT directional trading profit. A leaderboard lumps
# them in; a bot that copies the wallet without separating them will
# misattribute the edge entirely.
REWARD_TYPES = {"REWARD"}
STRUCTURAL_TYPES = {"SPLIT", "MERGE", "CONVERSION"}
SETTLEMENT_TYPES = {"REDEEM"}


@dataclass
class IncomeBreakdown:
    """Where the money actually came from."""

    trade_count: int = 0
    reward_usd: float = 0.0
    reward_events: int = 0
    structural_events: int = 0
    redeem_usd: float = 0.0
    redeem_events: int = 0

    @property
    def reward_dependent(self) -> bool:
        """True when liquidity-mining rewards are a material income line.

        Matters because reward programmes get cut. A strategy whose edge is
        really a subsidy dies the day the subsidy does.
        """
        return self.reward_events > 0 and self.reward_usd > 0


@dataclass
class RoundTrip:
    """A matched buy->sell pair, FIFO."""

    asset: str
    size: float
    entry_price: float
    exit_price: float
    entry_ts: int
    exit_ts: int

    @property
    def hold_seconds(self) -> int:
        return max(0, self.exit_ts - self.entry_ts)

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.size


@dataclass
class Fingerprint:
    """The behavioural signature of one wallet."""

    wallet: str
    name: str | None = None

    # Volume and sizing
    total_trades: int = 0
    total_volume_usd: float = 0.0
    mean_trade_usd: float = 0.0
    median_trade_usd: float = 0.0
    p95_trade_usd: float = 0.0
    max_trade_usd: float = 0.0

    # Posture -- the single most predictive field
    maker_fills: int = 0
    taker_fills: int = 0

    # Timing
    active_days: int = 0
    trades_per_active_day: float = 0.0
    median_hold_seconds: float | None = None
    round_trips: int = 0

    # Placement
    entry_price_histogram: dict[str, int] = field(default_factory=dict)
    mean_entry_price: float = 0.0

    # Breadth and concentration
    distinct_markets: int = 0
    distinct_assets: int = 0
    top_market_volume_share: float = 0.0
    herfindahl: float = 0.0

    # Mix
    category_volume: dict[str, float] = field(default_factory=dict)

    # Income sources
    income: IncomeBreakdown = field(default_factory=IncomeBreakdown)

    # Outcome
    realised_pnl: float = 0.0
    win_rate: float | None = None

    @property
    def maker_ratio(self) -> float:
        total = self.maker_fills + self.taker_fills
        return self.maker_fills / total if total else 0.0

    @property
    def dominant_category(self) -> str | None:
        if not self.category_volume:
            return None
        return max(self.category_volume.items(), key=lambda kv: kv[1])[0]

    @property
    def category_concentration(self) -> float:
        total = sum(self.category_volume.values())
        if not total:
            return 0.0
        return max(self.category_volume.values()) / total


# --------------------------------------------------------------- computation


def _f(v: Any, default: float = 0.0) -> float:
    try:
        out = float(v)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def trade_notional(trade: dict[str, Any]) -> float:
    """USD notional of a fill.

    Prefer an explicit usdcSize when the API gives one; otherwise size*price.
    """
    explicit = _f(trade.get("usdcSize"))
    if explicit > 0:
        return explicit
    return abs(_f(trade.get("size"))) * _f(trade.get("price"))


def match_round_trips(trades: Sequence[dict[str, Any]]) -> list[RoundTrip]:
    """FIFO-match buys against sells per asset to recover holding periods.

    Unmatched buys are open positions and are ignored -- that is correct for
    hold-time statistics, though it does bias toward closed trades. A wallet
    that never sells (holds to resolution) will show few round trips, which is
    itself a signal and is reported as such.
    """
    by_asset: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    out: list[RoundTrip] = []

    # Oldest first, so FIFO means what it says.
    ordered = sorted(trades, key=lambda t: _i(t.get("timestamp")))

    for t in ordered:
        asset = str(t.get("asset") or "")
        if not asset:
            continue
        side = str(t.get("side") or "").upper()
        size = abs(_f(t.get("size")))
        price = _f(t.get("price"))
        ts = _i(t.get("timestamp"))
        if size <= 0:
            continue

        if side == "BUY":
            by_asset[asset].append({"size": size, "price": price, "ts": ts})
        elif side == "SELL":
            remaining = size
            queue = by_asset[asset]
            while remaining > 1e-9 and queue:
                lot = queue[0]
                matched = min(remaining, lot["size"])
                out.append(
                    RoundTrip(
                        asset=asset,
                        size=matched,
                        entry_price=lot["price"],
                        exit_price=price,
                        entry_ts=lot["ts"],
                        exit_ts=ts,
                    )
                )
                lot["size"] -= matched
                remaining -= matched
                if lot["size"] <= 1e-9:
                    queue.popleft()

    return out


def price_histogram(trades: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Where in the probability range this wallet transacts.

    Buckets are deliberately uneven: the tails are where the favourite-longshot
    bias lives and where fees are cheapest, so they deserve their own bins.
    """
    buckets = {
        "0.00-0.05": 0, "0.05-0.15": 0, "0.15-0.35": 0,
        "0.35-0.65": 0, "0.65-0.85": 0, "0.85-0.95": 0, "0.95-1.00": 0,
    }
    edges = [(0.05, "0.00-0.05"), (0.15, "0.05-0.15"), (0.35, "0.15-0.35"),
             (0.65, "0.35-0.65"), (0.85, "0.65-0.85"), (0.95, "0.85-0.95")]

    for t in trades:
        p = _f(t.get("price"))
        if not 0.0 <= p <= 1.0:
            continue
        for cutoff, label in edges:
            if p < cutoff:
                buckets[label] += 1
                break
        else:
            buckets["0.95-1.00"] += 1
    return buckets


def summarise_income(activity: Iterable[dict[str, Any]]) -> IncomeBreakdown:
    """Split activity into trading, rewards, structural and settlement."""
    out = IncomeBreakdown()
    for a in activity:
        kind = str(a.get("type") or "").upper()
        usd = abs(_f(a.get("usdcSize")))
        if kind == "TRADE":
            out.trade_count += 1
        elif kind in REWARD_TYPES:
            out.reward_events += 1
            out.reward_usd += usd
        elif kind in STRUCTURAL_TYPES:
            out.structural_events += 1
        elif kind in SETTLEMENT_TYPES:
            out.redeem_events += 1
            out.redeem_usd += usd
    return out


def build_fingerprint(
    wallet: str,
    trades: Sequence[dict[str, Any]],
    *,
    name: str | None = None,
    activity: Sequence[dict[str, Any]] | None = None,
    taker_fill_count: int | None = None,
    positions: Sequence[dict[str, Any]] | None = None,
    category_of_market: dict[str, str] | None = None,
) -> Fingerprint:
    """Assemble the full fingerprint.

    `taker_fill_count` comes from re-querying /trades with takerOnly=true; the
    difference against the full count gives maker fills. The Data API does not
    label fills maker/taker directly, so this differencing trick is how we
    recover the most important statistic.
    """
    fp = Fingerprint(wallet=wallet, name=name)
    if not trades:
        return fp

    notionals = [trade_notional(t) for t in trades]
    notionals = [n for n in notionals if n > 0]

    fp.total_trades = len(trades)
    fp.total_volume_usd = sum(notionals)
    if notionals:
        fp.mean_trade_usd = fp.total_volume_usd / len(notionals)
        fp.median_trade_usd = statistics.median(notionals)
        fp.max_trade_usd = max(notionals)
        ordered = sorted(notionals)
        fp.p95_trade_usd = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]

    if taker_fill_count is not None:
        fp.taker_fills = max(0, min(taker_fill_count, fp.total_trades))
        fp.maker_fills = fp.total_trades - fp.taker_fills

    timestamps = [_i(t.get("timestamp")) for t in trades if _i(t.get("timestamp")) > 0]
    if timestamps:
        span_days = (max(timestamps) - min(timestamps)) / 86_400.0
        fp.active_days = max(1, int(math.ceil(span_days)))
        fp.trades_per_active_day = fp.total_trades / fp.active_days

    trips = match_round_trips(trades)
    fp.round_trips = len(trips)
    if trips:
        fp.median_hold_seconds = statistics.median(t.hold_seconds for t in trips)

    fp.entry_price_histogram = price_histogram(trades)
    entry_prices = [_f(t.get("price")) for t in trades if 0.0 < _f(t.get("price")) < 1.0]
    if entry_prices:
        fp.mean_entry_price = statistics.fmean(entry_prices)

    # Breadth / concentration
    vol_by_market: dict[str, float] = defaultdict(float)
    assets: set[str] = set()
    for t, n in zip(trades, (trade_notional(x) for x in trades)):
        cid = str(t.get("conditionId") or "")
        if cid:
            vol_by_market[cid] += n
        if t.get("asset"):
            assets.add(str(t["asset"]))

    fp.distinct_markets = len(vol_by_market)
    fp.distinct_assets = len(assets)
    total_vol = sum(vol_by_market.values())
    if total_vol > 0:
        shares = [v / total_vol for v in vol_by_market.values()]
        fp.top_market_volume_share = max(shares)
        fp.herfindahl = sum(s * s for s in shares)

    if category_of_market:
        cat_vol: dict[str, float] = defaultdict(float)
        for cid, v in vol_by_market.items():
            cat_vol[category_of_market.get(cid, "unknown")] += v
        fp.category_volume = dict(cat_vol)

    if activity:
        fp.income = summarise_income(activity)

    if positions:
        pnls = [_f(p.get("cashPnl")) for p in positions]
        fp.realised_pnl = sum(pnls)
        decided = [p for p in pnls if abs(p) > 1e-9]
        if decided:
            fp.win_rate = sum(1 for p in decided if p > 0) / len(decided)

    return fp


# ------------------------------------------------------------ classification


@dataclass
class Archetype:
    """A verdict on whether, and how, a wallet can be copied."""

    label: str
    confidence: float
    replicable: bool
    rationale: list[str] = field(default_factory=list)
    bot_translation: str = ""


def classify(fp: Fingerprint) -> Archetype:
    """Map a fingerprint onto a strategy archetype.

    Thresholds are heuristics chosen to separate the documented extremes
    (a ~18-position conviction whale vs a ~150k-position systematic maker).
    Re-tune them against your own pulled data before relying on the label;
    the rationale strings matter more than the label itself.
    """
    reasons: list[str] = []

    avg = fp.mean_trade_usd
    trades = fp.total_trades
    maker_ratio = fp.maker_ratio
    concentration = fp.top_market_volume_share

    # Reward farming -- check first, because it masquerades as everything else.
    if fp.income.reward_dependent and fp.total_volume_usd > 0:
        reward_intensity = fp.income.reward_usd / max(fp.total_volume_usd, 1.0)
        if reward_intensity > 0.002 and maker_ratio > 0.8:
            reasons.append(
                f"${fp.income.reward_usd:,.0f} of liquidity rewards across "
                f"{fp.income.reward_events} payouts, with {maker_ratio:.0%} maker fills"
            )
            reasons.append("Income is substantially a subsidy, not a price edge")
            return Archetype(
                label="REWARD_FARMER",
                confidence=0.7,
                replicable=True,
                rationale=reasons,
                bot_translation=(
                    "Quote to maximise reward-programme score, not directional edge. "
                    "Viable but fragile: model the programme terms explicitly and "
                    "assume they can be cut at any time."
                ),
            )

    # Structural arbitrage -- heavy SPLIT/MERGE relative to trades.
    if fp.income.structural_events > 0 and trades > 0:
        structural_ratio = fp.income.structural_events / trades
        if structural_ratio > 0.15:
            reasons.append(
                f"{fp.income.structural_events} SPLIT/MERGE/CONVERSION events "
                f"({structural_ratio:.0%} of trade count)"
            )
            reasons.append("Mints and redeems complete sets rather than taking views")
            return Archetype(
                label="STRUCTURAL_ARB",
                confidence=0.75,
                replicable=True,
                rationale=reasons,
                bot_translation=(
                    "Implement complement and neg-risk basket arbitrage. Real, but "
                    "latency-bound: windows are ~seconds and most of the profit goes "
                    "to sub-100ms infrastructure."
                ),
            )

    # Conviction whale: very few, very large, long-held positions.
    if trades <= 200 and avg >= 25_000 and concentration >= 0.10:
        reasons.append(f"{trades} lifetime fills averaging ${avg:,.0f}")
        reasons.append(f"Largest single market is {concentration:.0%} of volume")
        if fp.median_hold_seconds is not None:
            reasons.append(f"Median hold {fp.median_hold_seconds / 86_400:.1f} days")
        if fp.round_trips < trades * 0.25:
            reasons.append("Rarely sells -- holds to resolution")
        return Archetype(
            label="CONVICTION_WHALE",
            confidence=0.8,
            replicable=False,
            rationale=reasons,
            bot_translation=(
                "NOT reproducible by a bot. The edge is off-platform research "
                "(private polling, domain expertise) plus the balance sheet to sit "
                "through drawdown. Copying the fills late is negative-edge: you pay "
                "the price their own buying already moved."
            ),
        )

    # Systematic maker: many small fills, mostly resting, short holds.
    #
    # Thresholds are expressed per active day as well as in absolute terms,
    # because the absolute ones were calibrated on Polymarket wallets with
    # years of history. A 10-day sample of a Hyperliquid account doing 200
    # fills a day is obviously systematic and was being dropped to
    # UNCLASSIFIED purely because 1,951 < 2,000.
    per_day = fp.trades_per_active_day
    systematic = trades >= 2_000 or (trades >= 300 and per_day >= 100)
    if systematic and avg <= 20_000 and maker_ratio >= 0.6:
        reasons.append(f"{trades:,} fills averaging ${avg:,.0f}")
        reasons.append(f"{maker_ratio:.0%} of fills are passive (maker)")
        if fp.median_hold_seconds is not None:
            reasons.append(f"Median hold {fp.median_hold_seconds / 3600:.1f} hours")
        reasons.append(f"Spread across {fp.distinct_markets:,} markets (HHI {fp.herfindahl:.3f})")
        if fp.dominant_category:
            reasons.append(
                f"{fp.category_concentration:.0%} of volume in {fp.dominant_category}"
            )
        return Archetype(
            label="SYSTEMATIC_MAKER",
            confidence=0.85,
            replicable=True,
            rationale=reasons,
            bot_translation=(
                "This is the template. Build a fair-value model for one category, "
                "quote both sides passively inside your own uncertainty band, size "
                "small, repeat thousands of times. Edge per trade is tiny; it "
                "compounds through turnover and costs nothing in fees."
            ),
        )

    # High-turnover taker: the pattern that loses money at scale.
    if (trades >= 500 or (trades >= 100 and per_day >= 50)) and maker_ratio < 0.35:
        reasons.append(f"{trades:,} fills, only {maker_ratio:.0%} passive")
        reasons.append(
            "Crosses the spread habitually -- pays the taker fee on every entry"
        )
        return Archetype(
            label="MOMENTUM_TAKER",
            confidence=0.6,
            replicable=True,
            rationale=reasons,
            bot_translation=(
                "Do NOT copy without proof of edge. Taking costs ~1.25c/share at mid "
                "prices; a round trip needs >2.5c of edge to break even. Profitable "
                "examples here are usually fast reactions to news, which is a "
                "latency race you are unlikely to win."
            ),
        )

    reasons.append(
        f"{trades:,} fills, ${avg:,.0f} average, {maker_ratio:.0%} passive -- "
        "no dominant pattern"
    )
    return Archetype(
        label="UNCLASSIFIED",
        confidence=0.3,
        replicable=False,
        rationale=reasons,
        bot_translation="Pull more history before drawing conclusions.",
    )
