"""Hyperliquid websocket recorder message handling.

The recorder swallows per-message exceptions so one malformed frame cannot
kill a long recording. That makes silent breakage the risk, so the parsing
is tested directly rather than through the socket.
"""

import gzip
from pathlib import Path

import pytest

from polybot.marketdata.store import SnapshotWriter, read_snapshots, read_trades
from polybot.venues.hl_recorder import HyperliquidRecorder, _infer_tick


def book_msg(coin="BTC", bid="100.5", ask="100.6"):
    return {
        "channel": "l2Book",
        "data": {
            "coin": coin,
            "time": 1_789_000_000_000,
            "levels": [
                [{"px": bid, "sz": "2.0", "n": 3}, {"px": "100.4", "sz": "1.0", "n": 1}],
                [{"px": ask, "sz": "1.5", "n": 2}, {"px": "100.7", "sz": "3.0", "n": 4}],
            ],
        },
    }


def trade_msg(coin="BTC", side="B", px="100.55", sz="0.5"):
    return {
        "channel": "trades",
        "data": [{
            "coin": coin, "side": side, "px": px, "sz": sz,
            "time": 1_789_000_000_500, "hash": "0xabc",
        }],
    }


@pytest.fixture
def rec(tmp_path):
    r = HyperliquidRecorder(tmp_path, ["BTC"])
    r._books = SnapshotWriter(tmp_path / "books.jsonl.gz")
    r._trades = SnapshotWriter(tmp_path / "trades.jsonl.gz")
    return r


class TestBookHandling:
    def test_writes_a_snapshot(self, rec, tmp_path):
        rec._handle(book_msg())
        assert rec.stats.snapshots == 1
        rec._books.close()
        snaps = list(read_snapshots(tmp_path / "books.jsonl.gz"))
        assert len(snaps) == 1
        assert snaps[0].best_bid == pytest.approx(100.5)
        assert snaps[0].best_ask == pytest.approx(100.6)

    def test_thins_by_interval(self, rec):
        """l2Book pushes on every change; markout does not need that rate."""
        rec.snapshot_interval = 60.0
        rec._handle(book_msg())
        rec._handle(book_msg())
        assert rec.stats.snapshots == 1

    def test_thinning_is_per_coin(self, rec):
        rec.snapshot_interval = 60.0
        rec._handle(book_msg(coin="BTC"))
        rec._handle(book_msg(coin="ETH"))
        assert rec.stats.snapshots == 2

    def test_one_sided_book_skipped(self, rec):
        msg = book_msg()
        msg["data"]["levels"][1] = []
        rec._handle(msg)
        assert rec.stats.snapshots == 0

    def test_malformed_levels_skipped(self, rec):
        msg = book_msg()
        msg["data"]["levels"] = [[{"px": "bad", "sz": "x"}], []]
        rec._handle(msg)
        assert rec.stats.snapshots == 0

    def test_missing_fields_skipped(self, rec):
        rec._handle({"channel": "l2Book", "data": {}})
        assert rec.stats.snapshots == 0


class TestTradeHandling:
    def test_writes_trades_with_aggressor_side(self, rec, tmp_path):
        rec._handle(trade_msg(side="B"))
        rec._handle(trade_msg(side="A"))
        assert rec.stats.trades == 2
        rec._trades.close()
        trades = list(read_trades(tmp_path / "trades.jsonl.gz"))
        assert [t.side for t in trades] == ["BUY", "SELL"]

    def test_milliseconds_converted_to_seconds(self, rec, tmp_path):
        """Trades in ms against snapshots in seconds would put every fill
        ~56,000 years after its book."""
        rec._handle(trade_msg())
        rec._trades.close()
        t = list(read_trades(tmp_path / "trades.jsonl.gz"))[0]
        assert 1_700_000_000 < t.ts < 2_000_000_000

    def test_bad_trade_counted_as_error_not_crash(self, rec):
        rec._handle({"channel": "trades", "data": [{"coin": "BTC"}]})
        assert rec.stats.trades == 0
        assert rec.stats.errors == 1

    def test_unknown_channel_ignored(self, rec):
        rec._handle({"channel": "subscriptionResponse", "data": {}})
        assert rec.stats.snapshots == 0
        assert rec.stats.trades == 0


class TestTickInference:
    def test_infers_from_quoted_precision(self):
        assert _infer_tick([100.5, 100.6]) == pytest.approx(0.1)
        assert _infer_tick([0.1234, 0.1235]) == pytest.approx(0.0001)

    def test_integers_fall_back(self):
        assert _infer_tick([100.0, 101.0]) == pytest.approx(0.01)
