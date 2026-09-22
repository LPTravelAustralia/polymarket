"""Snapshot storage.

Polymarket does not serve deep historical order books, so anything you want
to backtest against you have to record yourself, starting now. That is
annoying but it is also the honest situation: a backtest built on
reconstructed or interpolated books will flatter a market-making strategy
enormously, because the whole question is whether you would actually have
been filled.

Format is gzipped JSONL -- one record per line, append-only, greppable, and
survives a crashed recorder with at most one truncated line.
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..clients.clob import Book, Level

log = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """One order book at one instant."""

    ts: float
    token_id: str
    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)
    tick_size: float = 0.001
    min_order_size: float = 5.0

    @classmethod
    def from_book(cls, book: Book, ts: float) -> "Snapshot":
        return cls(
            ts=ts,
            token_id=book.token_id,
            bids=[(l.price, l.size) for l in book.bids],
            asks=[(l.price, l.size) for l in book.asks],
            tick_size=book.tick_size,
            min_order_size=book.min_order_size,
        )

    def to_book(self) -> Book:
        return Book(
            token_id=self.token_id,
            bids=[Level(p, s) for p, s in self.bids],
            asks=[Level(p, s) for p, s in self.asks],
            tick_size=self.tick_size,
            min_order_size=self.min_order_size,
        )

    @property
    def best_bid(self) -> float | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0][0] if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    def size_at(self, side: str, price: float) -> float:
        """Resting size at a price level -- the queue you join.

        Prices are floats off a JSON wire, so compare with a tolerance of
        half a tick rather than exactly.
        """
        levels = self.bids if side.upper() == "BUY" else self.asks
        tol = self.tick_size / 2.0
        return sum(s for p, s in levels if abs(p - price) < tol)

    def to_json(self) -> str:
        return json.dumps({
            "ts": round(self.ts, 3),
            "t": self.token_id,
            "b": [[round(p, 4), round(s, 2)] for p, s in self.bids],
            "a": [[round(p, 4), round(s, 2)] for p, s in self.asks],
            "ts_": self.tick_size,
            "m": self.min_order_size,
        }, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "Snapshot":
        d = json.loads(line)
        return cls(
            ts=d["ts"],
            token_id=d["t"],
            bids=[(p, s) for p, s in d.get("b", [])],
            asks=[(p, s) for p, s in d.get("a", [])],
            tick_size=d.get("ts_", 0.001),
            min_order_size=d.get("m", 5.0),
        )


@dataclass
class PublicTrade:
    """A trade that happened on the tape.

    Needed for honest fill simulation: a resting order fills when the market
    trades through it, not when the quoted price merely touches it.
    """

    ts: float
    token_id: str
    price: float
    size: float
    side: str = ""     # taker side, when known

    def to_json(self) -> str:
        return json.dumps({
            "ts": round(self.ts, 3), "t": self.token_id,
            "p": round(self.price, 4), "s": round(self.size, 2), "sd": self.side,
        }, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "PublicTrade":
        d = json.loads(line)
        return cls(ts=d["ts"], token_id=d["t"], price=d["p"],
                   size=d["s"], side=d.get("sd", ""))


class SnapshotWriter:
    """Append-only gzip JSONL writer."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = gzip.open(self.path, "at", encoding="utf-8")
        self._count = 0

    def write(self, record: Snapshot | PublicTrade) -> None:
        self._fh.write(record.to_json() + "\n")
        self._count += 1
        # Flush periodically so a killed recorder loses seconds, not hours.
        if self._count % 200 == 0:
            self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.flush()
            self._fh.close()
        except Exception:
            log.debug("writer close failed for %s", self.path, exc_info=True)

    def __enter__(self) -> "SnapshotWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _read_lines(path: Path) -> Iterator[str]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:  # type: ignore[operator]
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            yield line


def read_snapshots(path: Path) -> Iterator[Snapshot]:
    """Stream snapshots, skipping a trailing truncated line from a crash."""
    for line in _read_lines(Path(path)):
        try:
            yield Snapshot.from_json(line)
        except (json.JSONDecodeError, KeyError, TypeError):
            log.warning("skipping malformed snapshot line in %s", path)


def read_trades(path: Path) -> Iterator[PublicTrade]:
    for line in _read_lines(Path(path)):
        try:
            yield PublicTrade.from_json(line)
        except (json.JSONDecodeError, KeyError, TypeError):
            log.warning("skipping malformed trade line in %s", path)


def load_session(directory: Path) -> tuple[list[Snapshot], list[PublicTrade]]:
    """Load a recording directory, sorted by time."""
    directory = Path(directory)
    snaps: list[Snapshot] = []
    trades: list[PublicTrade] = []

    for f in sorted(directory.glob("books*.jsonl*")):
        snaps.extend(read_snapshots(f))
    for f in sorted(directory.glob("trades*.jsonl*")):
        trades.extend(read_trades(f))

    snaps.sort(key=lambda s: s.ts)
    trades.sort(key=lambda t: t.ts)
    log.info("Loaded %d snapshots and %d trades from %s",
             len(snaps), len(trades), directory)
    return snaps, trades
