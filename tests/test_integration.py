"""End-to-end test of the quote -> risk -> order pipeline against a fake
gateway, so the wiring is verified without touching the network."""

import pytest

from polybot.clients.clob import Book, Level
from polybot.config import MakerParams, Mode, RiskLimits, Settings
from polybot.economics import FeeBook, FeeSchedule
from polybot.execution.order_manager import OrderManager
from polybot.execution.risk import RiskManager
from polybot.strategy.fair_value import FairValue
from polybot.strategy.maker import MakerStrategy


class FakeGateway:
    """Records orders instead of sending them."""

    def __init__(self):
        self.posted = []
        self.cancelled = []
        self.fees = FeeBook()
        self._next_id = 0
        self.fail_next = False

    def post_limit(self, token_id, side, price, size, post_only=True):
        if self.fail_next:
            self.fail_next = False
            return None
        self._next_id += 1
        self.posted.append((token_id, side, price, size, post_only))
        return {"orderID": f"order-{self._next_id}"}

    def cancel(self, order_id):
        self.cancelled.append(order_id)
        return True

    def cancel_all(self):
        return True


def book(bid=0.48, ask=0.52, token="t1"):
    return Book(
        token_id=token,
        bids=[Level(bid, 500)],
        asks=[Level(ask, 500)],
        tick_size=0.01,
        min_order_size=5.0,
    )


@pytest.fixture
def rig():
    gw = FakeGateway()
    risk = RiskManager(RiskLimits(max_position_usd_per_market=500,
                                  max_total_exposure_usd=5_000))
    om = OrderManager(gw, risk, requote_threshold=0.003)
    return gw, risk, om


class TestPipeline:
    def test_quote_reaches_the_gateway_as_post_only(self, rig):
        gw, risk, om = rig
        decision = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule()
        )
        assert decision.quotes
        result = om.reconcile(decision.quotes)

        assert len(result.posted) == 1
        token, side, price, size, post_only = gw.posted[0]
        assert side == "BUY"
        assert post_only is True, "a maker order that crosses is a taker order"
        assert price < 0.52

    def test_stable_quote_is_kept_not_rechurned(self, rig):
        """Re-posting an unchanged quote would surrender queue position,
        which is most of the value of quoting passively."""
        gw, risk, om = rig
        quotes = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule()
        ).quotes

        om.reconcile(quotes)
        assert len(gw.posted) == 1

        second = om.reconcile(quotes)
        assert len(gw.posted) == 1, "should not have re-posted"
        assert len(second.kept) == 1
        assert second.cancelled == []

    def test_moved_quote_is_replaced(self, rig):
        gw, risk, om = rig
        s = MakerStrategy()
        om.reconcile(s.quote("t1", book(), FairValue(0.50, 0.008), FeeSchedule()).quotes)
        om.reconcile(s.quote("t1", book(0.58, 0.62), FairValue(0.60, 0.008),
                             FeeSchedule()).quotes)

        assert len(gw.cancelled) == 1
        assert len(gw.posted) == 2

    def test_risk_rejection_stops_the_order(self, rig):
        gw, _, _ = rig
        tight = RiskManager(RiskLimits(max_position_usd_per_market=1))
        om = OrderManager(gw, tight)

        quotes = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule()
        ).quotes
        result = om.reconcile(quotes)

        assert result.posted == []
        assert gw.posted == []
        assert "position cap" in result.rejected[0][1]

    def test_gateway_failure_is_not_recorded_as_resting(self, rig):
        """If the exchange rejects an order we must not believe it is live,
        or we will never replace it."""
        gw, risk, om = rig
        gw.fail_next = True
        quotes = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule()
        ).quotes

        result = om.reconcile(quotes)
        assert result.posted == []
        assert om.resting_for("t1", "BUY") is None
        assert risk.open_order_count == 0

    def test_fill_updates_position_and_frees_the_slot(self, rig):
        gw, risk, om = rig
        quotes = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule()
        ).quotes
        om.reconcile(quotes)
        assert risk.open_order_count == 1

        om.on_fill("t1", "BUY", 0.48, quotes[0].size)

        assert risk.open_order_count == 0
        assert om.resting_for("t1", "BUY") is None
        assert risk.position("t1").shares == pytest.approx(quotes[0].size)

    def test_partial_fill_leaves_the_order_resting(self, rig):
        gw, risk, om = rig
        quotes = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule()
        ).quotes
        om.reconcile(quotes)

        om.on_fill("t1", "BUY", 0.48, quotes[0].size / 2)

        resting = om.resting_for("t1", "BUY")
        assert resting is not None
        assert resting.size == pytest.approx(quotes[0].size / 2)
        assert risk.open_order_count == 1

    def test_round_trip_accumulates_pnl(self, rig):
        gw, risk, om = rig
        om.on_fill("t1", "BUY", 0.40, 100)
        om.on_fill("t1", "SELL", 0.50, 100)
        assert risk.session_realised_pnl == pytest.approx(10.0)

    def test_halt_blocks_all_new_quotes(self, rig):
        gw, risk, om = rig
        risk.halt("manual stop")
        quotes = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule()
        ).quotes

        result = om.reconcile(quotes)
        assert result.posted == []
        assert "halted" in result.rejected[0][1]

    def test_untouched_tokens_are_left_alone(self, rig):
        """A market-data failure on one token must not silently pull quotes
        on every other token."""
        gw, risk, om = rig
        s = MakerStrategy()
        om.reconcile(s.quote("t1", book(token="t1"), FairValue(0.50, 0.008),
                             FeeSchedule()).quotes)
        om.reconcile(s.quote("t2", book(token="t2"), FairValue(0.50, 0.008),
                             FeeSchedule()).quotes)
        assert len(gw.posted) == 2

        # A cycle that only sees t1 must not cancel t2.
        om.reconcile(s.quote("t1", book(token="t1"), FairValue(0.50, 0.008),
                             FeeSchedule()).quotes)
        assert gw.cancelled == []
        assert om.resting_for("t2", "BUY") is not None


class TestSettings:
    def test_defaults_to_dry_run(self, monkeypatch):
        monkeypatch.delenv("POLYBOT_MODE", raising=False)
        assert Settings.from_env().mode is Mode.DRY_RUN

    def test_unknown_mode_falls_back_to_dry_run(self, monkeypatch):
        """A typo in the mode must never silently become live trading."""
        monkeypatch.setenv("POLYBOT_MODE", "liev")
        assert Settings.from_env().mode is Mode.DRY_RUN

    def test_live_mode_requires_credentials(self, monkeypatch):
        monkeypatch.setenv("POLYBOT_MODE", "live")
        monkeypatch.delenv("POLYBOT_PRIVATE_KEY", raising=False)
        s = Settings.from_env()
        assert s.mode is Mode.LIVE
        with pytest.raises(RuntimeError):
            s.require_credentials()

    def test_maker_params_from_env(self, monkeypatch):
        monkeypatch.setenv("POLYBOT_MIN_EDGE", "0.02")
        assert MakerParams.from_env().min_edge_per_share == pytest.approx(0.02)
