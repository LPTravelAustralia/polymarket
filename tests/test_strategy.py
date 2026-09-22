"""Tests for quoting, devigging and structural arbitrage."""

import pytest

from polybot.clients.clob import Book, Level
from polybot.config import ArbParams, MakerParams
from polybot.economics import FeeSchedule
from polybot.strategy.fair_value import (
    FairValue,
    MicropriceModel,
    american_to_implied,
    decimal_to_implied,
    devig_multiplicative,
    devig_power,
)
from polybot.strategy.maker import MakerStrategy, round_to_tick
from polybot.strategy.structural import find_basket_arb, find_complement_arb


def book(bid=0.48, ask=0.52, bid_size=500, ask_size=500, tick=0.01,
         token="t1", neg_risk=False):
    return Book(
        token_id=token,
        bids=[Level(bid, bid_size)],
        asks=[Level(ask, ask_size)],
        tick_size=tick,
        min_order_size=5.0,
        neg_risk=neg_risk,
    )


class TestRoundToTick:
    def test_directions(self):
        assert round_to_tick(0.4567, 0.01, direction="down") == pytest.approx(0.45)
        assert round_to_tick(0.4567, 0.01, direction="up") == pytest.approx(0.46)

    def test_exact_values_do_not_move(self):
        """Rounding an already-valid price would give away a tick of edge on
        every quote."""
        assert round_to_tick(0.45, 0.01, direction="down") == pytest.approx(0.45)
        assert round_to_tick(0.45, 0.01, direction="up") == pytest.approx(0.45)

    def test_fine_tick(self):
        assert round_to_tick(0.4567, 0.001, direction="down") == pytest.approx(0.456)
        assert round_to_tick(0.4567, 0.001, direction="up") == pytest.approx(0.457)


class TestBook:
    def test_mid_and_spread(self):
        b = book(0.48, 0.52)
        assert b.mid == pytest.approx(0.50)
        assert b.spread == pytest.approx(0.04)

    def test_microprice_leans_away_from_the_thick_side(self):
        """Heavy bid size means the ask is likelier to be hit, so the
        microprice should sit above the mid."""
        b = book(0.48, 0.52, bid_size=900, ask_size=100)
        assert b.microprice() > b.mid

    def test_vwap_returns_none_when_book_too_thin(self):
        b = book(ask_size=10)
        assert b.vwap_for_size("BUY", 100) is None

    def test_vwap_walks_levels(self):
        b = Book("t", bids=[], asks=[Level(0.50, 50), Level(0.55, 50)])
        assert b.vwap_for_size("BUY", 100) == pytest.approx(0.525)


