"""Risk limits exist to bound the damage from a bug in a model, so they get
tested as adversarially as the models do."""

import pytest

from polybot.config import RiskLimits
from polybot.execution.risk import Position, RiskManager


class TestPosition:
    def test_buy_sets_average(self):
        p = Position("t")
        p.apply_fill("BUY", 0.40, 100)
        assert p.shares == pytest.approx(100)
        assert p.avg_price == pytest.approx(0.40)

    def test_average_blends_across_buys(self):
        p = Position("t")
        p.apply_fill("BUY", 0.40, 100)
        p.apply_fill("BUY", 0.60, 100)
        assert p.avg_price == pytest.approx(0.50)

    def test_sell_realises_pnl(self):
        p = Position("t")
        p.apply_fill("BUY", 0.40, 100)
        realised = p.apply_fill("SELL", 0.50, 50)
        assert realised == pytest.approx(5.0)
        assert p.shares == pytest.approx(50)
        assert p.avg_price == pytest.approx(0.40)

    def test_fee_reduces_realised_pnl(self):
        p = Position("t")
        p.apply_fill("BUY", 0.40, 100)
        realised = p.apply_fill("SELL", 0.50, 50, fee=2.0)
        assert realised == pytest.approx(3.0)

    def test_flat_position_resets_average(self):
        p = Position("t")
        p.apply_fill("BUY", 0.40, 100)
        p.apply_fill("SELL", 0.50, 100)
        assert p.shares == 0.0
        assert p.avg_price == 0.0

    def test_oversell_stays_visible(self):
        """An oversell must not be silently zeroed -- a wrong position you can
        see is fixable, one you cannot is not."""
        p = Position("t")
        p.apply_fill("BUY", 0.40, 100)
        p.apply_fill("SELL", 0.50, 150)
        assert p.shares == pytest.approx(-50)


class TestRiskManager:
    def test_allows_a_normal_order(self):
        r = RiskManager(RiskLimits())
        allowed, reason = r.check_order("t", "BUY", 0.50, 20)
        assert allowed, reason

    def test_blocks_oversized_position(self):
        r = RiskManager(RiskLimits(max_position_usd_per_market=100))
        allowed, reason = r.check_order("t", "BUY", 0.50, 1_000)
        assert not allowed
        assert "position cap" in reason

    def test_blocks_when_total_exposure_exceeded(self):
        r = RiskManager(RiskLimits(max_position_usd_per_market=10_000,
                                   max_total_exposure_usd=100))
        r.record_fill("other", "BUY", 0.50, 180)  # $90 of exposure
        allowed, reason = r.check_order("t", "BUY", 0.50, 100)
        assert not allowed
        assert "exposure cap" in reason

    def test_sells_are_never_blocked_by_position_caps(self):
        """Blocking a risk-reducing sell would trap the bot in a position it
        has already decided it does not want."""
        r = RiskManager(RiskLimits(max_position_usd_per_market=10))
        r.record_fill("t", "BUY", 0.50, 1_000)
        allowed, reason = r.check_order("t", "SELL", 0.50, 1_000)
        assert allowed, reason

    def test_rejects_invalid_prices(self):
        r = RiskManager()
        assert not r.check_order("t", "BUY", 0.0, 10)[0]
        assert not r.check_order("t", "BUY", 1.0, 10)[0]
        assert not r.check_order("t", "BUY", 0.5, 0)[0]

    def test_open_order_cap(self):
        r = RiskManager(RiskLimits(max_open_orders=2))
        for _ in range(2):
            assert r.check_order("t", "BUY", 0.5, 10)[0]
            r.record_order_sent()
        allowed, reason = r.check_order("t", "BUY", 0.5, 10)
        assert not allowed
        assert "max open orders" in reason

    def test_order_rate_limit(self):
        r = RiskManager(RiskLimits(max_orders_per_minute=3, max_open_orders=999))
        for _ in range(3):
            r.record_order_sent()
        allowed, reason = r.check_order("t", "BUY", 0.5, 10)
        assert not allowed
        assert "rate limit" in reason

    def test_daily_loss_limit_halts_trading(self):
        r = RiskManager(RiskLimits(daily_loss_limit_usd=50,
                                   max_position_usd_per_market=10_000))
        r.record_fill("t", "BUY", 0.50, 1_000)
        r.record_fill("t", "SELL", 0.40, 1_000)   # -$100 realised
        assert r.halted
        assert "daily loss" in r.halt_reason
        assert not r.check_order("t", "BUY", 0.5, 10)[0]

    def test_roll_day_clears_the_loss_halt(self):
        r = RiskManager(RiskLimits(daily_loss_limit_usd=50,
                                   max_position_usd_per_market=10_000))
        r.record_fill("t", "BUY", 0.50, 1_000)
        r.record_fill("t", "SELL", 0.40, 1_000)
        assert r.halted
        r.roll_day()
        assert not r.halted
        assert r.session_realised_pnl == 0.0

    def test_manual_halt_survives_roll_day(self):
        """Only the daily-loss halt should auto-clear; an operator halt must
        stay until someone clears it deliberately."""
        r = RiskManager()
        r.halt("operator stopped trading")
        r.roll_day()
        assert r.halted

    def test_max_inventory_shares_scales_with_price(self):
        r = RiskManager(RiskLimits(max_position_usd_per_market=100))
        assert r.max_inventory_shares(0.50) == pytest.approx(200)
        assert r.max_inventory_shares(0.10) == pytest.approx(1_000)
        assert r.max_inventory_shares(0.0) == 0.0

    def test_snapshot_reports_state(self):
        r = RiskManager()
        r.record_fill("t", "BUY", 0.50, 100)
        snap = r.snapshot()
        assert snap["positions"] == 1
        assert snap["exposure_usd"] == pytest.approx(50.0)
