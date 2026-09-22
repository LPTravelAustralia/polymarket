"""Funding harvest.

The failure mode to guard against here is a carry business that exists only
in the arithmetic: gross funding counted, execution and basis quietly
dropped, and entries chosen with hindsight.
"""

import pytest

from polybot.venues.funding import (
    HOURS_PER_YEAR,
    FundingPoint,
    FundingSeries,
    HarvestCosts,
    simulate_always_on,
    simulate_cross_sectional,
    simulate_harvest,
)


def series(rates, premiums=None, coin="X", start=0):
    prem = premiums if premiums is not None else [0.0] * len(rates)
    return FundingSeries(coin=coin, points=[
        FundingPoint(ts_ms=start + i * 3_600_000, rate=r, premium=p)
        for i, (r, p) in enumerate(zip(rates, prem))
    ])


FLAT_10PCT = 0.10 / HOURS_PER_YEAR


class TestCosts:
    def test_round_trip_is_four_legs(self):
        c = HarvestCosts(perp_taker=0.001, spot_taker=0.002,
                         perp_slippage=0.0, spot_slippage=0.0)
        assert c.round_trip == pytest.approx(0.006)

    def test_breakeven_lengthens_as_carry_thins(self):
        c = HarvestCosts()
        assert c.breakeven_hours(0.20) < c.breakeven_hours(0.05)

    def test_no_breakeven_on_negative_carry(self):
        assert HarvestCosts().breakeven_hours(-0.05) is None


class TestAlwaysOn:
    def test_gross_matches_the_summed_rate(self):
        s = series([FLAT_10PCT] * 8760)
        assert s.buy_and_hold_apr() == pytest.approx(0.10, rel=1e-6)

    def test_execution_is_deducted_once(self):
        s = series([FLAT_10PCT] * 8760)
        c = HarvestCosts(perp_slippage=0.0, spot_slippage=0.0)
        r = simulate_always_on(s, costs=c)
        assert r.total_cost == pytest.approx(c.round_trip)
        assert r.total_net == pytest.approx(0.10 - c.round_trip, rel=1e-4)

    def test_net_apr_is_divided_by_capital_committed(self):
        """APR on notional is not APR on money, and conflating them
        overstates the return by the whole margin multiple."""
        s = series([FLAT_10PCT] * 8760)
        one = HarvestCosts(capital_multiplier=1.0)
        two = HarvestCosts(capital_multiplier=2.0)
        assert (simulate_always_on(s, costs=two).net_apr_on_capital
                == pytest.approx(
                    simulate_always_on(s, costs=one).net_apr_on_capital / 2))

    def test_basis_widening_is_a_real_loss(self):
        """Enter cheap, exit rich, and the carry funded the counterparty."""
        flat = series([FLAT_10PCT] * 100, [0.0] * 100)
        widening = series([FLAT_10PCT] * 100, [0.0] * 99 + [0.01])
        assert (simulate_always_on(widening).total_net
                < simulate_always_on(flat).total_net - 0.009)


class TestTiming:
    def test_no_entry_below_threshold(self):
        s = series([0.01 / HOURS_PER_YEAR] * 2000)
        assert simulate_harvest(s, entry_apr=0.10).trades == []

    def test_entry_uses_only_trailing_data(self):
        """A rule that sees the funding it is about to earn is a lookahead,
        and it is the easiest way to invent a carry business."""
        quiet, rich = [0.0] * 200, [FLAT_10PCT * 5] * 200
        r = simulate_harvest(series(quiet + rich), entry_apr=0.10,
                             lookback_hours=24)
        assert r.trades, "should eventually enter"
        # Entry cannot precede the regime change it is reacting to.
        assert r.trades[0].entry_ts >= 200 * 3_600_000

    def test_churn_pays_the_round_trip_every_time(self):
        """Funding oscillating across the exit threshold must not produce
        free re-entries."""
        cycle = ([FLAT_10PCT * 3] * 30 + [0.0] * 30) * 20
        r = simulate_harvest(series(cycle), entry_apr=0.10, exit_apr=0.02,
                             lookback_hours=12, min_hold_hours=4)
        assert len(r.trades) > 3
        assert r.total_cost == pytest.approx(
            len(r.trades) * r.costs.round_trip)

    def test_min_hold_prevents_instant_exit(self):
        cycle = ([FLAT_10PCT * 3] * 5 + [0.0] * 5) * 50
        r = simulate_harvest(series(cycle), entry_apr=0.10, exit_apr=0.02,
                             lookback_hours=4, min_hold_hours=20)
        assert all(t.hours >= 20 or t.exit_reason == "end of data"
                   for t in r.trades)

    def test_thin_sample_is_flagged(self):
        s = series([FLAT_10PCT * 5] * 500)
        r = simulate_harvest(s, entry_apr=0.10)
        assert not r.is_conclusive


class TestCrossSectional:
    def test_picks_the_richer_name(self):
        rich = series([FLAT_10PCT * 5] * 2000, coin="RICH")
        poor = series([0.0] * 2000, coin="POOR")
        r = simulate_cross_sectional(
            {"RICH": rich, "POOR": poor}, top_n=1,
            rebalance_hours=240, lookback_hours=240,
        )
        assert r.gross > 0
        assert r.periods > 0

    def test_carrying_a_name_costs_nothing(self):
        """The advantage of rebalancing over timing is that unchanged
        positions do not re-pay execution. If they did, the two shapes
        would be the same trade."""
        rich = series([FLAT_10PCT * 5] * 3000, coin="RICH")
        poor = series([0.0] * 3000, coin="POOR")
        u = {"RICH": rich, "POOR": poor}
        r = simulate_cross_sectional(u, top_n=1, rebalance_hours=240,
                                     lookback_hours=240)
        # One entry plus one final unwind, never once per period.
        assert r.turnover_legs == 2
        assert r.periods > 2

    def test_alignment_drops_unshared_hours(self):
        long = series([FLAT_10PCT] * 2000, coin="LONG")
        short = series([FLAT_10PCT] * 500, coin="SHORT")
        r = simulate_cross_sectional({"LONG": long, "SHORT": short}, top_n=1,
                                     rebalance_hours=100, lookback_hours=100)
        assert r.window_hours <= 500

    def test_empty_universe_is_handled(self):
        r = simulate_cross_sectional({"A": series([0.0] * 10)}, top_n=1,
                                     rebalance_hours=100, lookback_hours=100)
        assert r.net_apr_on_capital == 0.0