class TestMakerQuoting:
    def test_does_not_short_without_inventory(self):
        """With no position there is nothing to sell -- selling would require
        minting a complete set, which is a different strategy."""
        d = MakerStrategy().quote("t1", book(), FairValue(0.50, 0.008), FeeSchedule())
        sides = {q.side for q in d.quotes}
        assert sides == {"BUY"}
        assert any("does not short" in s for s in d.skipped)

    def test_quotes_both_sides_when_holding_inventory(self):
        d = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule(),
            inventory_shares=100, max_inventory_shares=200,
        )
        assert {q.side for q in d.quotes} == {"BUY", "SELL"}

    def test_quotes_straddle_fair_value(self):
        d = MakerStrategy().quote(
            "t1", book(), FairValue(0.50, 0.008), FeeSchedule(),
            inventory_shares=100, max_inventory_shares=200,
        )
        bid = next(q for q in d.quotes if q.side == "BUY")
        ask = next(q for q in d.quotes if q.side == "SELL")
        assert bid.price < 0.50 < ask.price

    def test_never_crosses_the_book(self):
        """A fair value well above the offer must not produce a bid that
        crosses -- that would be a taker order paying the taker fee."""
        b = book(0.48, 0.52)
        d = MakerStrategy().quote("t1", b, FairValue(0.70, 0.008), FeeSchedule())
        for q in d.quotes:
            if q.side == "BUY":
                assert q.price < b.best_ask

    def test_never_offers_below_the_bid(self):
        b = book(0.48, 0.52)
        d = MakerStrategy().quote(
            "t1", b, FairValue(0.30, 0.008), FeeSchedule(),
            inventory_shares=100, max_inventory_shares=200,
        )
        for q in d.quotes:
            if q.side == "SELL":
                assert q.price > b.best_bid

    def test_refuses_thin_edge(self):
        """Huge model uncertainty widens the required band past what the
        book supports, so we decline rather than quote inside our own error."""
        params = MakerParams(min_edge_per_share=0.05)
        d = MakerStrategy(params).quote("t1", book(), FairValue(0.50, 0.008), FeeSchedule())
        assert d.quotes == []
        assert any("edge" in s for s in d.skipped)

    def test_refuses_outside_price_band(self):
        d = MakerStrategy().quote("t1", book(0.01, 0.03), FairValue(0.02, 0.005), FeeSchedule())
        assert d.quotes == []
        assert any("outside quotable band" in s for s in d.skipped)

    def test_refuses_empty_book(self):
        empty = Book("t1", bids=[], asks=[])
        d = MakerStrategy().quote("t1", empty, FairValue(0.50, 0.008), FeeSchedule())
        assert d.quotes == []

    def test_long_inventory_skews_quotes_down(self):
        """At the position limit the bot should stop bidding entirely."""
        s = MakerStrategy()
        flat = s.quote("t1", book(), FairValue(0.50, 0.008), FeeSchedule(),
                       inventory_shares=0, max_inventory_shares=200)
        loaded = s.quote("t1", book(), FairValue(0.50, 0.008), FeeSchedule(),
                         inventory_shares=200, max_inventory_shares=200)
        assert any(q.side == "BUY" for q in flat.quotes)
        assert not any(q.side == "BUY" for q in loaded.quotes)
        assert any("inventory limit" in s_ for s_ in loaded.skipped)

    def test_size_capped_by_book_depth(self):
        params = MakerParams(order_size_shares=1_000)
        d = MakerStrategy(params).quote(
            "t1", book(bid_size=100), FairValue(0.50, 0.008), FeeSchedule()
        )
        bid = next(q for q in d.quotes if q.side == "BUY")
        assert bid.size <= 100 * 0.25 + 1e-9

    def test_uncertainty_widens_the_spread(self):
        s = MakerStrategy()
        tight = s.quote("t1", book(), FairValue(0.50, 0.001), FeeSchedule(),
                        inventory_shares=100, max_inventory_shares=200)
        wide = s.quote("t1", book(), FairValue(0.50, 0.05), FeeSchedule(),
                       inventory_shares=100, max_inventory_shares=200)
        tight_bid = next((q.price for q in tight.quotes if q.side == "BUY"), None)
        wide_bid = next((q.price for q in wide.quotes if q.side == "BUY"), None)
        assert tight_bid is not None
        # A wider band means a lower bid, or no bid at all.
        assert wide_bid is None or wide_bid < tight_bid

    def test_requote_threshold(self):
        s = MakerStrategy(MakerParams())
        assert not s.should_requote(0.500, 0.5005)
        assert s.should_requote(0.500, 0.510)


class TestMicropriceModel:
    def test_returns_none_on_one_sided_book(self):
        m = MicropriceModel()
        assert m.estimate("t", Book("t", bids=[Level(0.4, 10)], asks=[])) is None

    def test_uncertainty_at_least_half_spread(self):
        fv = MicropriceModel().estimate("t", book(0.40, 0.60))
        assert fv is not None
        assert fv.uncertainty == pytest.approx(0.10)


class TestDevig:
    def test_multiplicative_normalises(self):
        out = devig_multiplicative([0.55, 0.50])
        assert sum(out) == pytest.approx(1.0)
        assert out[0] > out[1]

    def test_power_normalises(self):
        out = devig_power([0.55, 0.50])
        assert sum(out) == pytest.approx(1.0, abs=1e-6)

    def test_power_handles_underround(self):
        """Polymarket books genuinely trade under 1.0 -- that is the arb
        case -- so the devig must not blow up on it."""
        out = devig_power([0.45, 0.48])
        assert sum(out) == pytest.approx(1.0, abs=1e-6)

    def test_power_corrects_favourite_longshot_skew(self):
        """On a lopsided market the two methods must disagree, with the power
        method giving the favourite more and the longshot less."""
        mult = devig_multiplicative([0.90, 0.15])
        power = devig_power([0.90, 0.15])
        assert power[0] > mult[0]
        assert power[1] < mult[1]

    def test_already_fair_is_unchanged(self):
        out = devig_power([0.6, 0.4])
        assert out == pytest.approx([0.6, 0.4], abs=1e-6)

    def test_rejects_non_positive(self):
        with pytest.raises(ValueError):
            devig_power([0.5, 0.0])

    def test_odds_conversion(self):
        assert american_to_implied(100) == pytest.approx(0.5)
        assert american_to_implied(-200) == pytest.approx(2 / 3)
        assert decimal_to_implied(2.0) == pytest.approx(0.5)
        with pytest.raises(ValueError):
            decimal_to_implied(0.9)


