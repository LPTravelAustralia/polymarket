"""The fee model is load-bearing, so it gets checked against the published
worked examples rather than against itself."""

import pytest

from polybot.economics import (
    FeeSchedule,
    breakeven_win_rate,
    evaluate_trade,
    expected_maker_rebate,
    min_profitable_taker_price,
    round_trip_taker_cost_per_share,
    taker_fee,
    taker_fee_per_share,
)


class TestFeeFormula:
    @pytest.mark.parametrize(
        "size,price,rate,expected",
        [
            # Polymarket's published examples: fee = shares * rate * p * (1-p)
            (100, 0.50, 0.04, 1.00),   # politics, quoted as $1.00/100 shares
            (100, 0.50, 0.07, 1.75),   # crypto, quoted as $1.75/100 shares
            (100, 0.50, 0.05, 1.25),   # US schedule cap of $1.25/100 at 50c
            (500, 0.50, 0.04, 5.00),   # 500 shares at 0.50 on a politics market
        ],
    )
    def test_matches_published_examples(self, size, price, rate, expected):
        assert taker_fee(size, price, rate) == pytest.approx(expected, abs=1e-9)

    def test_symmetric_in_price(self):
        """Buying YES at p must cost the same fee as buying NO at 1-p,
        otherwise the two legs of a complement trade are not equivalent."""
        for p in (0.1, 0.25, 0.4, 0.49):
            assert taker_fee(100, p, 0.05) == pytest.approx(taker_fee(100, 1 - p, 0.05))

    def test_peaks_at_midpoint(self):
        mid = taker_fee_per_share(0.50, 0.05)
        for p in (0.05, 0.2, 0.35, 0.65, 0.8, 0.95):
            assert taker_fee_per_share(p, 0.05) < mid

    def test_tails_are_cheap(self):
        """The bell curve means tail trading is far cheaper -- which is why
        tail mispricing is where the fee-adjusted money is."""
        assert taker_fee_per_share(0.95, 0.05) == pytest.approx(0.05 * 0.95 * 0.05)
        assert taker_fee_per_share(0.95, 0.05) < taker_fee_per_share(0.50, 0.05) / 5

    def test_zero_at_boundaries(self):
        assert taker_fee(100, 0.0, 0.05) == 0.0
        assert taker_fee(100, 1.0, 0.05) == 0.0

    def test_clamps_out_of_range_prices(self):
        assert taker_fee(100, 1.5, 0.05) == 0.0
        assert taker_fee(100, -0.5, 0.05) == 0.0


class TestRoundTripCost:
    def test_round_trip_at_mid_is_brutal(self):
        """A taker-in/taker-out round trip at 0.50 with a 5% rate costs
        2.5c/share -- 5% of a 50c position. This single number is why the
        bot is maker-only."""
        cost = round_trip_taker_cost_per_share(0.50, 0.50, 0.05)
        assert cost == pytest.approx(0.025)
        assert cost / 0.50 == pytest.approx(0.05)


class TestFeeSchedule:
    def test_from_bps(self):
        s = FeeSchedule.from_bps(500)
        assert s.taker_rate == pytest.approx(0.05)

    def test_category_lookup_falls_back(self):
        assert FeeSchedule.for_category("not-a-category").taker_rate == 0.05
        assert FeeSchedule.for_category(None).taker_rate == 0.05

    def test_no_category_falls_back_to_zero(self):
        """Geopolitics used to be fee-free; new markets there now charge the
        4% politics rate. A zero fallback makes marginal trades look
        profitable, so no category falls back to it."""
        assert FeeSchedule.for_category("geopolitics").taker_rate == 0.04
        assert all(FeeSchedule.for_category(c).taker_rate > 0
                   for c in ("sports", "world", "politics", "crypto"))


class TestFromMarket:
    def test_reads_the_markets_own_schedule(self):
        m = {"feeType": "sports_fees_v3", "feesEnabled": True,
             "feeSchedule": {"exponent": 1, "rate": 0.05, "takerOnly": True,
                             "rebateRate": 0.15}}
        s = FeeSchedule.from_market(m)
        assert s.taker_rate == pytest.approx(0.05)
        assert s.maker_rebate_share == pytest.approx(0.15)

    def test_zero_fee_markets(self):
        m = {"feeType": "zero_fees", "feesEnabled": True,
             "feeSchedule": {"rate": 0, "rebateRate": 0}}
        assert FeeSchedule.from_market(m).taker_rate == 0.0

    def test_legacy_markets_created_before_fees_are_free(self):
        assert FeeSchedule.from_market({"feeType": None}).taker_rate == 0.0

    def test_unknown_falls_back_by_category(self):
        m = {"feeType": "politics_fees", "feesEnabled": True}
        assert FeeSchedule.from_market(m, "politics").taker_rate == pytest.approx(0.04)


