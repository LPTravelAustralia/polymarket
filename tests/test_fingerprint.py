"""Tests for the wallet-profiling logic, using synthetic histories shaped
like the two documented extremes: the conviction whale and the systematic
maker."""

import pytest

from polybot.research.fingerprint import (
    build_fingerprint,
    classify,
    match_round_trips,
    price_histogram,
    summarise_income,
    trade_notional,
)

HOUR = 3600
DAY = 86_400


def trade(ts, side, price, size, asset="A", condition="m1"):
    return {
        "timestamp": ts, "side": side, "price": price,
        "size": size, "asset": asset, "conditionId": condition,
    }


class TestNotional:
    def test_prefers_explicit_usdc_size(self):
        assert trade_notional({"usdcSize": 42.0, "size": 100, "price": 0.5}) == 42.0

    def test_falls_back_to_size_times_price(self):
        assert trade_notional({"size": 100, "price": 0.5}) == pytest.approx(50.0)

    def test_handles_junk(self):
        assert trade_notional({"size": None, "price": "abc"}) == 0.0


class TestRoundTrips:
    def test_simple_pair(self):
        trips = match_round_trips([
            trade(0, "BUY", 0.40, 100),
            trade(2 * HOUR, "SELL", 0.50, 100),
        ])
        assert len(trips) == 1
        assert trips[0].hold_seconds == 2 * HOUR
        assert trips[0].gross_pnl == pytest.approx(10.0)

    def test_fifo_order(self):
        """Selling 100 against two 50-lots must match the older lot first."""
        trips = match_round_trips([
            trade(0, "BUY", 0.40, 50),
            trade(HOUR, "BUY", 0.60, 50),
            trade(2 * HOUR, "SELL", 0.50, 100),
        ])
        assert len(trips) == 2
        assert trips[0].entry_price == 0.40
        assert trips[1].entry_price == 0.60
        assert sum(t.gross_pnl for t in trips) == pytest.approx(0.0)

    def test_partial_fill_leaves_remainder_open(self):
        trips = match_round_trips([
            trade(0, "BUY", 0.40, 100),
            trade(HOUR, "SELL", 0.50, 30),
        ])
        assert len(trips) == 1
        assert trips[0].size == pytest.approx(30)

    def test_separate_assets_do_not_cross_match(self):
        trips = match_round_trips([
            trade(0, "BUY", 0.40, 100, asset="A"),
            trade(HOUR, "SELL", 0.50, 100, asset="B"),
        ])
        assert trips == []

    def test_unsorted_input_is_handled(self):
        """A buy-and-hold wallet whose API rows arrive newest-first must not
        produce a negative hold time."""
        trips = match_round_trips([
            trade(2 * HOUR, "SELL", 0.50, 100),
            trade(0, "BUY", 0.40, 100),
        ])
        assert len(trips) == 1
        assert trips[0].hold_seconds == 2 * HOUR


class TestHistogram:
    def test_buckets_by_price(self):
        h = price_histogram([
            trade(0, "BUY", 0.02, 1), trade(0, "BUY", 0.50, 1), trade(0, "BUY", 0.97, 1),
        ])
        assert h["0.00-0.05"] == 1
        assert h["0.35-0.65"] == 1
        assert h["0.95-1.00"] == 1

    def test_ignores_out_of_range(self):
        h = price_histogram([trade(0, "BUY", 1.4, 1)])
        assert sum(h.values()) == 0


class TestIncome:
    def test_separates_rewards_from_trading(self):
        income = summarise_income([
            {"type": "TRADE", "usdcSize": 100},
            {"type": "REWARD", "usdcSize": 5},
            {"type": "REWARD", "usdcSize": 7},
            {"type": "SPLIT", "usdcSize": 50},
            {"type": "REDEEM", "usdcSize": 200},
        ])
        assert income.trade_count == 1
        assert income.reward_events == 2
        assert income.reward_usd == pytest.approx(12.0)
        assert income.structural_events == 1
        assert income.redeem_usd == pytest.approx(200.0)
        assert income.reward_dependent


