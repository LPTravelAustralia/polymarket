"""What repetition does to an edge -- in both directions.

There is a widespread and completely reasonable intuition that goes: any
single trade is a coin flip, but if I take a small profit over and over and
never sit in a loser, the law of large numbers works for me. It is the
instinct behind scalping, and it is correct *given a positive edge*. Given a
negative one it is exactly backwards, and the size of the mistake grows with
the number of trades rather than shrinking.

The reason is that bankrolls compound multiplicatively. Sequential bets on
the same pot multiply, they do not add, so what accumulates is the **mean of
the logarithm** of the per-trade multiplier, not the mean of the multiplier.
Those two numbers can have opposite signs, and in fat-tailed markets they
routinely do:

    a bet paying +100% or -50% on a fair coin has an arithmetic mean
    of +25% a throw, and drives every bankroll staked on it to zero.

This matters here because the memecoin return distribution is the most
extreme real example available. Measured over 770 call-channel calls and
2.4M trades, a 30-second hold returns **+552% on average** and **-4.0% at
the median**. The mean is genuinely positive. Anyone repeating that trade at
size still goes broke, and this module computes how fast.

It also computes the honest counter-case, because the counter-case is real:
at small enough position sizing the arithmetic mean can dominate and the
geometric growth rate can turn positive. That is the steelman of "lots of
little trades", it is the Kelly criterion, and whether it survives is a
question about fees rather than about nerve. So `optimal_fraction` searches
for it rather than assuming the answer.

**Read the sanity check before believing any fractional-stake number here.**
Fitted to the published pair, this model says a 25% stake compounds to
10^12 over a hundred trades with a zero percent chance of losing money. Four
independent datasets say 94-96% of real memecoin traders lose. Both cannot
be true, and the datasets are the ones counting actual wallets.

The reconstruction fails in a specific and informative way. A +552% *sample*
mean drawn from 770 observations of a distribution this skewed is not an
estimate of the population mean; it is a statement about the largest one or
two observations in that sample, and it moves when you add data. Feed it to
a compounding model and the model prints the wealth of whoever held those
particular outliers. `sanity_check` exists to catch this, and
`truncate` exists because it points straight at the real answer: the mean
lives entirely in a tail that a take-profit rule deliberately cuts off.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

# The published 30-second figures from the call-channel study: buy at the
# exact instant of the call (which no one can do), sell 30 seconds later.
CALL_MEAN_RETURN = 5.522      # +552.2%
CALL_MEDIAN_RETURN = -0.040   # -4.0%

# All-in round-trip cost of a Solana memecoin trade: bot fee, priority fee,
# tip, slippage and MEV. The low end is a quiet launch, the high end a
# contested one.
COST_LOW = 0.042
COST_HIGH = 0.062


@dataclass(frozen=True)
class LogNormalReturns:
    """A fat-tailed return distribution pinned to a mean and a median.

    Lognormal is the right family here for two reasons: returns are bounded
    below at -100% (you cannot lose more than the position), and the shape
    reproduces the defining feature of this market, a mean dragged far above
    the median by a thin right tail.

    Pinning to (mean, median) rather than (mean, stdev) is deliberate. The
    median is the robust statistic and the one a trader actually experiences
    trade after trade; the standard deviation of a distribution like this is
    barely meaningful and is dominated by whichever outliers made the sample.
    """

    mu: float      # mean of log(1 + R)
    sigma: float   # stdev of log(1 + R)

    @classmethod
    def from_mean_and_median(cls, mean: float, median: float) -> "LogNormalReturns":
        if median <= -1.0 or mean <= -1.0:
            raise ValueError("returns must exceed -100%")
        mu = math.log1p(median)
        # mean = exp(mu + sigma^2/2) - 1
        excess = math.log1p(mean) - mu
        if excess <= 0:
            raise ValueError("mean must exceed median for a right-skewed fit")
        return cls(mu=mu, sigma=math.sqrt(2.0 * excess))

    @property
    def arithmetic_mean(self) -> float:
        return math.exp(self.mu + self.sigma ** 2 / 2.0) - 1.0

    @property
    def median(self) -> float:
        return math.exp(self.mu) - 1.0

    @property
    def geometric_mean(self) -> float:
        """Growth per trade when the whole bankroll rides on each one.

        For a lognormal this equals the median, which is the cleanest
        statement of the whole problem: bet everything repeatedly and you
        compound the typical trade, not the average one.
        """
        return math.exp(self.mu) - 1.0

    def draw(self, rng: random.Random) -> float:
        return math.exp(rng.gauss(self.mu, self.sigma)) - 1.0


@dataclass
class RepetitionResult:
    trades: int
    fraction: float
    cost: float
    median_terminal: float
    mean_terminal: float
    p_below_start: float
    p_ruin: float          # bankroll below 1% of starting
    log_growth_per_trade: float

    @property
    def median_total_return(self) -> float:
        return self.median_terminal - 1.0

    def line(self) -> str:
        return (
            f"    stake {self.fraction:>5.1%}  "
            f"log growth/trade {self.log_growth_per_trade:>+8.4f}  "
            f"median x{self.median_terminal:>9.2e}  "
            f"mean x{self.mean_terminal:>9.2e}  "
            f"lose money {self.p_below_start:>5.1%}  "
            f"wiped out {self.p_ruin:>5.1%}"
        )


def simulate_repetition(
    dist: LogNormalReturns,
    *,
    trades: int = 100,
    fraction: float = 1.0,
    cost: float = COST_LOW,
    paths: int = 20_000,
    seed: int = 7,
) -> RepetitionResult:
    """Run `paths` bankrolls through `trades` repetitions of the same bet.

    `fraction` is the share of the bankroll staked on each trade, so 1.0 is
    "roll it all forward" and 0.02 is "risk 2% a go". `cost` is the all-in
    round-trip execution charged on the staked amount.

    Reported as a distribution rather than an average, because in a market
    this skewed the average terminal wealth is a number essentially nobody
    experiences -- it is one path in ten thousand carrying the mean.
    """
    rng = random.Random(seed)
    terminals: list[float] = []
    log_sum = 0.0
    for _ in range(paths):
        wealth = 1.0
        for _ in range(trades):
            gross = dist.draw(rng)
            net = (1.0 + gross) * (1.0 - cost) - 1.0
            mult = 1.0 + fraction * net
            if mult <= 1e-12:
                wealth = 0.0
                break
            wealth *= mult
        terminals.append(wealth)
        log_sum += math.log(wealth) if wealth > 0 else -math.inf

    finite = [math.log(w) for w in terminals if w > 0]
    growth = (statistics.fmean(finite) / trades) if finite else -math.inf
    if len(finite) < len(terminals):
        growth = -math.inf

    return RepetitionResult(
        trades=trades,
        fraction=fraction,
        cost=cost,
        median_terminal=statistics.median(terminals),
        mean_terminal=statistics.fmean(terminals),
        p_below_start=sum(1 for w in terminals if w < 1.0) / len(terminals),
        p_ruin=sum(1 for w in terminals if w < 0.01) / len(terminals),
        log_growth_per_trade=growth,
    )


def optimal_fraction(
    dist: LogNormalReturns,
    *,
    cost: float = COST_LOW,
    samples: int = 200_000,
    seed: int = 11,
) -> tuple[float, float]:
    """Find the stake that maximises long-run growth, if one exists.

    This is the steelman: if any position size makes repeated betting on this
    distribution compound upwards, it is here. Returns (fraction, growth per
    trade); a growth rate at or below zero means no stake works and the
    answer to "what if I size smaller" is that smaller only loses slower.
    """
    rng = random.Random(seed)
    draws = [(1.0 + dist.draw(rng)) * (1.0 - cost) - 1.0 for _ in range(samples)]

    def growth(f: float) -> float:
        total = 0.0
        for r in draws:
            m = 1.0 + f * r
            if m <= 1e-12:
                return -math.inf
            total += math.log(m)
        return total / len(draws)

    best_f, best_g = 0.0, 0.0
    f = 0.001
    while f <= 1.0:
        g = growth(f)
        if g > best_g:
            best_f, best_g = f, g
        f = f * 1.35 if f < 0.05 else f + 0.02
    return best_f, best_g


@dataclass(frozen=True)
class TruncatedReturns:
    """What an exit rule does to the distribution it is applied to.

    A take-profit at +p converts every outcome above +p into exactly +p. On a
    symmetric distribution that costs a little. On this one it is the whole
    proposition, because the arithmetic mean sits far out in the right tail:
    capping at +50% discards every 10x and 100x, which is where all of the
    positive expectation was.

    The stop-loss is modelled as *optimistic*: it assumes you exit at exactly
    -s. In a token doing -80% in one block, through a bonding curve, against
    the same latency that made copy trading impossible, you do not. Treat the
    downside here as a floor on the real one.
    """

    take_profit: float | None
    stop_loss: float | None
    mean: float
    median: float
    win_rate: float
    tail_mean_lost: float   # mean removed by the cap

    def line(self) -> str:
        tp = f"+{self.take_profit:.0%}" if self.take_profit is not None else "none"
        sl = f"-{self.stop_loss:.0%}" if self.stop_loss is not None else "none"
        return (f"    TP {tp:>6}  SL {sl:>6}  ->  mean {self.mean:>+9.2%}  "
                f"median {self.median:>+7.2%}  win {self.win_rate:>5.1%}  "
                f"(mean given up to the cap: {self.tail_mean_lost:>+9.2%})")


def truncate(
    dist: LogNormalReturns,
    *,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    cost: float = COST_LOW,
    samples: int = 400_000,
    seed: int = 13,
) -> TruncatedReturns:
    """Apply a take-profit / stop-loss rule and re-measure the distribution.

    This is the actual proposal being tested: get in, take a small gain, get
    out before it falls over, repeat. Costs are charged on every trade,
    because every trade is a round trip whether it hit the target or the
    stop.
    """
    rng = random.Random(seed)
    raw: list[float] = []
    capped: list[float] = []
    for _ in range(samples):
        g = dist.draw(rng)
        raw.append(g)
        if take_profit is not None and g > take_profit:
            g = take_profit
        if stop_loss is not None and g < -stop_loss:
            g = -stop_loss
        capped.append((1.0 + g) * (1.0 - cost) - 1.0)

    gross_mean = statistics.fmean((1.0 + g) * (1.0 - cost) - 1.0 for g in raw)
    return TruncatedReturns(
        take_profit=take_profit,
        stop_loss=stop_loss,
        mean=statistics.fmean(capped),
        median=statistics.median(capped),
        win_rate=sum(1 for r in capped if r > 0) / len(capped),
        tail_mean_lost=statistics.fmean(capped) - gross_mean,
    )


def sanity_check(
    dist: LogNormalReturns,
    *,
    observed_loss_rate: float = 0.94,
    trades: int = 100,
    fraction: float = 1.0,
    cost: float = COST_LOW,
) -> str:
    """Does the fitted distribution reproduce the outcome actually observed?

    A per-trade distribution inferred from a sample mean is only worth
    simulating if it predicts the population result that four separate
    datasets already measured. When it does not, the sample mean is the
    thing to distrust, not the datasets.
    """
    got = simulate_repetition(dist, trades=trades, fraction=fraction,
                              cost=cost, paths=20_000).p_below_start
    gap = got - observed_loss_rate
    verdict = "CONSISTENT" if abs(gap) < 0.10 else "FAILS"
    return (
        f"  observed loss rate {observed_loss_rate:.0%}; model predicts "
        f"{got:.0%} at a {fraction:.0%} stake over {trades} trades -> {verdict}"
        + ("" if verdict == "CONSISTENT" else
           "\n  -> the fitted mean is not a population parameter. Any "
           "fractional-stake\n     result below inherits that and should not "
           "be acted on.")
    )


def render_repetition(
    dist: LogNormalReturns, *, cost: float = COST_LOW, trades: int = 100
) -> str:
    lines = [
        "Repeating the trade",
        "=" * 78,
        f"  per-trade gross return: mean {dist.arithmetic_mean:>+8.1%}, "
        f"median {dist.median:>+7.1%}  (sigma of log {dist.sigma:.2f})",
        f"  all-in round-trip cost: {cost:.1%}",
        f"  trades simulated:       {trades}",
        "",
    ]
    for frac in (1.0, 0.25, 0.10, 0.05, 0.02, 0.01):
        lines.append(simulate_repetition(
            dist, trades=trades, fraction=frac, cost=cost).line())

    f, g = optimal_fraction(dist, cost=cost)
    lines += ["", f"  best stake found: {f:.1%} of bankroll, "
                  f"log growth {g:+.5f} per trade"]
    if g <= 0:
        lines.append("  -> no stake compounds upward. Sizing smaller only "
                     "loses more slowly.")
    else:
        lines.append(f"  -> compounds at {math.exp(g) - 1:+.3%} per trade at "
                     f"that stake, and only at that stake.")

    lines += ["", "  Sanity check against observed outcomes", "  " + "-" * 40,
              sanity_check(dist, cost=cost, trades=trades)]

    lines += ["", "  Take a small profit and cut losses early", "  " + "-" * 40]
    for tp, sl in ((0.20, 0.10), (0.50, 0.20), (1.00, 0.30),
                   (2.00, 0.50), (None, None)):
        lines.append(truncate(dist, take_profit=tp, stop_loss=sl,
                              cost=cost).line())
    lines.append("  -> the cap is where the mean lived. Exiting early removes "
                 "the outcomes")
    lines.append("     that made the average positive and keeps every cost.")
    return "\n".join(lines)
