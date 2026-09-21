"""Hyperliquid adapter.

The point of these tests is that the venue-specific mapping is correct, so
the venue-agnostic fingerprint engine downstream receives clean input.
"""

import pytest

from polybot.research.fingerprint import build_fingerprint, classify
from polybot.venues.hyperliquid import (
    _window_performance,
    iter_windows,
    summarise_fills,
    to_common_fills,
)


def fill(px="100", sz="2", side="B", crossed=True, fee="0.05",
         closed_pnl="0", direction="Open Long", coin="ETH", t=1_700_000_000_000):
    return {
        "coin": coin, "px": px, "sz": sz, "side": side, "crossed": crossed,
        "fee": fee, "closedPnl": closed_pnl, "dir": direction, "time": t,
        "hash": f"0x{t}", "oid": t,
    }


class TestSummarise:
    def test_counts_maker_and_taker_exactly(self):
        """The whole reason this venue is better: no differencing hack."""
        s = summarise_fills([
            fill(crossed=True), fill(crossed=True), fill(crossed=False),
        ])
        assert s.taker_fills == 2
        assert s.maker_fills == 1
        assert s.maker_ratio == pytest.approx(1 / 3)

    def test_fee_drag_measured_against_notional(self):
        s = summarise_fills([fill(px="100", sz="1", fee="0.02")])
        assert s.total_notional_usd == pytest.approx(100.0)
        assert s.total_fees_usd == pytest.approx(0.02)
        assert s.fee_drag_pct == pytest.approx(0.02)

    def test_pnl_counted_only_on_closes(self):
        """Counting opens would report a win rate over trades that have not
        had an outcome -- the distortion that inflates leaderboards."""
        s = summarise_fills([
            fill(direction="Open Long", closed_pnl="0"),
            fill(direction="Close Long", closed_pnl="50"),
            fill(direction="Close Long", closed_pnl="-20"),
        ])
        assert s.winning_closes == 1
        assert s.losing_closes == 1
        assert s.realised_pnl_usd == pytest.approx(30.0)
        assert s.close_win_rate == pytest.approx(0.5)

    def test_liquidations_count_as_closes(self):
        s = summarise_fills([fill(direction="Liquidated Long", closed_pnl="-500")])
        assert s.losing_closes == 1

    def test_net_pnl_subtracts_fees(self):
        s = summarise_fills([
            fill(direction="Close Long", closed_pnl="100", fee="3"),
        ])
        assert s.net_pnl_after_fees == pytest.approx(97.0)

    def test_win_rate_none_without_closes(self):
        assert summarise_fills([fill()]).close_win_rate is None

    def test_empty(self):
        s = summarise_fills([])
        assert s.total_fills == 0
        assert s.maker_ratio == 0.0
        assert s.fee_drag_pct == 0.0

    def test_tolerates_missing_fields(self):
        s = summarise_fills([{"coin": "ETH"}])
        assert s.total_fills == 1
        assert s.total_notional_usd == 0.0


class TestNormalisation:
    def test_maps_to_fingerprint_shape(self):
        out = to_common_fills([fill(px="100", sz="2", side="B")])
        r = out[0]
        assert r["side"] == "BUY"
        assert r["price"] == pytest.approx(100.0)
        assert r["size"] == pytest.approx(2.0)
        assert r["usdcSize"] == pytest.approx(200.0)

    def test_sell_side_mapped(self):
        assert to_common_fills([fill(side="A")])[0]["side"] == "SELL"

    def test_milliseconds_converted_to_seconds(self):
        """Fingerprint works in seconds; a missed conversion would make every
        hold time look 1000x too long."""
        out = to_common_fills([fill(t=1_700_000_000_000)])
        assert out[0]["timestamp"] == 1_700_000_000

    def test_feeds_the_shared_fingerprint_engine(self):
        fills = [
            fill(coin=f"C{i%20}", t=1_700_000_000_000 + i * 60_000, sz="1", px="50")
            for i in range(3_000)
        ]
        s = summarise_fills(fills)
        fp = build_fingerprint("0xabc", to_common_fills(fills),
                               taker_fill_count=s.taker_fills)
        assert fp.total_trades == 3_000
        assert fp.distinct_markets == 20
        assert classify(fp).label in {
            "SYSTEMATIC_MAKER", "MOMENTUM_TAKER", "UNCLASSIFIED",
        }

    def test_maker_heavy_account_classifies_as_maker(self):
        fills = [
            fill(coin=f"C{i%50}", t=1_700_000_000_000 + i * 60_000,
                 sz="1", px="50", crossed=False)
            for i in range(3_000)
        ]
        s = summarise_fills(fills)
        fp = build_fingerprint("0xabc", to_common_fills(fills),
                               taker_fill_count=s.taker_fills)
        assert fp.maker_ratio == pytest.approx(1.0)
        assert classify(fp).label == "SYSTEMATIC_MAKER"


class TestWindowing:
    def test_walks_backwards_and_covers_the_range(self):
        w = list(iter_windows(0, 86_400_000 * 3, step_hours=24))
        assert len(w) == 3
        assert w[0][1] == 86_400_000 * 3
        assert w[-1][0] == 0
        for s, e in w:
            assert s < e

    def test_no_windows_for_empty_range(self):
        assert list(iter_windows(100, 100)) == []


class TestLeaderboardParsing:
    def test_extracts_named_window(self):
        row = {"windowPerformances": [
            ["day", {"pnl": "1", "vlm": "10"}],
            ["month", {"pnl": "500", "vlm": "9000", "roi": "0.25"}],
        ]}
        perf = _window_performance(row, "month")
        assert perf["pnl"] == "500"

    def test_missing_window_returns_empty(self):
        assert _window_performance({"windowPerformances": []}, "month") == {}

    def test_malformed_row(self):
        assert _window_performance({}, "month") == {}
