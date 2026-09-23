"""Does anything we can observe say when to buy, sell, or size down?

Every feature a trader might watch -- momentum, trend, RSI, volatility,
funding, basis, implied volatility, stablecoin flows, exchange premiums --
tested the same way against what actually happened next.

The discipline matters more than the list, because this is the exercise that
produces most of the false "patterns" in trading:

- **Features are fixed before results are seen.** `FEATURES` is the whole
  menu; nothing is added after a look at the answers.
- **Everything is strictly trailing.** A feature on day t uses data up to
  and including day t's close; the target starts after it.
- **Overlap is not evidence.** Daily 30-day forward returns overlap 29/30
  with their neighbours, so 3,000 daily points are about 100 independent
  ones. Information coefficients are averaged across all start offsets and
  judged on the non-overlapping count.
- **Discovery and confirmation use different years.** A feature must be
  significant in the earlier period after a Benjamini-Hochberg correction
  across every test run, then hold the same sign and significance in the
  later period it never saw.
- **Significance is not money.** Survivors get a simple rule backtest in the
  confirmation period, net of switching costs, against buy-and-hold.

The information coefficient (IC) is the Spearman rank correlation between
the feature and the forward outcome. For daily-rebalanced crypto, an IC of
0.05 that survives out of sample is a respectable signal; 0.2 would be
remarkable and should be treated as a bug until proven otherwise.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable

# --------------------------------------------------------------- statistics


def rank(xs: list[float]) -> list[float]:
    """Average ranks, ties shared."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return float("nan")
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def spearman(x: list[float], y: list[float]) -> float:
    return pearson(rank(x), rank(y))


def normal_p_two_sided(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    q = [0.0] * m
    running = 1.0
    for r in range(m, 0, -1):
        i = order[r - 1]
        running = min(running, p_values[i] * m / r)
        q[i] = min(running, 1.0)
    return q


# ------------------------------------------------------------------- series

@dataclass
class Daily:
    """Aligned daily series keyed by ISO date. Missing values are None."""

    dates: list[str]
    cols: dict[str, list[float | None]] = field(default_factory=dict)

    def col(self, name: str) -> list[float | None]:
        return self.cols[name]


def trailing(values: list[float | None], window: int,
             fn: Callable[[list[float]], float]) -> list[float | None]:
    """fn over the last `window` values, inclusive of today; None if any gap."""
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        w = values[i + 1 - window: i + 1]
        out.append(None if any(v is None for v in w) else fn(w))  # type: ignore[arg-type]
    return out


def log_returns(prices: list[float | None]) -> list[float | None]:
    out: list[float | None] = [None]
    for a, b in zip(prices[:-1], prices[1:]):
        out.append(math.log(b / a) if a and b else None)
    return out


def forward_sum(values: list[float | None], h: int) -> list[float | None]:
    """Sum of the next h values, starting tomorrow. Strictly forward."""
    out: list[float | None] = []
    for i in range(len(values)):
        w = values[i + 1: i + 1 + h]
        out.append(sum(w) if len(w) == h and all(v is not None for v in w) else None)  # type: ignore[arg-type]
    return out


def forward_vol(rets: list[float | None], h: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(rets)):
        w = rets[i + 1: i + 1 + h]
        if len(w) == h and all(v is not None for v in w):
            out.append(statistics.pstdev(w) * math.sqrt(365))  # type: ignore[arg-type]
        else:
            out.append(None)
    return out


# ---------------------------------------------------------------- IC engine

@dataclass
class IC:
    feature: str
    target: str
    horizon: int
    ic: float
    n_eff: int
    p: float
    q: float = 1.0

    @property
    def z(self) -> float:
        return self.ic * math.sqrt(max(self.n_eff - 3, 1))


def information_coefficient(
    feature: list[float | None], target: list[float | None], horizon: int,
    *, lo: int = 0, hi: int | None = None,
) -> tuple[float, int]:
    """Spearman IC averaged over all `horizon` start offsets.

    Each offset uses only non-overlapping observations, so every
    correlation is honest on its own; averaging them uses all the data
    without pretending overlapping windows are independent. Returns
    (mean IC, non-overlapping sample size).
    """
    hi = len(feature) if hi is None else hi
    ics, ns = [], []
    for off in range(horizon):
        xs, ys = [], []
        for i in range(lo + off, hi, horizon):
            f, t = feature[i], target[i]
            if f is not None and t is not None:
                xs.append(f)
                ys.append(t)
        if len(xs) >= 20:
            v = spearman(xs, ys)
            if not math.isnan(v):
                ics.append(v)
                ns.append(len(xs))
    if not ics:
        return float("nan"), 0
    return statistics.fmean(ics), int(statistics.fmean(ns))


def ic_test(feature, target, horizon, *, lo=0, hi=None, name="", tname="") -> IC:
    ic, n = information_coefficient(feature, target, horizon, lo=lo, hi=hi)
    if n < 20 or math.isnan(ic):
        return IC(name, tname, horizon, float("nan"), n, 1.0)
    # Fisher-z standard error for a rank correlation.
    z = math.atanh(max(min(ic, 0.999), -0.999)) * math.sqrt(max(n - 3, 1))
    return IC(name, tname, horizon, ic, n, normal_p_two_sided(z))


# ------------------------------------------------------------ rule backtest

@dataclass
class RuleResult:
    name: str
    days: int
    trades: int
    rule_return: float
    hold_return: float
    rule_vol: float
    hold_vol: float
    rule_maxdd: float
    hold_maxdd: float
    exposure: float

    @property
    def rule_sharpe(self) -> float:
        return self.rule_return / self.rule_vol if self.rule_vol else float("nan")

    @property
    def hold_sharpe(self) -> float:
        return self.hold_return / self.hold_vol if self.hold_vol else float("nan")


def _maxdd(curve: list[float]) -> float:
    peak, dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1.0)
    return dd


