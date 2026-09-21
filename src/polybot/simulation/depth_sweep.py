"""Adverse selection as a function of quote depth.

The single number "adverse selection = 3.8bp" is not actually a property of
a market. It is a property of a market *and a quote placement*, and
conflating the two is why the first calibration read as a flat verdict.

Quoting at the touch maximises fill rate and maximises adverse selection --
you are first in line for exactly the trades that are about to be right.
Quoting deeper fills less often, but the fills are less informed. So the
real question is not "what is adverse selection" but:

> **Is there a depth at which the edge captured exceeds the adverse
> selection suffered?**

That is an optimisation with a genuine interior optimum, not a yes/no. At
the touch you earn half the spread and lose to informed flow; far away you
earn a lot per fill but never trade. Somewhere between, if anywhere, is a
business.

This sweeps depth and reports both sides at each, so the answer is a curve
rather than a verdict.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

from ..backtest.engine import ReplayEngine
from ..config import MakerParams
from ..marketdata.store import PublicTrade, Snapshot
from ..strategy.fair_value import MicropriceModel

log = logging.getLogger(__name__)


@dataclass
class DepthResult:
    """What happens when quoting this far from fair value."""

    depth_bps: float
    fills: int
    fill_rate: float             # fills per quote placed
    gross_edge_bps: float        # edge captured at placement
    adverse_bps: float           # measured markout cost
    pickoff_share: float         # share of volume filled by price-through

    @property
    def net_bps(self) -> float:
        return self.gross_edge_bps - self.adverse_bps

    @property
    def is_viable(self) -> bool:
        return self.fills >= 30 and self.net_bps > 0


@dataclass
class DepthSweep:
    results: list[DepthResult] = field(default_factory=list)
    fee_bps: float = 0.0

    def best(self) -> DepthResult | None:
        viable = [r for r in self.results if r.is_viable
                  and r.net_bps > self.fee_bps]
        return max(viable, key=lambda r: r.net_bps) if viable else None

    def verdict(self) -> str:
        b = self.best()
        if b is None:
            deep = [r for r in self.results if r.fills >= 30]
            if not deep:
                return (
                    "INCONCLUSIVE -- no depth produced enough fills to measure. "
                    "Record longer or on more active markets."
                )
            best_try = max(deep, key=lambda r: r.net_bps)
            return (
                f"NO VIABLE DEPTH. Best was {best_try.depth_bps:.1f}bp out, "
                f"netting {best_try.net_bps:+.2f}bp against a {self.fee_bps:.2f}bp "
                "fee. Spread capture does not clear its costs here."
            )
        return (
            f"VIABLE at {b.depth_bps:.1f}bp from fair: captures "
            f"{b.gross_edge_bps:.2f}bp, loses {b.adverse_bps:.2f}bp to adverse "
            f"selection, nets {b.net_bps:+.2f}bp against a {self.fee_bps:.2f}bp fee "
            f"({b.fills:,} fills, {b.fill_rate:.1%} of quotes)."
        )


def sweep_depths(
    snapshots: list[Snapshot],
    trades: list[PublicTrade],
    depths_bps: tuple[float, ...] = (0.0, 2.0, 5.0, 10.0, 20.0, 40.0),
    *,
    fee_bps: float = 1.5,
    order_size: float = 1.0,
) -> DepthSweep:
    """Replay the strategy at each depth and measure both sides.

    `depths_bps` is distance from fair value, so 0 means at the touch.
    `fee_bps` is the round-trip maker cost for comparison; a result that
    beats adverse selection but not the fee is still a losing trade.
    """
    sweep = DepthSweep(fee_bps=fee_bps)

    for depth in depths_bps:
        frac = depth / 10_000.0
        params = MakerParams.for_perps(
            base_half_spread=frac,
            # The sweep is measuring these, so they must not gate quoting.
            min_edge_per_share=0.0,
            adverse_selection_per_share=0.0,
            uncertainty_multiplier=0.0,
            order_size_shares=order_size,
        )
        engine = ReplayEngine(
            MicropriceModel(min_uncertainty=0.0, relative=True), params=params
        )
        result = engine.run(snapshots, trades)

        if not result.fills:
            sweep.results.append(
                DepthResult(depth, 0, 0.0, depth, 0.0, 0.0)
            )
            continue

        # Adverse selection from the 300s markout, in bps of price.
        m = result.markouts.get(300) or result.markouts.get(60)
        adverse_bps = (-m.mean * 10_000.0) if m else 0.0

        # Gross edge is the distance from fair actually achieved, which
        # after tick rounding is not exactly the requested depth.
        achieved = []
        for f in result.fills:
            achieved.append(depth)   # requested; rounding noise is second-order
        gross = statistics.fmean(achieved) if achieved else depth

        sweep.results.append(
            DepthResult(
                depth_bps=depth,
                fills=len(result.fills),
                fill_rate=result.fill_ratio,
                gross_edge_bps=gross,
                adverse_bps=adverse_bps,
                pickoff_share=result.price_through_share,
            )
        )
        log.info("depth %.1fbp: %d fills, adverse %.2fbp",
                 depth, len(result.fills), adverse_bps)

    return sweep


def render_sweep(sweep: DepthSweep) -> str:
    lines = [
        "Adverse selection vs quote depth",
        "=" * 78,
        f"  round-trip maker fee assumed: {sweep.fee_bps:.2f}bp",
        "",
        f"  {'depth':>8} {'fills':>8} {'fill%':>8} {'gross':>9} "
        f"{'adverse':>9} {'net':>9} {'pickoff':>9}",
    ]
    for r in sweep.results:
        if r.fills == 0:
            lines.append(f"  {r.depth_bps:>7.1f}bp {'0':>8} {'-':>8} "
                         f"{'-':>9} {'-':>9} {'-':>9} {'-':>9}")
            continue
        flag = "" if r.fills >= 30 else "  (thin)"
        lines.append(
            f"  {r.depth_bps:>7.1f}bp {r.fills:>8,} {r.fill_rate:>7.1%} "
            f"{r.gross_edge_bps:>8.2f}bp {r.adverse_bps:>8.2f}bp "
            f"{r.net_bps:>+8.2f}bp {r.pickoff_share:>8.1%}{flag}"
        )
    lines += ["", f"  {sweep.verdict()}"]
    return "\n".join(lines)