class TestEvaluateTrade:
    def test_maker_pays_nothing(self):
        s = FeeSchedule(taker_rate=0.05)
        e = evaluate_trade("BUY", 0.50, 100, fair_value=0.52, schedule=s, is_maker=True)
        assert e.fee_per_share == 0.0
        assert e.net_edge_per_share == pytest.approx(0.02)
        assert e.net_edge_total == pytest.approx(2.0)

    def test_taker_edge_is_eaten_by_fees(self):
        """2c of gross edge at mid prices is only 0.75c net after a 5% fee."""
        s = FeeSchedule(taker_rate=0.05)
        e = evaluate_trade("BUY", 0.50, 100, fair_value=0.52, schedule=s, is_maker=False)
        assert e.fee_per_share == pytest.approx(0.0125)
        assert e.net_edge_per_share == pytest.approx(0.0075)

    def test_thin_taker_edge_is_actually_a_loss(self):
        s = FeeSchedule(taker_rate=0.05)
        e = evaluate_trade("BUY", 0.50, 100, fair_value=0.51, schedule=s, is_maker=False)
        assert not e.is_profitable
        assert e.net_edge_per_share < 0

    def test_sell_side_sign(self):
        s = FeeSchedule(taker_rate=0.05)
        e = evaluate_trade("SELL", 0.60, 100, fair_value=0.55, schedule=s, is_maker=True)
        assert e.gross_edge_per_share == pytest.approx(0.05)

    def test_rejects_bad_side(self):
        with pytest.raises(ValueError):
            evaluate_trade("HOLD", 0.5, 1, 0.5, FeeSchedule(), True)


class TestMinProfitablePrice:
    @pytest.mark.parametrize("fair", [0.2, 0.4, 0.6, 0.8])
    def test_solution_has_zero_net_edge(self, fair):
        """The returned price is where net edge is exactly zero, so verify by
        substituting it back rather than trusting the algebra."""
        s = FeeSchedule(taker_rate=0.05)
        p = min_profitable_taker_price(fair, s)
        net = fair - p - taker_fee_per_share(p, s.taker_rate)
        assert net == pytest.approx(0.0, abs=1e-9)

    def test_always_below_fair_value(self):
        s = FeeSchedule(taker_rate=0.05)
        for fair in (0.3, 0.5, 0.7):
            assert min_profitable_taker_price(fair, s) < fair

    def test_zero_rate_degenerates_to_fair_value(self):
        s = FeeSchedule(taker_rate=0.0)
        assert min_profitable_taker_price(0.6, s) == pytest.approx(0.6)

    def test_margin_tightens_the_bound(self):
        s = FeeSchedule(taker_rate=0.05)
        assert min_profitable_taker_price(0.6, s, 0.01) < min_profitable_taker_price(0.6, s)


class TestBreakeven:
    def test_maker_breakeven_is_just_the_price(self):
        assert breakeven_win_rate(0.40, FeeSchedule(taker_rate=0.05), True) == pytest.approx(0.40)

    def test_taker_breakeven_is_worse(self):
        s = FeeSchedule(taker_rate=0.05)
        assert breakeven_win_rate(0.40, s, False) > 0.40


class TestRebate:
    def test_scales_with_pool_capture(self):
        s = FeeSchedule(taker_rate=0.05, maker_rebate_share=0.25)
        assert expected_maker_rebate(100, 0.5, s, 0.0) == 0.0
        full = expected_maker_rebate(100, 0.5, s, 1.0)
        assert full == pytest.approx(1.25 * 0.25)
        assert expected_maker_rebate(100, 0.5, s, 0.5) == pytest.approx(full / 2)

    def test_capture_is_clamped(self):
        s = FeeSchedule(taker_rate=0.05, maker_rebate_share=0.25)
        assert expected_maker_rebate(100, 0.5, s, 5.0) == pytest.approx(
            expected_maker_rebate(100, 0.5, s, 1.0)
        )