class TestStructuralArb:
    def test_finds_genuine_complement_mispricing(self):
        yes = book(0.40, 0.45, token="yes")
        no = book(0.45, 0.50, token="no")   # asks sum to 0.95
        opp = find_complement_arb(yes, no, FeeSchedule(0.05), FeeSchedule(0.05))
        assert opp is not None
        assert opp.kind == "complement_buy"
        assert opp.gross_profit_per_share == pytest.approx(0.05)
        # Fees and assumed slippage must eat into it, not be ignored.
        assert 0 < opp.net_profit_per_share < opp.gross_profit_per_share

    def test_rejects_when_fees_eat_the_edge(self):
        """A 1c gross mispricing at mid prices is NOT arbitrage: two taker
        legs cost ~2.5c."""
        yes = book(0.45, 0.495, token="yes")
        no = book(0.45, 0.495, token="no")  # asks sum to 0.99
        assert find_complement_arb(yes, no, FeeSchedule(0.05), FeeSchedule(0.05)) is None

    def test_no_opportunity_when_priced_fairly(self):
        yes = book(0.48, 0.52, token="yes")
        no = book(0.48, 0.52, token="no")   # asks sum to 1.04
        assert find_complement_arb(yes, no, FeeSchedule(0.05), FeeSchedule(0.05)) is None

    def test_fee_free_category_lowers_the_bar(self):
        """Geopolitics markets carry no taker fee, so a mispricing that is
        not tradeable elsewhere is tradeable there."""
        yes = book(0.45, 0.485, token="yes")
        no = book(0.45, 0.485, token="no")  # asks sum to 0.97
        assert find_complement_arb(yes, no, FeeSchedule(0.05), FeeSchedule(0.05)) is None
        assert find_complement_arb(yes, no, FeeSchedule(0.0), FeeSchedule(0.0)) is not None

    def test_size_limited_by_thinnest_leg(self):
        yes = book(0.40, 0.45, ask_size=40, token="yes")
        no = book(0.45, 0.50, ask_size=900, token="no")
        opp = find_complement_arb(yes, no, FeeSchedule(0.05), FeeSchedule(0.05))
        assert opp is not None
        assert opp.size_shares == pytest.approx(40)

    def test_basket_requires_neg_risk_flag(self):
        """Three unrelated markets summing under 1.0 is not arbitrage unless
        they are genuinely mutually exclusive."""
        books = [book(0.20, 0.25, token=f"t{i}", neg_risk=False) for i in range(3)]
        schedules = [FeeSchedule(0.05)] * 3
        assert find_basket_arb(books, schedules) is None

    def test_basket_buy_found(self):
        books = [book(0.20, 0.25, token=f"t{i}", neg_risk=True) for i in range(3)]
        schedules = [FeeSchedule(0.0)] * 3   # asks sum to 0.75
        opp = find_basket_arb(books, schedules)
        assert opp is not None
        assert opp.kind == "basket_buy"
        assert opp.gross_profit_per_share == pytest.approx(0.25)

    def test_basket_sell_found(self):
        books = [book(0.40, 0.95, token=f"t{i}", neg_risk=True) for i in range(3)]
        schedules = [FeeSchedule(0.0)] * 3   # bids sum to 1.20
        opp = find_basket_arb(books, schedules)
        assert opp is not None
        assert opp.kind == "basket_sell"
        assert any("SPLIT" in n for n in opp.notes)

    def test_arb_params_gate_respected(self):
        yes = book(0.40, 0.45, token="yes")
        no = book(0.45, 0.50, token="no")
        strict = ArbParams(min_profit_per_share=0.99)
        assert find_complement_arb(yes, no, FeeSchedule(0.0), FeeSchedule(0.0), strict) is None
