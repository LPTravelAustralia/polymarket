"""Event study: is a news-driven move tradeable *after* it starts?

You are right that news causes large swings in crypto. That is not in
dispute and it is not the useful question. The useful question is:

> Once a shock has begun, does price keep moving in the same direction
> (**drift**), or snap back (**mean reversion**)?

That distinction decides everything:

  - **Drift** → you do not need to be fast. See the move, join it, profit.
    This is the crypto analogue of post-earnings announcement drift in
    equities, and it is tradeable by a slow participant.
  - **Mean reversion** → latecomers are the exit liquidity for the fast
    money. Actively harmful.
  - **Neither** → no edge, and the appeal was an illusion.

**Methodological note.** This deliberately needs no news feed. Large
price shocks *are* news events, essentially by definition, and using
returns to identify them avoids three problems that wreck news-based
studies: the timestamp on a news article is when the *vendor published*,
not when the information existed; news coverage is itself caused by price
moves, creating circularity; and an LLM reading historical headlines
knows what happened next, which is the look-ahead bias that invalidates
most published sentiment backtests.

Identifying shocks from returns sidesteps all three. The cost is that we
learn nothing about *which* news matters -- but that was never the
blocker.

**The bar this must clear.** Drift is not enough; it must exceed round-trip
costs. At 0.05% taker each way that is 0.10%, so a statistically real drift
of 0.03% is a statistically real way to lose money.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

# Horizons in bars. With 1-minute candles these are 1m, 5m, 15m, 1h, 4h.
DEFAULT_HORIZONS = (1, 5, 15, 60, 240)


@dataclass
class Candle:
    ts: int          # ms
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @classmethod
    def from_hyperliquid(cls, d: dict) -> "Candle":
        return cls(
            ts=int(d.get("t", 0)),
            open=float(d.get("o", 0)),
            high=float(d.get("h", 0)),
            low=float(d.get("l", 0)),
            close=float(d.get("c", 0)),
            volume=float(d.get("v", 0) or 0),
        )


@dataclass
class Shock:
    index: int
    ts: int
    ret: float               # the shock bar's own return
    z: float                 # how many sigma
    direction: int           # +1 up, -1 down
    forward: dict[int, float] = field(default_factory=dict)  # horizon -> signed return


@dataclass
class HorizonResult:
    horizon: int
    n: int
    mean_return: float       # signed in the shock's direction
    median_return: float
    stdev: float
    hit_rate: float          # share continuing in the shock direction

    @property
    def standard_error(self) -> float:
        return self.stdev / math.sqrt(self.n) if self.n > 1 else float("inf")

    @property
    def t_stat(self) -> float:
        se = self.standard_error
        return self.mean_return / se if se > 0 else 0.0

    @property
    def is_significant(self) -> bool:
        """|t| > 2 and a sample worth the name.

        With many horizons tested, 2 sigma is a *weak* bar -- test five
        horizons and one clears it by luck roughly once in ten. Treat a
        lone significant horizon with suspicion; a monotone pattern across
        horizons is far more convincing than any single t-stat.
        """
        return self.n >= 30 and abs(self.t_stat) > 2.0

    def net_of_costs(self, round_trip_cost: float) -> float:
        return self.mean_return - round_trip_cost

    def verdict(self, round_trip_cost: float) -> str:
        if not self.is_significant:
            return "no signal"
        net = self.net_of_costs(round_trip_cost)
        if self.mean_return < 0:
            return "MEAN REVERTS — joining late is harmful"
        if net <= 0:
            return f"drifts, but costs eat it ({net * 100:+.4f}% net)"
        return f"DRIFTS, net {net * 100:+.4f}% after costs"


@dataclass
class EventStudy:
    symbol: str
    bars: int
    shocks: int
    threshold_sigma: float
    results: dict[int, HorizonResult] = field(default_factory=dict)
    first_bar_share: float = 0.0     # share of the 1h move done in the shock bar

    def tradeable_horizons(self, round_trip_cost: float) -> list[int]:
        return [
            h for h, r in self.results.items()
            if r.is_significant and r.net_of_costs(round_trip_cost) > 0
        ]

    def verdict(self, round_trip_cost: float = 0.001) -> str:
        good = self.tradeable_horizons(round_trip_cost)
        if not good:
            reverting = [
                h for h, r in self.results.items()
                if r.is_significant and r.mean_return < 0
            ]
            if reverting:
                return (
                    "NOT TRADEABLE — shocks mean-revert at "
                    f"{sorted(reverting)} bars. Joining a move late makes you "
                    "the exit liquidity. Do not build this."
                )
            return (
                "NOT TRADEABLE — no horizon shows drift that survives costs. "
                "The swings are real; what follows them is not capturable."
            )
        return (
            f"POSSIBLY TRADEABLE at horizons {sorted(good)} bars. "
            "Confirm out-of-sample before risking anything."
        )


def returns(candles: list[Candle]) -> list[float]:
    out = []
    for prev, cur in zip(candles, candles[1:]):
        out.append((cur.close - prev.close) / prev.close if prev.close else 0.0)
    return out


def rolling_sigma(rets: list[float], window: int = 720) -> list[float]:
    """Trailing volatility, so a shock is judged against recent conditions.

    A 2% minute is unremarkable in a crisis and enormous in a quiet week.
    Using a global sigma would cluster every "shock" into the volatile
    periods and tell you about regimes rather than events.
    """
    out: list[float] = []
    for i in range(len(rets)):
        lo = max(0, i - window)
        sample = rets[lo:i]
        if len(sample) < 30:
            out.append(float("inf"))     # not enough history: never a shock
            continue
        sd = statistics.pstdev(sample)
        out.append(sd if sd > 0 else float("inf"))
    return out


def find_shocks(
    candles: list[Candle],
    *,
    threshold_sigma: float = 4.0,
    vol_window: int = 720,
    min_gap_bars: int = 60,
) -> list[Shock]:
    """Bars whose return is a large multiple of trailing volatility.

    `min_gap_bars` prevents one event being counted many times as its
    aftershocks also clear the threshold, which would fake statistical
    significance by inflating n with non-independent observations.
    """
    rets = returns(candles)
    sigmas = rolling_sigma(rets, vol_window)

    out: list[Shock] = []
    last = -10**9
    for i, (r, sd) in enumerate(zip(rets, sigmas)):
        if not math.isfinite(sd) or sd <= 0:
            continue
        z = r / sd
        if abs(z) < threshold_sigma:
            continue
        if i - last < min_gap_bars:
            continue
        last = i
        # rets[i] is the move from candle i to i+1.
        out.append(
            Shock(index=i + 1, ts=candles[i + 1].ts, ret=r, z=z,
                  direction=1 if r > 0 else -1)
        )
    return out


def measure_forward(
    candles: list[Candle],
    shocks: list[Shock],
    horizons: tuple[int, ...],
    *,
    clean_windows: bool = True,
) -> None:
    """Fill in forward returns, signed in the direction of the shock.

    Signing matters: a down-shock that keeps falling is a *successful*
    continuation trade for someone who sold. Without signing, up and down
    shocks cancel and every study concludes "no effect".

    `clean_windows` drops any (shock, horizon) whose forward window contains
    a *later* shock. Without it, a horizon longer than the typical gap
    between events measures the next event as if it were this one's
    aftermath, and manufactures drift out of nothing. This is standard
    event-study practice and it is not optional: it was added after a test
    on data with deliberately zero follow-through reported tradeable drift
    at the longest horizon purely from window overlap.
    """
    later = sorted(s.index for s in shocks)

    for s in shocks:
        base = candles[s.index].close
        if base <= 0:
            continue
        for h in horizons:
            j = s.index + h
            if j >= len(candles):
                continue
            if clean_windows and _contains_later_shock(later, s.index, j):
                continue
            raw = (candles[j].close - base) / base
            s.forward[h] = raw * s.direction


def _contains_later_shock(sorted_indices: list[int], start: int, end: int) -> bool:
    """Is there another shock strictly inside (start, end]?"""
    from bisect import bisect_right

    i = bisect_right(sorted_indices, start)
    return i < len(sorted_indices) and sorted_indices[i] <= end


def run_event_study(
    symbol: str,
    candles: list[Candle],
    *,
    threshold_sigma: float = 4.0,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    vol_window: int = 720,
) -> EventStudy:
    study = EventStudy(symbol=symbol, bars=len(candles), shocks=0,
                       threshold_sigma=threshold_sigma)
    if len(candles) < vol_window + max(horizons) + 10:
        return study

    shocks = find_shocks(candles, threshold_sigma=threshold_sigma,
                         vol_window=vol_window)
    measure_forward(candles, shocks, horizons)
    study.shocks = len(shocks)
    if not shocks:
        return study

    for h in horizons:
        vals = [s.forward[h] for s in shocks if h in s.forward]
        if len(vals) < 2:
            continue
        study.results[h] = HorizonResult(
            horizon=h,
            n=len(vals),
            mean_return=statistics.fmean(vals),
            median_return=statistics.median(vals),
            stdev=statistics.stdev(vals),
            hit_rate=sum(1 for v in vals if v > 0) / len(vals),
        )

    # How much of the hour-long move is already done in the shock bar itself?
    # If it is ~all of it, there is nothing left for a latecomer regardless
    # of what the significance tests say.
    long_h = max(h for h in horizons if h in study.results) if study.results else None
    if long_h:
        shares = []
        for s in shocks:
            total = s.forward.get(long_h)
            if total is None or abs(total) < 1e-9:
                continue
            shares.append(abs(s.ret) / (abs(s.ret) + abs(total)))
        if shares:
            study.first_bar_share = statistics.fmean(shares)

    return study


def pool_studies(studies: list[EventStudy]) -> EventStudy:
    """Combine per-symbol studies into one pooled sample.

    A single coin rarely produces enough shocks in the available history to
    support a verdict, so pooling is usually the only route to an adequate
    sample. The assumption it buys -- that the effect is common across the
    coins pooled -- is a real one, and if the per-coin results disagree in
    sign the pooled number is meaningless. Check the per-coin tables above
    the pooled one before trusting it.

    Means are weighted by n; the pooled standard deviation is reconstructed
    from each group's mean and variance rather than averaged, which would
    understate it.
    """
    out = EventStudy(
        symbol=f"POOLED ({len(studies)} symbols)",
        bars=sum(s.bars for s in studies),
        shocks=sum(s.shocks for s in studies),
        threshold_sigma=studies[0].threshold_sigma if studies else 0.0,
    )

    horizons = sorted({h for s in studies for h in s.results})
    for h in horizons:
        groups = [s.results[h] for s in studies if h in s.results]
        n = sum(g.n for g in groups)
        if n < 2:
            continue
        mean = sum(g.mean_return * g.n for g in groups) / n
        # Total variance = within-group + between-group dispersion.
        ss = sum((g.n - 1) * g.stdev**2 + g.n * (g.mean_return - mean) ** 2
                 for g in groups)
        stdev = math.sqrt(ss / (n - 1)) if n > 1 else 0.0
        out.results[h] = HorizonResult(
            horizon=h,
            n=n,
            mean_return=mean,
            median_return=statistics.median([g.median_return for g in groups]),
            stdev=stdev,
            hit_rate=sum(g.hit_rate * g.n for g in groups) / n,
        )

    shares = [s.first_bar_share for s in studies if s.first_bar_share]
    if shares:
        out.first_bar_share = statistics.fmean(shares)
    return out


def render_event_study(study: EventStudy, round_trip_cost: float = 0.001) -> str:
    lines = [
        f"Event study: {study.symbol}",
        "=" * 66,
        f"  bars analysed     {study.bars:,}",
        f"  shocks found      {study.shocks:,} (>{study.threshold_sigma:.1f} sigma)",
        f"  round-trip cost   {round_trip_cost * 100:.3f}%",
        "",
    ]
    if not study.results:
        lines.append("  Not enough data.")
        return "\n".join(lines)

    lines.append(f"  {'horizon':>8} {'n':>6} {'mean':>10} {'median':>10} "
                 f"{'hit%':>7} {'t':>7}  verdict")
    for h in sorted(study.results):
        r = study.results[h]
        lines.append(
            f"  {h:>7}b {r.n:>6} {r.mean_return * 100:>9.4f}% "
            f"{r.median_return * 100:>9.4f}% {r.hit_rate * 100:>6.1f}% "
            f"{r.t_stat:>7.2f}  {r.verdict(round_trip_cost)}"
        )

    if study.first_bar_share:
        lines += [
            "",
            f"  Share of the move already done in the shock bar itself: "
            f"{study.first_bar_share:.1%}",
        ]
        if study.first_bar_share > 0.8:
            lines.append(
                "  -> Most of the move is gone before a slow participant can act."
            )

    lines += ["", f"  {study.verdict(round_trip_cost)}"]
    return "\n".join(lines)
