"""Record order books and the trade tape to disk.

Run this before you backtest anything. Polymarket serves current books and
recent trades but not deep history, so the dataset you will eventually test
against is the one you start collecting today.

Record for at least a week across the markets you actually intend to quote.
Sampling a category you will not trade produces a backtest about a strategy
you will not run.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..clients.clob import ClobGateway
from ..clients.data_api import DataAPI
from .store import PublicTrade, Snapshot, SnapshotWriter

log = logging.getLogger(__name__)


@dataclass
class RecorderStats:
    snapshots: int = 0
    trades: int = 0
    odds: int = 0
    cycles: int = 0
    errors: int = 0


class MarketRecorder:
    def __init__(
        self,
        gateway: ClobGateway,
        out_dir: Path,
        *,
        interval: float = 2.0,
        record_trades: bool = True,
        odds_provider: object | None = None,
        sport_keys: list[str] | None = None,
        odds_interval: float = 120.0,
    ):
        self.gateway = gateway
        self.out_dir = Path(out_dir)
        self.interval = interval
        self.record_trades = record_trades
        # Recording odds alongside books is what makes a sports model
        # backtestable later. You cannot buy historical odds back, so capture
        # them from the first run even if nothing consumes them yet.
        self.odds_provider = odds_provider
        self.sport_keys = sport_keys or []
        self.odds_interval = odds_interval
        self.stats = RecorderStats()
        self._stop = False
        self._seen_trades: set[str] = set()
        self._data_api: DataAPI | None = None
        self._last_odds_poll = 0.0

    def install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("Signal %s -- finishing current cycle and closing files", signum)
            self._stop = True

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def stop(self) -> None:
        self._stop = True

    def run(
        self,
        token_ids: list[str],
        condition_ids: list[str] | None = None,
        *,
        duration_seconds: float | None = None,
        max_cycles: int | None = None,
    ) -> RecorderStats:
        if not token_ids:
            log.error("No tokens to record")
            return self.stats

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        session = self.out_dir / stamp
        book_path = session / "books.jsonl.gz"
        trade_path = session / "trades.jsonl.gz"

        log.info("Recording %d tokens to %s every %.1fs",
                 len(token_ids), session, self.interval)

        started = time.monotonic()
        if self.record_trades and condition_ids:
            self._data_api = DataAPI()

        books = SnapshotWriter(book_path)
        trades = SnapshotWriter(trade_path) if self.record_trades else None
        odds = SnapshotWriter(session / "odds.jsonl.gz") if self.odds_provider else None

        try:
            while not self._stop:
                if max_cycles is not None and self.stats.cycles >= max_cycles:
                    break
                if duration_seconds is not None and \
                        time.monotonic() - started >= duration_seconds:
                    break

                cycle_start = time.monotonic()
                try:
                    self._record_books(token_ids, books)
                    if trades is not None and condition_ids:
                        self._record_trades(condition_ids, trades)
                    if odds is not None:
                        self._record_odds(odds)
                except Exception:
                    self.stats.errors += 1
                    log.exception("Recording cycle failed; continuing")

                self.stats.cycles += 1
                if self.stats.cycles % 30 == 0:
                    log.info("... %d cycles, %d snapshots, %d trades",
                             self.stats.cycles, self.stats.snapshots, self.stats.trades)

                time.sleep(max(0.0, self.interval - (time.monotonic() - cycle_start)))
        finally:
            books.close()
            if trades is not None:
                trades.close()
            if odds is not None:
                odds.close()
            if self._data_api is not None:
                self._data_api.close()
            log.info(
                "Recorded %d snapshots, %d trades, %d odds over %d cycles "
                "(%d errors) into %s",
                self.stats.snapshots, self.stats.trades, self.stats.odds,
                self.stats.cycles, self.stats.errors, session,
            )

        return self.stats

    def _record_books(self, token_ids: list[str], writer: SnapshotWriter) -> None:
        now = time.time()
        books = self.gateway.books(token_ids)
        for token_id, book in books.items():
            if not book.bids and not book.asks:
                continue
            writer.write(Snapshot.from_book(book, now))
            self.stats.snapshots += 1

    def _record_trades(self, condition_ids: list[str], writer: SnapshotWriter) -> None:
        """Poll recent public trades, de-duplicating across cycles.

        Polling cannot guarantee a complete tape -- a burst between polls can
        be missed. Missing trades makes the fill simulator MORE pessimistic
        (queue drains slower than it really did), which is the safe direction
        to be wrong in, but it is a real limitation of a REST recorder.
        """
        if self._data_api is None:
            return

        for cid in condition_ids:
            try:
                rows = list(self._data_api.trades(market=cid, max_items=100))
            except Exception as exc:
                log.debug("trade poll failed for %s: %s", cid[:12], exc)
                continue

            for row in rows:
                key = str(row.get("transactionHash") or "") + str(row.get("timestamp") or "")
                if not key or key in self._seen_trades:
                    continue
                self._seen_trades.add(key)

                try:
                    writer.write(
                        PublicTrade(
                            ts=float(row.get("timestamp") or 0),
                            token_id=str(row.get("asset") or ""),
                            price=float(row.get("price") or 0),
                            size=float(row.get("size") or 0),
                            side=str(row.get("side") or ""),
                        )
                    )
                    self.stats.trades += 1
                except (TypeError, ValueError):
                    continue

        # Bound memory on a long recording run.
        if len(self._seen_trades) > 200_000:
            self._seen_trades.clear()
            log.debug("cleared trade dedup cache")

    def _record_odds(self, writer: SnapshotWriter) -> None:
        """Poll the odds feed on its own, slower cadence.

        Odds APIs are metered far more tightly than Polymarket's, so this
        runs on `odds_interval` rather than the book interval.
        """
        now = time.monotonic()
        if now - self._last_odds_poll < self.odds_interval:
            return
        self._last_odds_poll = now

        wall = time.time()
        for key in self.sport_keys:
            try:
                events = self.odds_provider.events(key)  # type: ignore[union-attr]
            except Exception as exc:
                log.warning("odds poll failed for %s: %s", key, exc)
                continue
            for event in events:
                writer.write(_OddsLine(event.to_json(wall)))
                self.stats.odds += 1


class _OddsLine:
    """Adapter so odds events can use the same writer as books and trades."""

    def __init__(self, payload: str):
        self._payload = payload

    def to_json(self) -> str:
        return self._payload
