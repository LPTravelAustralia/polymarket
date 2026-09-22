"""Funding-rate harvest: does the carry survive the cost of carrying it?

The trade is the oldest one in crypto. Perpetual futures have no expiry, so
they are tethered to spot by a periodic payment: when the perp trades above
the index, longs pay shorts. Short the perp, buy the spot, hold a position
with no price exposure, and collect that payment.

The number everyone quotes is the gross funding rate -- "11% APR" -- and it
is real. It is also not the return. Three things sit between it and the
money:

1. **Four legs of fees.** The position is two instruments and it has to be
   opened and closed, so a round trip pays perp fees twice and spot fees
   twice. At a 0.045% perp taker and a 0.10% spot taker that is 0.29% before
   slippage. Against 11% APR (0.0301% a day) the position must survive
   roughly ten days just to repay its own execution.

2. **Basis drift.** Delta-neutral means the spot and perp price moves cancel.
   What does not cancel is the gap between them. Enter when the perp is 0.05%
   rich and exit when it is 0.20% rich and you have handed back six days of
   funding. This is the term that gets left out of every spreadsheet, and it
   is measurable: Hyperliquid publishes `premium` alongside every hourly
   funding print, which is exactly that gap.

3. **Capital, not notional.** APR on notional is not APR on money. The spot
   leg is bought outright and the perp leg needs margin, so a dollar of
   notional ties up more than a dollar.

The honest calculation is therefore

    net = sum(hourly funding) + (premium_in - premium_out) - fees

per unit of notional, divided by the capital actually committed. Everything
here computes that, over real funding history, with entry decisions made only
from data available at the time.

Entry rules use a *trailing* window on purpose. A rule that enters when the
next fortnight of funding is high is not a strategy, it is a lookahead, and
it is the single easiest way to manufacture a carry business that does not
exist.
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field

from .hyperliquid import HyperliquidAPI, _f

log = logging.getLogger(__name__)

HOURS_PER_YEAR = 24 * 365

# Published base-tier defaults. Real tiers are better; these are the
# conservative fallback, and the whole point of the exercise is that the
# answer is dominated by them.
DEFAULT_PERP_TAKER = 0.00045     # Hyperliquid perp taker, 0.045%
DEFAULT_SPOT_TAKER = 0.00100     # major CEX spot taker, 0.10%

# Hyperliquid's funding history endpoint returns at most 500 rows, and
# funding prints hourly, so a request can span no more than ~20 days.
MAX_ROWS_PER_REQUEST = 500
REQUEST_SPAN_HOURS = 480


@dataclass(frozen=True)
class FundingPoint:
    """One hourly funding print.

    `rate` is the hourly rate paid by longs to shorts when positive, so a
    short perp position earns `rate` per hour per unit of notional.

    `premium` is (mark - index) / index at that hour: how rich the perp is.
    A short is opened at the prevailing premium and closed at another one,
    and the difference is a real P&L term, not a rounding detail.
    """

    ts_ms: int
    rate: float
    premium: float

    @property
    def apr(self) -> float:
        return self.rate * HOURS_PER_YEAR


@dataclass
class FundingSeries:
    coin: str
    points: list[FundingPoint] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.points)

    @property
    def hours(self) -> int:
        return len(self.points)

    @property
    def mean_apr(self) -> float:
        return statistics.fmean(p.apr for p in self.points) if self.points else 0.0

    @property
    def median_apr(self) -> float:
        return statistics.median(p.apr for p in self.points) if self.points else 0.0

    @property
    def positive_share(self) -> float:
        """Share of hours a short would have been paid rather than charged."""
        if not self.points:
            return 0.0
        return sum(1 for p in self.points if p.rate > 0) / len(self.points)

    def buy_and_hold_apr(self) -> float:
        """Gross funding from holding the whole window, annualised.

        Gross: no fees, no basis. The number the marketing uses.
        """
        if not self.points:
            return 0.0
        return sum(p.rate for p in self.points) / len(self.points) * HOURS_PER_YEAR

    def trailing_apr(self, index: int, lookback: int) -> float | None:
        """Annualised funding over the `lookback` hours ending at `index`.

        Strictly backward-looking: this is what a decision at `index` is
        allowed to see.
        """
        if index < lookback:
            return None
        window = self.points[index - lookback: index]
        if not window:
            return None
        return statistics.fmean(p.rate for p in window) * HOURS_PER_YEAR


@dataclass(frozen=True)
class HarvestCosts:
    """Everything between the funding rate and the bank balance.

    Slippage defaults are deliberately small (2bp a leg). They are not a
    measurement -- no book data is used here -- and on a thin coin they will
    be far too kind. The sensitivity table exists because of that.
    """

    perp_taker: float = DEFAULT_PERP_TAKER
    spot_taker: float = DEFAULT_SPOT_TAKER
    perp_slippage: float = 0.0002
    spot_slippage: float = 0.0002

    # Spot bought outright (1.0) plus margin posted against the perp short.
    # 0.25 is 4x leverage on the hedge leg, which is already aggressive when
    # the spot collateral sits at a different venue and cannot rescue it.
    capital_multiplier: float = 1.25

    @property
    def one_leg(self) -> float:
        return (self.perp_taker + self.perp_slippage
                + self.spot_taker + self.spot_slippage)

    @property
    def round_trip(self) -> float:
        """Cost of opening and closing the pair, as a fraction of notional."""
        return 2.0 * self.one_leg

    def breakeven_hours(self, apr: float) -> float | None:
        """How long the position must survive to repay its own execution."""
        if apr <= 0:
            return None
        return self.round_trip / (apr / HOURS_PER_YEAR)


@dataclass
class HarvestTrade:
    """One delta-neutral hold, priced end to end."""

    coin: str
    entry_ts: int
    exit_ts: int
    hours: int
    gross_funding: float      # summed hourly rates, per unit notional
    basis_pnl: float          # premium_in - premium_out
    cost: float               # round-trip fees + slippage
    exit_reason: str

    @property
    def net(self) -> float:
        return self.gross_funding + self.basis_pnl - self.cost


@dataclass
class HarvestResult:
    coin: str
    trades: list[HarvestTrade] = field(default_factory=list)
    costs: HarvestCosts = field(default_factory=HarvestCosts)
    window_hours: int = 0
    gross_buy_and_hold_apr: float = 0.0

    # A verdict off three trades is noise. Carry is a slow trade and a year
    # of hourly data yields few independent holds, which is itself part of
    # the answer.
    MIN_TRADES_FOR_VERDICT = 8

    @property
    def hours_in_market(self) -> int:
        return sum(t.hours for t in self.trades)

    @property
    def utilisation(self) -> float:
        return self.hours_in_market / self.window_hours if self.window_hours else 0.0

    @property
    def total_net(self) -> float:
        return sum(t.net for t in self.trades)

    @property
    def total_gross(self) -> float:
        return sum(t.gross_funding for t in self.trades)

    @property
    def total_basis(self) -> float:
        return sum(t.basis_pnl for t in self.trades)

    @property
    def total_cost(self) -> float:
        return sum(t.cost for t in self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t.net > 0) / len(self.trades)

    @property
    def net_apr_on_capital(self) -> float:
        """Annualised over the *whole window*, not just time in market.

        Capital sitting idle between trades earns nothing, and a strategy in
        the market 12% of the time cannot claim the APR it earns while there.
        """
        if not self.window_hours:
            return 0.0
        per_hour = self.total_net / self.window_hours
        return per_hour * HOURS_PER_YEAR / self.costs.capital_multiplier

    @property
    def net_apr_while_deployed(self) -> float:
        """Annualised over time in market. Flattering; reported for contrast."""
        if not self.hours_in_market:
            return 0.0
        per_hour = self.total_net / self.hours_in_market
        return per_hour * HOURS_PER_YEAR / self.costs.capital_multiplier

    @property
    def worst_trade(self) -> HarvestTrade | None:
        return min(self.trades, key=lambda t: t.net) if self.trades else None

    @property
    def cost_share_of_gross(self) -> float:
        """What fraction of the gross carry execution ate."""
        if self.total_gross <= 0:
            return float("inf")
        return self.total_cost / self.total_gross

    @property
    def is_conclusive(self) -> bool:
        return len(self.trades) >= self.MIN_TRADES_FOR_VERDICT


def fetch_funding_history(
    api: HyperliquidAPI, coin: str, *, days: int = 365, pause: float = 0.15
) -> FundingSeries:
    """Pull hourly funding, paging backwards through the row cap.

    A year of hourly prints is ~19 requests per coin, and a universe scan is
    several hundred back to back. `pause` keeps that under the venue's rate
    limit; without it the scan gets a 429 partway through and the partial
    series silently shortens the measurement window.
    """
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86_400_000
    span_ms = REQUEST_SPAN_HOURS * 3_600_000

    seen: dict[int, FundingPoint] = {}
    cursor = start_ms
    while cursor < now_ms:
        end = min(cursor + span_ms, now_ms)
        rows = api._post({
            "type": "fundingHistory",
            "coin": coin,
            "startTime": cursor,
            "endTime": end,
        })
        if not isinstance(rows, list):
            log.warning("%s: unexpected funding payload", coin)
            break
        for r in rows:
            ts = int(_f(r.get("time")))
            seen[ts] = FundingPoint(
                ts_ms=ts,
                rate=_f(r.get("fundingRate")),
                premium=_f(r.get("premium")),
            )
        if len(rows) >= MAX_ROWS_PER_REQUEST:
            # Cap hit: advance only as far as we actually got.
            cursor = max(int(_f(r.get("time"))) for r in rows) + 1
        else:
            cursor = end + 1
        if pause:
            time.sleep(pause)

    points = [seen[k] for k in sorted(seen)]
    log.info("%s: %d hourly funding prints", coin, len(points))
    return FundingSeries(coin=coin, points=points)


def simulate_harvest(
    series: FundingSeries,
    *,
    costs: HarvestCosts | None = None,
    entry_apr: float = 0.10,
    exit_apr: float = 0.02,
    lookback_hours: int = 24,
    min_hold_hours: int = 8,
    max_hold_hours: int = 24 * 30,
) -> HarvestResult:
    """Replay a carry rule over real funding history.

    Enter short-perp/long-spot when trailing funding is rich enough to be
    worth the execution; hold while it stays above `exit_apr`; exit on decay,
    on the hold cap, or at the end of the data.

    `min_hold_hours` stops the rule thrashing in and out on a rate that
    oscillates around the exit threshold, which would pay the round trip
    repeatedly for nothing. It is a cost control, not an edge.
    """
    costs = costs or HarvestCosts()
    result = HarvestResult(
        coin=series.coin,
        costs=costs,
        window_hours=series.hours,
        gross_buy_and_hold_apr=series.buy_and_hold_apr(),
    )
    if series.hours <= lookback_hours:
        return result

    i = lookback_hours
    n = series.hours
    while i < n:
        trailing = series.trailing_apr(i, lookback_hours)
        if trailing is None or trailing < entry_apr:
            i += 1
            continue

        entry = series.points[i]
        accrued = 0.0
        held = 0
        reason = "end of data"
        j = i
        while j < n:
            accrued += series.points[j].rate
            held += 1
            j += 1
            if held >= max_hold_hours:
                reason = "max hold"
                break
            if held >= min_hold_hours:
                t = series.trailing_apr(j, lookback_hours)
                if t is not None and t < exit_apr:
                    reason = "funding decayed"
                    break

        exit_point = series.points[min(j, n - 1)]
        result.trades.append(HarvestTrade(
            coin=series.coin,
            entry_ts=entry.ts_ms,
            exit_ts=exit_point.ts_ms,
            hours=held,
            gross_funding=accrued,
            basis_pnl=entry.premium - exit_point.premium,
            cost=costs.round_trip,
            exit_reason=reason,
        ))
        i = j

    return result


def simulate_always_on(
    series: FundingSeries, *, costs: HarvestCosts | None = None
) -> HarvestResult:
    """The passive benchmark: enter once, hold the window, pay once.

    Worth computing because it is the hardest version to beat. Any rule that
    times entries must beat it by more than the extra round trips it pays,
    and most do not.
    """
    costs = costs or HarvestCosts()
    result = HarvestResult(
        coin=series.coin,
        costs=costs,
        window_hours=series.hours,
        gross_buy_and_hold_apr=series.buy_and_hold_apr(),
    )
    if series.hours < 2:
        return result
    first, last = series.points[0], series.points[-1]
    result.trades.append(HarvestTrade(
        coin=series.coin,
        entry_ts=first.ts_ms,
        exit_ts=last.ts_ms,
        hours=series.hours,
        gross_funding=sum(p.rate for p in series.points),
        basis_pnl=first.premium - last.premium,
        cost=costs.round_trip,
        exit_reason="end of data",
    ))
    return result


@dataclass
class CrossSectionalResult:
    """Hold the richest N coins, rebalance periodically.

    This is what a real basis fund does, and it is the only version of the
    trade with a plausible route to beating the passive benchmark: not timing
    *when* to be in carry, but choosing *which* carry to be in. It also has
    the only realistic cost profile, because rebalancing charges execution
    solely on the names that actually change.
    """

    top_n: int
    rebalance_hours: int
    periods: int = 0
    window_hours: int = 0
    gross: float = 0.0
    basis: float = 0.0
    cost: float = 0.0
    turnover_legs: int = 0
    costs: HarvestCosts = field(default_factory=HarvestCosts)
    period_returns: list[float] = field(default_factory=list)

    @property
    def net(self) -> float:
        return self.gross + self.basis - self.cost

    @property
    def net_apr_on_capital(self) -> float:
        if not self.window_hours:
            return 0.0
        return (self.net / self.window_hours * HOURS_PER_YEAR
                / self.costs.capital_multiplier)

    @property
    def win_rate(self) -> float:
        if not self.period_returns:
            return 0.0
        return sum(1 for r in self.period_returns if r > 0) / len(self.period_returns)

    @property
    def worst_period(self) -> float:
        return min(self.period_returns) if self.period_returns else 0.0


def simulate_cross_sectional(
    series_by_coin: dict[str, FundingSeries],
    *,
    top_n: int = 5,
    rebalance_hours: int = 24 * 30,
    lookback_hours: int = 24 * 30,
    costs: HarvestCosts | None = None,
) -> CrossSectionalResult:
    """Rank on trailing funding, hold the top N, rebalance on a fixed clock.

    Selection uses only the trailing window, so a coin is chosen for what it
    paid before the holding period, never during it. Execution is charged per
    leg that actually changes hands: names carried across a rebalance pay
    nothing, which is the whole advantage of this shape over a timing rule.
    """
    costs = costs or HarvestCosts()

    # Align on the timestamps every coin has, so a name with a short history
    # cannot silently drop out of the ranking mid-window.
    common: set[int] | None = None
    for s in series_by_coin.values():
        stamps = {p.ts_ms for p in s.points}
        common = stamps if common is None else (common & stamps)
    if not common:
        return CrossSectionalResult(top_n=top_n, rebalance_hours=rebalance_hours,
                                    costs=costs)

    axis = sorted(common)
    by_coin: dict[str, dict[int, FundingPoint]] = {
        c: {p.ts_ms: p for p in s.points} for c, s in series_by_coin.items()
    }

    result = CrossSectionalResult(
        top_n=top_n, rebalance_hours=rebalance_hours,
        window_hours=len(axis) - lookback_hours, costs=costs,
    )
    if result.window_hours <= rebalance_hours:
        result.window_hours = 0
        return result

    held: set[str] = set()
    i = lookback_hours
    while i + rebalance_hours <= len(axis):
        window = axis[i - lookback_hours: i]
        ranked = sorted(
            by_coin,
            key=lambda c: -statistics.fmean(by_coin[c][t].rate for t in window),
        )
        target = set(ranked[:top_n])

        # Only the difference trades.
        churn = len(target - held) + len(held - target)
        result.turnover_legs += churn
        result.cost += churn * costs.one_leg / top_n

        hold = axis[i: i + rebalance_hours]
        entry, exit_ = hold[0], hold[-1]
        period = 0.0
        for c in target:
            g = sum(by_coin[c][t].rate for t in hold)
            b = by_coin[c][entry].premium - by_coin[c][exit_].premium
            period += (g + b) / top_n
            result.gross += g / top_n
            result.basis += b / top_n

        result.period_returns.append(period - churn * costs.one_leg / top_n)
        result.periods += 1
        held = target
        i += rebalance_hours

    # Unwind whatever is still on at the end.
    result.turnover_legs += len(held)
    result.cost += len(held) * costs.one_leg / top_n
    result.window_hours = result.periods * rebalance_hours
    return result


def render_cross_sectional(r: CrossSectionalResult, *, universe: int = 0) -> str:
    return "\n".join([
        f"  top {r.top_n} of {universe or '?'}, rebalanced every "
        f"{r.rebalance_hours // 24}d",
        f"    periods             {r.periods}  "
        f"({r.turnover_legs} position changes)",
        f"    gross funding       {r.gross:>+8.4%}",
        f"    basis drift         {r.basis:>+8.4%}",
        f"    execution           {-r.cost:>+8.4%}",
        f"    net                 {r.net:>+8.4%}",
        f"    NET APR ON CAPITAL  {r.net_apr_on_capital:>+8.2%}",
        f"    periods positive    {r.win_rate:>8.0%}  "
        f"(worst {r.worst_period:+.3%})",
    ])


def render_harvest(result: HarvestResult, *, label: str = "") -> str:
    c = result.costs
    be = c.breakeven_hours(result.gross_buy_and_hold_apr)
    head = f"{result.coin}{(' ' + label) if label else ''}"
    lines = [
        f"  {head}",
        f"    window              {result.window_hours:,}h "
        f"({result.window_hours / 24:.0f}d)",
        f"    gross funding APR   {result.gross_buy_and_hold_apr:>8.2%}  "
        f"(the quoted number)",
        f"    round-trip cost     {c.round_trip:>8.4%} of notional"
        + (f"  -> breakeven {be:.0f}h ({be / 24:.1f}d)" if be else ""),
    ]
    if not result.trades:
        lines.append("    no trades -- funding never cleared the entry threshold")
        return "\n".join(lines)

    lines += [
        f"    trades              {len(result.trades):,}  "
        f"(median hold {statistics.median(t.hours for t in result.trades):.0f}h, "
        f"in market {result.utilisation:.0%} of the window)",
        f"    gross funding       {result.total_gross:>+8.4%}",
        f"    basis drift         {result.total_basis:>+8.4%}",
        f"    execution           {-result.total_cost:>+8.4%}"
        f"   ({result.cost_share_of_gross:.0%} of gross)",
        f"    net                 {result.total_net:>+8.4%}",
        f"    NET APR ON CAPITAL  {result.net_apr_on_capital:>+8.2%}"
        f"   (while deployed: {result.net_apr_while_deployed:+.2%})",
        f"    win rate            {result.win_rate:>8.0%}",
    ]
    w = result.worst_trade
    if w:
        lines.append(f"    worst hold          {w.net:>+8.4%} over {w.hours}h "
                     f"({w.exit_reason})")
    if not result.is_conclusive:
        lines.append(f"    ** thin: {len(result.trades)} trades, below the "
                     f"{HarvestResult.MIN_TRADES_FOR_VERDICT} needed **")
    return "\n".join(lines)
