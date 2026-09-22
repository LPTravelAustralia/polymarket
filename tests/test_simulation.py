"""Fill simulation and markout.

These tests matter more than most: if the fill model is optimistic, every
backtest built on it lies in the same direction.
"""

import pytest

from polybot.marketdata.store import PublicTrade, Snapshot
from polybot.simulation.fills import FillSimulator, SimulatedOrder
from polybot.simulation.markout import (
    MidSeries,
    calibrate,
    compute_markouts,
    render_markout_report,
)


def snap(ts, bids=((0.48, 100.0),), asks=((0.52, 100.0),), token="t1"):
    return Snapshot(ts=ts, token_id=token, bids=list(bids), asks=list(asks),
                    tick_size=0.01)


def order(price=0.48, size=20.0, side="BUY", ts=0.0, oid="o1", token="t1"):
    return SimulatedOrder(order_id=oid, token_id=token, side=side,
                          price=price, size=size, placed_ts=ts)


class TestQueuePosition:
    def test_queue_recorded_at_placement(self):
        sim = FillSimulator()
        o = sim.place(order(), snap(0))
        assert o.queue_ahead == pytest.approx(100.0)

    def test_no_fill_while_queue_is_ahead(self):
        """The core correctness property. A naive simulator books a fill
        here and thereby invents most of a strategy's profit."""
        sim = FillSimulator()
        sim.place(order(), snap(0))
        fills = sim.on_trade(PublicTrade(ts=1, token_id="t1", price=0.48, size=50))
        assert fills == []
        assert sim.open_orders("t1")[0].queue_ahead == pytest.approx(50.0)

    def test_fills_once_queue_is_consumed(self):
        sim = FillSimulator()
        sim.place(order(size=20), snap(0))
        sim.on_trade(PublicTrade(ts=1, token_id="t1", price=0.48, size=100))
        fills = sim.on_trade(PublicTrade(ts=2, token_id="t1", price=0.48, size=30))
        assert len(fills) == 1
        assert fills[0].size == pytest.approx(20.0)
        assert fills[0].reason == "queue"

    def test_partial_fill(self):
        sim = FillSimulator()
        sim.place(order(size=50), snap(0, bids=[(0.48, 0.0)]))
        fills = sim.on_trade(PublicTrade(ts=1, token_id="t1", price=0.48, size=30))
        assert fills[0].size == pytest.approx(30.0)
        assert sim.open_orders("t1")[0].remaining == pytest.approx(20.0)

    def test_cancellations_move_us_up_the_queue(self):
        sim = FillSimulator()
        sim.place(order(), snap(0))
        assert sim.open_orders("t1")[0].queue_ahead == pytest.approx(100.0)
        # Level thins out: others cancelled, so our queue shrank.
        sim.on_snapshot(snap(1, bids=[(0.48, 10.0)]))
        assert sim.open_orders("t1")[0].queue_ahead == pytest.approx(10.0)

    def test_queue_never_grows_from_new_arrivals(self):
        """Orders joining behind us must not push us back."""
        sim = FillSimulator()
        sim.place(order(), snap(0, bids=[(0.48, 10.0)]))
        sim.on_snapshot(snap(1, bids=[(0.48, 900.0)]))
        assert sim.open_orders("t1")[0].queue_ahead == pytest.approx(10.0)


class TestTradeDirection:
    def test_bid_not_touched_by_higher_trades(self):
        sim = FillSimulator()
        sim.place(order(price=0.48), snap(0, bids=[(0.48, 0.0)]))
        assert sim.on_trade(PublicTrade(ts=1, token_id="t1", price=0.51, size=100)) == []

    def test_bid_touched_by_lower_trades(self):
        sim = FillSimulator()
        sim.place(order(price=0.48), snap(0, bids=[(0.48, 0.0)]))
        assert sim.on_trade(PublicTrade(ts=1, token_id="t1", price=0.47, size=100))

    def test_offer_touched_by_higher_trades(self):
        sim = FillSimulator()
        sim.place(order(price=0.52, side="SELL"), snap(0, asks=[(0.52, 0.0)]))
        assert sim.on_trade(PublicTrade(ts=1, token_id="t1", price=0.53, size=100))

    def test_trades_before_placement_are_ignored(self):
        sim = FillSimulator()
        sim.place(order(ts=10), snap(10, bids=[(0.48, 0.0)]))
        assert sim.on_trade(PublicTrade(ts=5, token_id="t1", price=0.48, size=100)) == []

    def test_other_tokens_ignored(self):
        sim = FillSimulator()
        sim.place(order(), snap(0, bids=[(0.48, 0.0)]))
        assert sim.on_trade(PublicTrade(ts=1, token_id="OTHER", price=0.48, size=100)) == []


class TestPriceThrough:
    def test_market_running_through_the_bid_fills_it(self):
        """The adverse fill. Ignoring it is what makes bad backtests look
        profitable."""
        sim = FillSimulator()
        sim.place(order(price=0.48), snap(0))
        fills = sim.on_snapshot(snap(1, bids=[(0.45, 100.0)], asks=[(0.47, 100.0)]))
        assert len(fills) == 1
        assert fills[0].reason == "price_through"
        assert fills[0].size == pytest.approx(20.0)

    def test_no_price_through_when_book_holds(self):
        sim = FillSimulator()
        sim.place(order(price=0.48), snap(0))
        assert sim.on_snapshot(snap(1)) == []

    def test_can_be_disabled(self):
        sim = FillSimulator(allow_price_through=False)
        sim.place(order(price=0.48), snap(0))
        assert sim.on_snapshot(snap(1, bids=[(0.45, 10.0)], asks=[(0.47, 10.0)])) == []

    def test_pickoff_rate_reported(self):
        sim = FillSimulator()
        sim.place(order(price=0.48), snap(0))
        sim.on_snapshot(snap(1, bids=[(0.45, 10.0)], asks=[(0.47, 10.0)]))
        assert sim.fill_rate() == pytest.approx(1.0)