def rule_backtest(
    signal: list[bool | None], rets: list[float | None], *,
    lo: int, hi: int, cost: float = 0.001, cash_rate: float = 0.0, name: str = "",
) -> RuleResult:
    """Long when signal is True, in cash otherwise, decided on the prior close.

    Position for day i+1 is set by the signal at day i -- no same-day
    lookahead. `cost` is charged on every switch; cash earns `cash_rate`.
    """
    eq, hold = [1.0], [1.0]
    daily_r, daily_h = [], []
    trades, pos, days_in = 0, False, 0
    for i in range(lo, min(hi, len(rets)) - 1):
        s, r = signal[i], rets[i + 1]
        if r is None:
            continue
        want = bool(s) if s is not None else pos
        if want != pos:
            trades += 1
            eq[-1] *= (1.0 - cost)
            pos = want
        rr = (math.exp(r) - 1.0) if pos else cash_rate / 365.0
        days_in += pos
        eq.append(eq[-1] * (1.0 + rr))
        hold.append(hold[-1] * math.exp(r))
        daily_r.append(rr)
        daily_h.append(math.exp(r) - 1.0)
    n = len(daily_r)
    if n < 30:
        return RuleResult(name, n, trades, float("nan"), float("nan"), float("nan"),
                          float("nan"), 0.0, 0.0, 0.0)
    ann = lambda c: c[-1] ** (365.0 / n) - 1.0  # noqa: E731
    return RuleResult(
        name=name, days=n, trades=trades,
        rule_return=ann(eq), hold_return=ann(hold),
        rule_vol=statistics.pstdev(daily_r) * math.sqrt(365),
        hold_vol=statistics.pstdev(daily_h) * math.sqrt(365),
        rule_maxdd=_maxdd(eq), hold_maxdd=_maxdd(hold),
        exposure=days_in / n,
    )


def tercile_cuts(values: list[float | None], lo: int, hi: int) -> tuple[float, float]:
    """Tercile boundaries fitted on [lo, hi) only -- the training period."""
    xs = sorted(v for v in values[lo:hi] if v is not None)
    if len(xs) < 30:
        raise ValueError("too few observations to fit terciles")
    return xs[len(xs) // 3], xs[2 * len(xs) // 3]