class TestFingerprint:
    def test_empty_history(self):
        fp = build_fingerprint("0xabc", [])
        assert fp.total_trades == 0
        assert fp.maker_ratio == 0.0

    def test_maker_ratio_from_differencing(self):
        trades = [trade(i * HOUR, "BUY", 0.5, 10) for i in range(100)]
        fp = build_fingerprint("0xabc", trades, taker_fill_count=20)
        assert fp.taker_fills == 20
        assert fp.maker_fills == 80
        assert fp.maker_ratio == pytest.approx(0.8)

    def test_taker_count_cannot_exceed_total(self):
        trades = [trade(i, "BUY", 0.5, 10) for i in range(10)]
        fp = build_fingerprint("0xabc", trades, taker_fill_count=999)
        assert fp.taker_fills == 10
        assert fp.maker_fills == 0

    def test_concentration_across_markets(self):
        trades = (
            [trade(i, "BUY", 0.5, 100, condition="big") for i in range(9)]
            + [trade(100, "BUY", 0.5, 100, condition="small")]
        )
        fp = build_fingerprint("0xabc", trades)
        assert fp.distinct_markets == 2
        assert fp.top_market_volume_share == pytest.approx(0.9)

    def test_win_rate_ignores_undecided_positions(self):
        fp = build_fingerprint(
            "0xabc",
            [trade(0, "BUY", 0.5, 10)],
            positions=[{"cashPnl": 100}, {"cashPnl": -50}, {"cashPnl": 0.0}],
        )
        assert fp.win_rate == pytest.approx(0.5)
        assert fp.realised_pnl == pytest.approx(50.0)


class TestClassification:
    def test_conviction_whale(self):
        """Few fills, enormous size, concentrated -- the Theo4 shape."""
        trades = [
            trade(i * 30 * DAY, "BUY", 0.45, 2_000_000, asset=f"a{i % 8}",
                  condition=f"m{i % 8}")
            for i in range(18)
        ]
        arch = classify(build_fingerprint("0xwhale", trades, taker_fill_count=18))
        assert arch.label == "CONVICTION_WHALE"
        assert arch.replicable is False

    def test_systematic_maker(self):
        """Many tiny passive fills across many markets -- the swisstony shape,
        and the one the bot is modelled on."""
        trades = [
            trade(i * 60, "BUY", 0.5, 90, asset=f"a{i % 500}", condition=f"m{i % 500}")
            for i in range(5_000)
        ]
        arch = classify(build_fingerprint("0xmaker", trades, taker_fill_count=500))
        assert arch.label == "SYSTEMATIC_MAKER"
        assert arch.replicable is True

    def test_momentum_taker_is_flagged_as_risky(self):
        trades = [
            trade(i * 60, "BUY", 0.5, 100, asset=f"a{i % 50}", condition=f"m{i % 50}")
            for i in range(1_000)
        ]
        arch = classify(build_fingerprint("0xtaker", trades, taker_fill_count=950))
        assert arch.label == "MOMENTUM_TAKER"
        assert "do NOT copy" in arch.bot_translation.lower() or \
               "not copy" in arch.bot_translation.lower()

    def test_reward_farmer_detected_before_maker(self):
        """A wallet whose income is really a liquidity subsidy must not be
        sold to the user as a systematic maker."""
        trades = [
            trade(i * 60, "BUY", 0.5, 20, asset=f"a{i % 200}", condition=f"m{i % 200}")
            for i in range(3_000)
        ]
        activity = [{"type": "REWARD", "usdcSize": 50} for _ in range(300)]
        fp = build_fingerprint("0xfarm", trades, activity=activity, taker_fill_count=100)
        arch = classify(fp)
        assert arch.label == "REWARD_FARMER"
        assert "subsidy" in " ".join(arch.rationale).lower()

    def test_structural_arb_detected(self):
        trades = [
            trade(i * 60, "BUY", 0.5, 100, asset=f"a{i % 20}", condition=f"m{i % 20}")
            for i in range(300)
        ]
        activity = [{"type": "MERGE", "usdcSize": 100} for _ in range(100)]
        arch = classify(build_fingerprint("0xarb", trades, activity=activity))
        assert arch.label == "STRUCTURAL_ARB"

    def test_sparse_history_is_unclassified(self):
        arch = classify(build_fingerprint("0x", [trade(0, "BUY", 0.5, 10)]))
        assert arch.label == "UNCLASSIFIED"
        assert arch.replicable is False