class TestMidSeries:
    def test_lookup_after_timestamp(self):
        s = MidSeries([snap(0), snap(10), snap(20)])
        assert s.at_or_after(5) is not None
        assert len(s) == 3

    def test_refuses_stale_lookup(self):
        """Comparing a fill against a mid from an hour later is not a
        markout, it is noise."""
        s = MidSeries([snap(0), snap(10_000)])
        assert s.at_or_after(100, max_gap=300) is None

    def test_past_end_returns_none(self):
        s = MidSeries([snap(0)])
        assert s.at_or_after(1_000) is None


class TestMarkout:
    @staticmethod
    def _adverse_fills(n=60):
        """Bought at 0.50, and the mid then fell to 0.49 every time."""
        from polybot.simulation.fills import SimulatedFill

        fills, snaps = [], []
        for i in range(n):
            t = i * 1000.0
            fills.append(SimulatedFill(f"o{i}", "t1", "BUY", 0.50, 10, t, "queue"))
            snaps.append(snap(t, bids=[(0.49, 10)], asks=[(0.51, 10)]))
            snaps.append(snap(t + 60, bids=[(0.48, 10)], asks=[(0.50, 10)]))
        return fills, snaps

    def test_detects_adverse_selection(self):
        fills, snaps = self._adverse_fills()
        m = compute_markouts(fills, {"t1": snaps}, horizons=(60,))
        assert m[60].mean == pytest.approx(-0.01, abs=1e-9)
        assert m[60].adverse_selection_per_share == pytest.approx(0.01, abs=1e-9)

    def test_calibration_recommends_raising_a_too_low_constant(self):
        fills, snaps = self._adverse_fills()
        m = compute_markouts(fills, {"t1": snaps}, horizons=(60,))
        cal = calibrate(m, current=0.004, prefer_horizon=60)
        assert cal.confident
        assert cal.suggested == pytest.approx(0.01, abs=1e-9)
        assert "RAISE" in cal.verdict

    def test_small_sample_refuses_to_recommend(self):
        """Ten fills must not produce a confident-looking constant."""
        fills, snaps = self._adverse_fills(n=5)
        m = compute_markouts(fills, {"t1": snaps}, horizons=(60,))
        cal = calibrate(m, current=0.004, prefer_horizon=60)
        assert not cal.confident
        assert "INSUFFICIENT" in cal.verdict

    def test_no_fills_is_handled(self):
        cal = calibrate({}, current=0.004)
        assert not cal.confident
        assert cal.suggested == 0.0

    def test_report_renders(self):
        fills, snaps = self._adverse_fills()
        m = compute_markouts(fills, {"t1": snaps}, horizons=(60,))
        text = render_markout_report(m, calibrate(m, current=0.004, prefer_horizon=60))
        assert "Markout analysis" in text
        assert "adverse selection" in text.lower()


class TestRelativeMarkout:
    """Absolute markout is only poolable when instruments share a price
    scale. Prediction-market prices are all probabilities in [0,1] so it is
    fine there; across perps it is not, and pooling BTC with DOGE in
    absolute terms produced a reported $23.66/share of adverse selection
    against a $0.00009 median on the first live run.
    """

    @staticmethod
    def _mixed_fills(n=60):
        from polybot.simulation.fills import SimulatedFill

        fills, snaps = [], {"BIG": [], "SMALL": []}
        for i in range(n):
            t = i * 1000.0
            # Both lose exactly 1% after the fill, at wildly different scales.
            for token, px in (("BIG", 80_000.0), ("SMALL", 0.08)):
                fills.append(SimulatedFill(f"{token}{i}", token, "BUY", px, 1, t, "queue"))
                lo, hi = px * 0.99, px * 1.01
                snaps[token].append(snap(t, bids=[(px * 0.999, 10)],
                                         asks=[(px * 1.001, 10)], token=token))
                snaps[token].append(snap(t + 60, bids=[(lo * 0.999, 10)],
                                         asks=[(lo * 1.001, 10)], token=token))
        return fills, snaps

    def test_absolute_mode_is_dominated_by_the_expensive_instrument(self):
        fills, snaps = self._mixed_fills()
        m = compute_markouts(fills, snaps, horizons=(60,), relative=False)
        # ~1% of 80,000 swamps ~1% of 0.08 entirely.
        assert m[60].mean < -100.0

    def test_relative_mode_gives_the_shared_percentage(self):
        fills, snaps = self._mixed_fills()
        m = compute_markouts(fills, snaps, horizons=(60,), relative=True)
        # Both instruments lost ~1%, so the pooled mean should be ~-0.01.
        assert m[60].mean == pytest.approx(-0.01, abs=0.002)

    def test_relative_mode_skips_non_positive_prices(self):
        from polybot.simulation.fills import SimulatedFill

        fills = [SimulatedFill("o", "t1", "BUY", 0.0, 1, 0.0, "queue")]
        snaps = {"t1": [snap(0), snap(60)]}
        assert compute_markouts(fills, snaps, horizons=(60,), relative=True) == {}
