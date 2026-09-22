"""Event study methodology.

These tests validate the *analyser* by feeding it synthetic data with a
known answer. If it cannot detect drift that was deliberately inserted, or
reports drift in data that mean-reverts, then nothing it says about real
markets is worth reading.
"""

import random

import pytest

from polybot.research.event_study import (
    Candle,
    find_shocks,
    render_event_study,
    returns,
    rolling_sigma,
    run_event_study,
)


def series(prices, start_ts=1_700_000_000_000, step=60_000):
    return [
        Candle(ts=start_ts + i * step, open=p, high=p, low=p, close=p)
        for i, p in enumerate(prices)
    ]


def synthetic(n=4000, shock_every=400, shock_size=0.05, drift_after=0.0, seed=1):
    """Quiet random walk punctuated by shocks, with controllable aftermath.

    drift_after > 0 continues the move; < 0 reverses it; 0 means the shock
    is a one-off step with no follow-through.
    """
    rng = random.Random(seed)
    price = 100.0
    prices = [price]
    for i in range(1, n):
        if i % shock_every == 0:
            price *= 1 + shock_size
        elif i % shock_every in range(1, 61) and drift_after:
            price *= 1 + drift_after / 60.0
        else:
            price *= 1 + rng.gauss(0, 0.0004)
        prices.append(price)
    return series(prices)


class TestPrimitives:
    def test_returns(self):
        assert returns(series([100, 110])) == pytest.approx([0.10])

    def test_returns_empty(self):
        assert returns(series([100])) == []

    def test_rolling_sigma_needs_history(self):
        """Without enough history, nothing should qualify as a shock."""
        sig = rolling_sigma([0.01] * 10, window=100)
        assert all(s == float("inf") for s in sig)

    def test_rolling_sigma_computes_once_warm(self):
        rng = random.Random(0)
        rets = [rng.gauss(0, 0.001) for _ in range(200)]
        sig = rolling_sigma(rets, window=100)
        assert sig[-1] < float("inf")
        assert sig[-1] > 0


class TestShockDetection:
    def test_finds_inserted_shocks(self):
        candles = synthetic(n=3000, shock_every=500, shock_size=0.05)
        shocks = find_shocks(candles, threshold_sigma=4.0)
        assert len(shocks) >= 3
        assert all(s.direction == 1 for s in shocks)

    def test_detects_downward_shocks(self):
        candles = synthetic(n=3000, shock_every=500, shock_size=-0.05)
        shocks = find_shocks(candles, threshold_sigma=4.0)
        assert shocks and all(s.direction == -1 for s in shocks)

    def test_quiet_series_has_no_shocks(self):
        rng = random.Random(3)
        price = 100.0
        prices = [price]
        for _ in range(2000):
            price *= 1 + rng.gauss(0, 0.0004)
            prices.append(price)
        assert find_shocks(series(prices), threshold_sigma=6.0) == []

    def test_min_gap_prevents_double_counting(self):
        """Aftershocks must not be counted as separate events -- that inflates
        n with non-independent observations and fakes significance."""
        candles = synthetic(n=3000, shock_every=500, shock_size=0.05)
        few = find_shocks(candles, threshold_sigma=4.0, min_gap_bars=200)
        many = find_shocks(candles, threshold_sigma=4.0, min_gap_bars=1)
        assert len(few) <= len(many)


class TestDirectionSigning:
    def test_down_shock_that_keeps_falling_counts_as_continuation(self):
        """Without signing by direction, up and down shocks cancel and every
        study concludes 'no effect'."""
        candles = synthetic(n=4000, shock_every=400, shock_size=-0.05,
                            drift_after=-0.02)
        study = run_event_study("DOWN", candles, threshold_sigma=3.5)
        assert study.shocks > 0
        r = study.results.get(15)
        assert r is not None and r.mean_return > 0, "continuation must read positive"


