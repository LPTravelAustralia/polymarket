"""Are Polymarket prices honest probabilities -- and is the gap tradeable?

The best-documented pattern in betting markets is the favourite-longshot
bias: longshots are overpriced and favourites underpriced, because people
enjoy buying lottery tickets. If Polymarket has it, then contracts at 5c win
less than 5% of the time and contracts at 95c win more than 95%, and the
side to be on is the boring one.

That matters here for a specific reason. The complete-set strategy in
STRATEGY.md died because fees at mid prices consumed its edge, and
STRATEGY.md named two ways out that were never tested: **trade away from
0.50**, where the `p(1-p)` fee curve collapses, and **trade fee-free
categories**. A calibration gap in the tails is exactly an edge that lives
where the fee does not.

The test is simple and easy to get wrong in three ways, each handled here:

1. **Outcomes are not independent.** A 20-candidate election produces 19
   "No"s from one event. Treating them as 20 draws makes the error bars
   several times too narrow. Uncertainty is bootstrapped by *event*.
2. **Decided contracts are not predictions.** A contract trading at 99.5c
   after the game has ended wins 100% of the time and "beats its price" --
   that is resolution lag, a different trade with different risk. Prices
   beyond `decided` are reported separately, not pooled.
3. **Many bands, many chances.** Testing a dozen price bands across several
   categories will find a "significant" band by luck. p-values are
   corrected with Benjamini-Hochberg before anything is called real.

Costs are charged per contract at its own published taker rate and the
`p(1-p)` curve, plus half the quoted spread.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contract:
    """One YES contract, observed `hold_days` before the market closed."""

    market_id: str
    event_id: str
    price: float          # YES price at the observation point
    won: bool             # did YES resolve true
    fee_rate: float       # taker rate from the market's own fee schedule
    category: str
    hold_days: float
    volume: float = 0.0

    @property
    def fee_per_share(self) -> float:
        p = min(max(self.price, 0.0), 1.0)
        return self.fee_rate * p * (1.0 - p)


DEFAULT_BANDS = (0.0, 0.03, 0.07, 0.15, 0.30, 0.45, 0.55, 0.70, 0.85, 0.93,
                 0.97, 1.0)


@dataclass
class BandResult:
    lo: float
    hi: float
    n: int
    events: int
    mean_price: float
    win_rate: float
    mean_fee: float
    half_spread: float
    ci_lo: float           # 95% CI on gross edge (win - price), by event
    ci_hi: float
    p_value: float         # two-sided, gross edge == 0, event bootstrap
    q_value: float = 1.0   # Benjamini-Hochberg across all bands tested
    mean_hold_days: float = 0.0

    @property
    def gross_edge(self) -> float:
        """Positive: YES underpriced (buy YES). Negative: buy NO."""
        return self.win_rate - self.mean_price

    @property
    def side(self) -> str:
        return "YES" if self.gross_edge >= 0 else "NO"

    @property
    def net_edge(self) -> float:
        """Per share, on the better side, after fee and half-spread."""
        return abs(self.gross_edge) - self.mean_fee - self.half_spread

    @property
    def return_on_stake(self) -> float:
        """Net edge divided by what the better side costs to buy."""
        cost = self.mean_price if self.side == "YES" else 1.0 - self.mean_price
        return self.net_edge / cost if cost > 0 else 0.0

    @property
    def significant(self) -> bool:
        return self.q_value < 0.05


def _band_stats(cs: list[Contract]) -> tuple[float, float, float]:
    """(win rate, mean price, gross edge) for a list of contracts."""
    w = sum(1 for c in cs if c.won) / len(cs)
    p = statistics.fmean(c.price for c in cs)
    return w, p, w - p


def _event_bootstrap(cs: list[Contract], n_boot: int, rng: random.Random
                     ) -> list[float]:
    by_event: dict[str, list[Contract]] = {}
    for c in cs:
        by_event.setdefault(c.event_id or c.market_id, []).append(c)
    groups = list(by_event.values())
    edges = []
    for _ in range(n_boot):
        sample: list[Contract] = []
        for _ in range(len(groups)):
            sample.extend(groups[rng.randrange(len(groups))])
        edges.append(_band_stats(sample)[2])
    return edges


def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else float("-inf")
    if p >= 1.0:
        return 0.0 if k == n else float("-inf")
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def binomial_two_sided_p(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial test: P(an outcome at least as unlikely)."""
    lp = [_log_pmf(i, n, p) for i in range(n + 1)]
    obs = lp[k]
    return min(1.0, sum(math.exp(v) for v in lp if v <= obs + 1e-9))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact confidence interval for a binomial proportion."""
    def cdf(p: float, upto: int) -> float:
        return sum(math.exp(_log_pmf(i, n, p)) for i in range(upto + 1))

    def solve(f, lo=0.0, hi=1.0):
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda q: 1.0 - cdf(q, k - 1) >= alpha / 2)
    upper = 1.0 if k == n else solve(lambda q: cdf(q, k) <= alpha / 2)
    return lower, upper


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """q-values: the false-discovery rate at which each test is significant."""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, p_values[i] * m / rank)
        q[i] = min(running, 1.0)
    return q


def calibrate(
    contracts: list[Contract],
    bands: tuple[float, ...] = DEFAULT_BANDS,
    *,
    half_spread: float = 0.005,
    decided: float = 0.015,
    min_n: int = 30,
    n_boot: int = 1000,
    seed: int = 17,
) -> tuple[list[BandResult], list[Contract]]:
    """Calibration by price band, with event-clustered uncertainty.

    Returns (bands, decided_contracts). Contracts priced within `decided` of
    0 or 1 are held out of the bands and returned for separate treatment.
    """
    rng = random.Random(seed)
    live = [c for c in contracts if decided <= c.price <= 1.0 - decided]
    held = [c for c in contracts if not (decided <= c.price <= 1.0 - decided)]

    results: list[BandResult] = []
    for lo, hi in zip(bands[:-1], bands[1:]):
        cs = [c for c in live if lo <= c.price < hi or (hi == 1.0 and c.price == 1.0)]
        if len(cs) < min_n:
            continue
        w, p, e = _band_stats(cs)
        boot = sorted(_event_bootstrap(cs, n_boot, rng))
        lo_ci = boot[int(0.025 * n_boot)]
        hi_ci = boot[int(0.975 * n_boot) - 1]
        # Two-sided p: how often the bootstrap distribution, recentred on
        # zero, is at least as extreme as the observed edge.
        centred = [b - e for b in boot]
        pv = sum(1 for b in centred if abs(b) >= abs(e)) / n_boot
        # The bootstrap cannot see uncertainty it has no variation to
        # resample: a band where every contract won returns a zero-width
        # interval and a tiny p-value. 70 of 70 at 97.7c is what a 97.7%
        # true rate produces a fifth of the time. The exact binomial test is
        # a floor -- clustering can only widen uncertainty, never narrow it --
        # so the wider of the two intervals and the larger p-value are used.
        k = sum(1 for c in cs if c.won)
        cp_lo, cp_hi = clopper_pearson(k, len(cs))
        lo_ci = min(lo_ci, cp_lo - p)
        hi_ci = max(hi_ci, cp_hi - p)
        pv = max(pv, binomial_two_sided_p(k, len(cs), min(max(p, 1e-9), 1 - 1e-9)))
        results.append(BandResult(
            lo=lo, hi=hi, n=len(cs),
            events=len({c.event_id or c.market_id for c in cs}),
            mean_price=p, win_rate=w,
            mean_fee=statistics.fmean(c.fee_per_share for c in cs),
            half_spread=half_spread, ci_lo=lo_ci, ci_hi=hi_ci,
            p_value=max(pv, 1.0 / n_boot),
            mean_hold_days=statistics.fmean(c.hold_days for c in cs),
        ))
    for r, q in zip(results, benjamini_hochberg([r.p_value for r in results])):
        r.q_value = q
    return results, held


def render_calibration(results: list[BandResult], *, title: str = "") -> str:
    lines = [
        title or "Calibration by price band",
        "=" * 96,
        f"  {'band':<11}{'n':>6}{'events':>8}{'price':>8}{'won':>8}"
        f"{'gross':>8}{'95% CI':>17}{'fee':>7}{'net':>8}{'side':>6}{'q':>7}",
    ]
    for r in results:
        flag = "  *" if r.significant and r.net_edge > 0 else ""
        lines.append(
            f"  {r.lo:>4.2f}-{r.hi:<5.2f}{r.n:>6}{r.events:>8}{r.mean_price:>8.3f}"
            f"{r.win_rate:>8.3f}{r.gross_edge:>+8.3f}"
            f"  [{r.ci_lo:+.3f},{r.ci_hi:+.3f}]{r.mean_fee:>7.4f}"
            f"{r.net_edge:>+8.3f}{r.side:>6}{r.q_value:>7.3f}{flag}")
    lines.append("  * = survives the false-discovery correction AND clears "
                 "fee plus half-spread")
    return "\n".join(lines)


@dataclass
class SplitResult:
    """Did a band's edge hold up out of sample?"""
    band: tuple[float, float]
    train: BandResult | None
    test: BandResult | None
    notes: list[str] = field(default_factory=list)

    @property
    def replicated(self) -> bool:
        if not (self.train and self.test):
            return False
        same_side = (self.train.gross_edge >= 0) == (self.test.gross_edge >= 0)
        return same_side and self.test.net_edge > 0 and self.test.ci_lo * self.test.ci_hi > 0
