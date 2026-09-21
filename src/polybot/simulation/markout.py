"""Markout: measuring adverse selection instead of guessing it.

`adverse_selection_per_share` is the most dangerous number in the config.
Set it too low and the bot quotes inside its true cost and bleeds on every
fill, slowly enough that it looks like variance for weeks.

Markout measures it directly. After a fill at price P at time t, look at the
mid at t+h:

    BUY  markout(h) = mid(t+h) - P
    SELL markout(h) = P - mid(t+h)

Positive means the market moved your way after you traded. Negative means you
were picked off. Averaged over many fills, **-mean(markout) is your adverse
selection cost per share**, and that is the number the quoting strategy must
clear before it books any edge at all.

Horizons matter. A very short horizon mostly measures noise and the spread
you just captured; a long one drifts into unrelated market movement. For
prediction markets, 60s to 600s is the useful band.
"""

from __future__ import annotations

import logging
import statistics
from bisect import bisect_left
from dataclasses import dataclass, field

from ..marketdata.store import Snapshot
from .fills import SimulatedFill

log = logging.getLogger(__name__)

DEFAULT_HORIZONS = (60, 300, 900)


class MidSeries:
    """Time-indexed mids for one token, with as-of lookup."""

    def __init__(self, snapshots: list[Snapshot]):
        pairs = [(s.ts, s.mid) for s in snapshots if s.mid is not None]
        pairs.sort(key=lambda x: x[0])
        self._ts = [p[0] for p in pairs]
        self._mid = [p[1] for p in pairs]

    def __len__(self) -> int:
        return len(self._ts)

    def at_or_after(self, ts: float, max_gap: float = 300.0) -> float | None:
        """First mid at or after `ts`.

        Returns None if the nearest observation is more than `max_gap` later,
        rather than silently comparing against a stale price from an hour on.
        """
        if not self._ts:
            return None
        idx = bisect_left(self._ts, ts)
        if idx >= len(self._ts):
            return None
        if self._ts[idx] - ts > max_gap:
            return None
        return self._mid[idx]


@dataclass
class MarkoutResult:
    horizon_seconds: int
    n: int
    mean: float
    median: float
    stdev: float
    mean_by_reason: dict[str, float] = field(default_factory=dict)

    @property
    def adverse_selection_per_share(self) -> float:
        """Cost per share. Positive means fills are adversely selected."""
        return -self.mean

    @property
    def standard_error(self) -> float:
        return self.stdev / (self.n**0.5) if self.n > 1 else float("inf")

    @property
    def is_significant(self) -> bool:
        """Roughly two standard errors from zero.

        Without this check a handful of fills will happily suggest a
        precise-looking constant that is pure noise.
        """
        return self.n >= 30 and abs(self.mean) > 2 * self.standard_error


def compute_markouts(
    fills: list[SimulatedFill],
    snapshots_by_token: dict[str, list[Snapshot]],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, MarkoutResult]:
    """Markout at each horizon, overall and split by fill reason."""
    series = {tid: MidSeries(snaps) for tid, snaps in snapshots_by_token.items()}
    out: dict[int, MarkoutResult] = {}

    for h in horizons:
        values: list[float] = []
        by_reason: dict[str, list[float]] = {}

        for fill in fills:
            s = series.get(fill.token_id)
            if s is None:
                continue
            future_mid = s.at_or_after(fill.ts + h)
            if future_mid is None:
                continue

            if fill.side.upper() == "BUY":
                mo = future_mid - fill.price
            else:
                mo = fill.price - future_mid

            values.append(mo)
            by_reason.setdefault(fill.reason, []).append(mo)

        if not values:
            continue

        out[h] = MarkoutResult(
            horizon_seconds=h,
            n=len(values),
            mean=statistics.fmean(values),
            median=statistics.median(values),
            stdev=statistics.stdev(values) if len(values) > 1 else 0.0,
            mean_by_reason={
                k: statistics.fmean(v) for k, v in by_reason.items() if v
            },
        )

    return out