class TestVerdicts:
    # Enough shocks to clear the analyser's n>=30 significance floor. That
    # floor is deliberate -- a verdict off 15 events would be noise -- so the
    # fixtures accommodate it rather than the analyser relaxing it.
    BIG = dict(n=16_000, shock_every=150, shock_size=0.04)

    def test_detects_real_drift(self):
        study = run_event_study(
            "DRIFT", synthetic(**self.BIG, drift_after=0.03), threshold_sigma=3.5
        )
        r = study.results.get(60)
        assert r is not None and r.mean_return > 0
        assert r.is_significant
        # "NOT TRADEABLE" also contains "TRADEABLE", so assert on the
        # positive verdict explicitly.
        assert study.verdict(round_trip_cost=0.0005).startswith("POSSIBLY TRADEABLE")

    def test_detects_mean_reversion_and_warns(self):
        study = run_event_study(
            "REVERT", synthetic(**self.BIG, drift_after=-0.03), threshold_sigma=3.5
        )
        r = study.results.get(60)
        assert r is not None and r.mean_return < 0
        v = study.verdict(round_trip_cost=0.0005)
        assert v.startswith("NOT TRADEABLE")
        assert "exit liquidity" in v

    def test_costs_can_overturn_a_real_drift(self):
        """The distinction that matters: statistically real is not the same
        as profitable."""
        study = run_event_study(
            "THIN", synthetic(**self.BIG, drift_after=0.004), threshold_sigma=3.5
        )
        assert study.results[60].is_significant, "drift should be statistically real"
        assert study.verdict(round_trip_cost=0.00001).startswith("POSSIBLY TRADEABLE")
        assert study.verdict(round_trip_cost=0.05).startswith("NOT TRADEABLE")

    def test_no_followthrough_is_not_tradeable(self):
        study = run_event_study(
            "STEP", synthetic(**self.BIG, drift_after=0.0), threshold_sigma=3.5
        )
        assert study.verdict(round_trip_cost=0.001).startswith("NOT TRADEABLE")

    def test_insufficient_data(self):
        study = run_event_study("TINY", series([100, 101, 102]))
        assert study.shocks == 0
        assert "Not enough data" in render_event_study(study)

    def test_report_renders(self):
        candles = synthetic(n=6000, shock_every=400, shock_size=0.04,
                            drift_after=0.02)
        text = render_event_study(run_event_study("X", candles, threshold_sigma=3.5))
        assert "Event study" in text
        assert "horizon" in text


class TestCandleParsing:
    def test_from_hyperliquid(self):
        c = Candle.from_hyperliquid(
            {"t": 1700000000000, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "10"}
        )
        assert c.close == pytest.approx(1.5)
        assert c.ts == 1700000000000

    def test_tolerates_missing_fields(self):
        assert Candle.from_hyperliquid({}).close == 0.0


class TestCleanWindows:
    """Regression: forward windows must not span a later shock.

    Found by a test on data with deliberately ZERO follow-through, which
    reported tradeable drift at the longest horizon purely because the
    window reached into the next event.
    """

    def test_overlapping_windows_do_not_manufacture_drift(self):
        # Shocks every 150 bars, measured out to 240 -- windows overlap.
        study = run_event_study(
            "OVERLAP",
            synthetic(n=16_000, shock_every=150, shock_size=0.04, drift_after=0.0),
            threshold_sigma=3.5,
        )
        assert study.verdict(round_trip_cost=0.001).startswith("NOT TRADEABLE")

    def test_contaminated_horizon_is_dropped_not_fudged(self):
        from polybot.research.event_study import find_shocks, measure_forward

        candles = synthetic(n=16_000, shock_every=150, shock_size=0.04)
        shocks = find_shocks(candles, threshold_sigma=3.5)
        measure_forward(candles, shocks, (1, 240), clean_windows=True)
        # The 240-bar horizon spans the next shock, so it should be absent.
        assert all(240 not in s.forward for s in shocks[:-1])
        assert any(1 in s.forward for s in shocks)

    def test_disabling_the_guard_reintroduces_the_artifact(self):
        from polybot.research.event_study import find_shocks, measure_forward

        candles = synthetic(n=16_000, shock_every=150, shock_size=0.04)
        shocks = find_shocks(candles, threshold_sigma=3.5)
        measure_forward(candles, shocks, (240,), clean_windows=False)
        assert any(240 in s.forward for s in shocks)
