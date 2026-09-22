"""Book walking for hedge execution cost.

Everything downstream trusts this number, so the properties that matter are
the unglamorous ones: cost is measured from the mid, it grows with size, and
a book too thin to fill is reported as unfillable rather than as cheap.
"""

import pytest

from polybot.venues.hedge_cost import HedgeCostSurvey, LegCost, walk_book

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