@dataclass
class Calibration:
    """A recommendation for adverse_selection_per_share."""

    suggested: float
    based_on_horizon: int
    sample_size: int
    current: float | None = None
    confident: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if not self.confident:
            return "INSUFFICIENT DATA -- keep the current value and collect more"
        if self.current is None:
            return f"Set adverse_selection_per_share = {self.suggested:.4f}"
        if self.suggested > self.current * 1.2:
            return (
                f"RAISE adverse_selection_per_share to {self.suggested:.4f} "
                f"(currently {self.current:.4f} -- too tight, quotes will bleed)"
            )
        if self.suggested < self.current * 0.8:
            return (
                f"Could lower adverse_selection_per_share to {self.suggested:.4f} "
                f"(currently {self.current:.4f} -- leaving edge on the table)"
            )
        return f"Current value {self.current:.4f} is about right"


def calibrate(
    markouts: dict[int, MarkoutResult],
    *,
    current: float | None = None,
    prefer_horizon: int = 300,
) -> Calibration:
    """Turn markout measurements into a config recommendation.

    Uses the preferred horizon when it is available and significant, else the
    longest horizon that is. Deliberately refuses to recommend anything off a
    small or noisy sample.
    """
    notes: list[str] = []
    if not markouts:
        return Calibration(0.0, 0, 0, current, False,
                           ["No markouts computed -- no fills, or no future mids."])

    chosen = markouts.get(prefer_horizon)
    if chosen is None or not chosen.is_significant:
        significant = [m for m in markouts.values() if m.is_significant]
        if significant:
            chosen = max(significant, key=lambda m: m.horizon_seconds)
            notes.append(
                f"Preferred {prefer_horizon}s horizon was not significant; "
                f"used {chosen.horizon_seconds}s instead."
            )
        else:
            fallback = markouts.get(prefer_horizon) or next(iter(markouts.values()))
            notes.append(
                f"No horizon reached significance (largest sample "
                f"n={max(m.n for m in markouts.values())}). Collect more data."
            )
            return Calibration(
                suggested=max(0.0, -fallback.mean),
                based_on_horizon=fallback.horizon_seconds,
                sample_size=fallback.n,
                current=current,
                confident=False,
                notes=notes,
            )

    suggested = max(0.0, chosen.adverse_selection_per_share)

    through = chosen.mean_by_reason.get("price_through")
    queue = chosen.mean_by_reason.get("queue")
    if through is not None and queue is not None:
        notes.append(
            f"Price-through fills markout {through * 100:+.3f}c vs "
            f"{queue * 100:+.3f}c for queue fills -- "
            + ("as expected, being run through is the expensive kind."
               if through < queue else
               "unexpected: queue fills look worse, check the fill model.")
        )

    if suggested == 0.0:
        notes.append(
            "Measured markout is positive: fills are NOT adversely selected "
            "in this sample. Treat with suspicion before trusting it."
        )

    return Calibration(
        suggested=suggested,
        based_on_horizon=chosen.horizon_seconds,
        sample_size=chosen.n,
        current=current,
        confident=True,
        notes=notes,
    )


def render_markout_report(
    markouts: dict[int, MarkoutResult], calibration: Calibration
) -> str:
    lines = ["Markout analysis", "=" * 60, ""]
    if not markouts:
        lines.append("No markouts computed.")
        return "\n".join(lines)

    lines.append(f"{'horizon':>9}  {'n':>7}  {'mean':>10}  {'median':>10}  {'sig':>4}")
    for h in sorted(markouts):
        m = markouts[h]
        lines.append(
            f"{h:>8}s  {m.n:>7,}  {m.mean * 100:>9.3f}c  "
            f"{m.median * 100:>9.3f}c  {'yes' if m.is_significant else 'no':>4}"
        )

    lines += ["", f"Adverse selection: {calibration.suggested * 100:.3f}c/share "
                  f"(from {calibration.based_on_horizon}s, n={calibration.sample_size:,})",
              "", calibration.verdict]
    if calibration.notes:
        lines += [""] + [f"  - {n}" for n in calibration.notes]
    return "\n".join(lines)
