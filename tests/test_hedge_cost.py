"""Book walking for hedge execution cost.

Everything downstream trusts this number, so the properties that matter are
the unglamorous ones: cost is measured from the mid, it grows with size, and
a book too thin to fill is reported as unfillable rather than as cheap.
"""

import pytest

from polybot.venues.funding import HOURS_PER_YEAR, FundingPoint, FundingSeries
from polybot.venues.hedge_cost import (
    HedgeCostSurvey,
    LegCost,
    breakeven_spot_fee,
    carry_on_measured_costs,
    walk_book,
)

ASKS = [(100.5, 10.0), (101.0, 10.0), (102.0, 10.0)]   # $1005 + $1010 + $1020
BIDS = [(99.5, 10.0), (99.0, 10.0), (98.0, 10.0)]
MID = 100.0


class TestWalk:
    def test_small_buy_pays_the_half_spread(self):
        w = walk_book(ASKS, 500.0, MID, side="buy")
        assert w.vwap == pytest.approx(100.5)
        assert w.cost_bps == pytest.approx(50.0)

    def test_sell_cost_is_positive(self):
        """Cost is signed to the taker: selling below mid is a cost, not a
        gain, or every perp leg would look like it paid you."""
        w = walk_book(BIDS, 500.0, MID, side="sell")
        assert w.cost_bps == pytest.approx(50.0)

    def test_cost_rises_with_size(self):
        small = walk_book(ASKS, 500.0, MID, side="buy")
        large = walk_book(ASKS, 2500.0, MID, side="buy")
        assert large.cost_bps > small.cost_bps

    def test_vwap_across_levels(self):
        w = walk_book(ASKS, 2015.0, MID, side="buy")   # first two levels exactly
        assert w.vwap == pytest.approx(2015.0 / 20.0)
        assert not w.exhausted

    def test_exhausted_book_is_not_reported_as_cheap(self):
        """The dangerous failure: averaging over whatever did fill and calling
        that the cost of a size the book could not take."""
        w = walk_book(ASKS, 10_000.0, MID, side="buy")
        assert w.exhausted
        assert w.cost_bps is None
        assert w.filled == pytest.approx(3035.0)

    def test_empty_book(self):
        w = walk_book([], 100.0, MID, side="buy")
        assert w.cost_bps is None and w.filled == 0.0

    def test_rejects_non_positive_mid(self):
        with pytest.raises(ValueError):
            walk_book(ASKS, 100.0, 0.0, side="buy")


class TestSurvey:
    def _survey(self, spot_samples, perp_samples, *, perp_exhausted=0):
        s = HedgeCostSurvey(sizes=(10_000.0,))
        s.spot[("X", 10_000.0)] = LegCost("X", "coinbase", 10_000.0,
                                          samples=spot_samples)
        s.perp[("X", 10_000.0)] = LegCost("X", "hyperliquid", 10_000.0,
                                          samples=perp_samples,
                                          exhausted=perp_exhausted)
        return s

    def test_pair_cost_is_the_sum_of_medians(self):
        s = self._survey([10.0, 20.0, 30.0], [1.0, 2.0, 3.0])
        assert s.one_leg_slippage("X", 10_000.0) == pytest.approx(22.0 / 1e4)

    def test_one_exhausted_snapshot_disqualifies_the_size(self):
        """A size that could not fill once is not a size to plan around."""
        s = self._survey([10.0, 10.0], [1.0, 1.0], perp_exhausted=1)
        assert s.one_leg_slippage("X", 10_000.0) is None

    def test_unknown_coin(self):
        s = self._survey([1.0], [1.0])
        assert s.one_leg_slippage("NOPE", 10_000.0) is None


def _series(coin, apr, hours=3000):
    rate = apr / HOURS_PER_YEAR
    return FundingSeries(coin=coin, points=[
        FundingPoint(ts_ms=i * 3_600_000, rate=rate, premium=0.0)
        for i in range(hours)])


def _measured(costs_bps: dict[str, float | None], size=10_000.0):
    s = HedgeCostSurvey(sizes=(size,))
    for c, bps in costs_bps.items():
        if bps is None:
            s.spot[(c, size)] = LegCost(c, "coinbase", size, exhausted=1)
            s.perp[(c, size)] = LegCost(c, "hyperliquid", size, samples=[1.0])
        else:
            s.spot[(c, size)] = LegCost(c, "coinbase", size, samples=[bps])
            s.perp[(c, size)] = LegCost(c, "hyperliquid", size, samples=[0.0])
    return s


class TestMeasuredCarry:
    def test_unfillable_names_leave_the_universe(self):
        """A name you cannot put on is not a candidate, however much it
        pays -- otherwise the ranking picks it and the result is fiction."""
        ser = {"RICH": _series("RICH", 0.50), "OK": _series("OK", 0.10)}
        sv = _measured({"RICH": None, "OK": 5.0})
        r, universe = carry_on_measured_costs(ser, sv, 10_000.0, spot_fee=0.0,
                                              top_n=1, rebalance_hours=240,
                                              lookback_hours=240)
        assert universe == ["OK"]
        assert r.gross / (r.window_hours / HOURS_PER_YEAR) == pytest.approx(
            0.10, rel=1e-3)

    def test_breakeven_fee_hits_the_hurdle(self):
        ser = {"A": _series("A", 0.10)}
        sv = _measured({"A": 5.0})
        kw = dict(top_n=1, rebalance_hours=240, lookback_hours=240)
        fee = breakeven_spot_fee(ser, sv, 10_000.0, hurdle=0.05, **kw)
        assert fee is not None and 0.0 < fee < 0.02
        r, _ = carry_on_measured_costs(ser, sv, 10_000.0, spot_fee=fee, **kw)
        assert r.net_apr_on_capital == pytest.approx(0.05, abs=1e-6)

    def test_no_breakeven_when_even_free_execution_misses(self):
        ser = {"A": _series("A", 0.02)}
        sv = _measured({"A": 5.0})
        assert breakeven_spot_fee(ser, sv, 10_000.0, hurdle=0.05, top_n=1,
                                  rebalance_hours=240,
                                  lookback_hours=240) is None
