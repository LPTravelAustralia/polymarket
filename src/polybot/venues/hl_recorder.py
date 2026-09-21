"""Record Hyperliquid books and trades over websocket.

**Why websocket rather than REST polling.** Hyperliquid exposes the public
trade tape only as a websocket subscription; there is no REST equivalent.
That is not a convenience issue, it is a correctness one:

Without the trade tape, the fill simulator can only produce *price-through*
fills -- the ones where the market ran clean past your quote. Those are
exactly the adverse subset. Calibrating adverse selection from them would
report a catastrophically negative number that describes the measurement,
not the market. The tape is what lets a quote fill *benignly*, through
ordinary queue turnover, and those fills are most of a real maker's flow.

Output is the venue-neutral `Snapshot`/`PublicTrade` format, so the existing
`polybot calibrate` machinery consumes it unchanged.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..marketdata.store import PublicTrade, Snapshot, SnapshotWriter

log = logging.getLogger(__name__)

WS_URL = "wss://api.hyperliquid.xyz/ws"


@dataclass
class HLRecorderStats:
    snapshots: int = 0
    trades: int = 0
    errors: int = 0
    started: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started


class HyperliquidRecorder:
    """Subscribes to l2Book and trades for a set of coins and writes both."""

    def __init__(self, out_dir: Path, coins: list[str]):
        self.out_dir = Path(out_dir)
        self.coins = [c.upper() for c in coins]
        self.stats = HLRecorderStats()
        self._stop = threading.Event()
        self._books: SnapshotWriter | None = None
        self._trades: SnapshotWriter | None = None
        self._ws = None
        # l2Book pushes on every change; at full rate that is far more data
        # than markout needs, so snapshots are thinned per coin.
        self._last_snap: dict[str, float] = {}
        self.snapshot_interval = 1.0

    def run(self, duration_seconds: float = 900.0) -> HLRecorderStats:
        import websocket

        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        session = self.out_dir / f"hl-{stamp}"
        self._books = SnapshotWriter(session / "books.jsonl.gz")
        self._trades = SnapshotWriter(session / "trades.jsonl.gz")
        log.info("Recording %d coins to %s for %.0fs",
                 len(self.coins), session, duration_seconds)

        def on_open(ws):
            for coin in self.coins:
                for sub in ({"type": "l2Book", "coin": coin},
                            {"type": "trades", "coin": coin}):
                    ws.send(json.dumps({"method": "subscribe", "subscription": sub}))
            log.info("Subscribed to %d channels", len(self.coins) * 2)

        def on_message(ws, message):
            try:
                self._handle(json.loads(message))
            except Exception:
                self.stats.errors += 1
                log.debug("message handling failed", exc_info=True)

        def on_error(ws, error):
            self.stats.errors += 1
            log.warning("websocket error: %s", error)

        self._ws = websocket.WebSocketApp(
            WS_URL, on_open=on_open, on_message=on_message, on_error=on_error
        )

        t = threading.Thread(target=self._ws.run_forever, daemon=True)
        t.start()

        try:
            deadline = time.time() + duration_seconds
            while time.time() < deadline and not self._stop.is_set():
                time.sleep(2.0)
                if int(self.stats.elapsed) % 60 < 2:
                    log.info("... %.0fs: %d snapshots, %d trades",
                             self.stats.elapsed, self.stats.snapshots, self.stats.trades)
        except KeyboardInterrupt:
            log.info("Interrupted")
        finally:
            self.stop()
            self._books.close()
            self._trades.close()
            log.info("Recorded %d snapshots and %d trades (%d errors) into %s",
                     self.stats.snapshots, self.stats.trades,
                     self.stats.errors, session)
            if self.stats.trades == 0:
                log.warning(
                    "NO TRADES captured. Adverse selection measured from this "
                    "session would reflect only price-through fills, which are "
                    "the adverse subset -- the resulting number would be wrong."
                )
        return self.stats

    def stop(self) -> None:
        self._stop.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass

    # ---------------------------------------------------------------- inner

    def _handle(self, msg: dict) -> None:
        channel = msg.get("channel")
        data = msg.get("data")

        if channel == "l2Book" and isinstance(data, dict):
            coin = data.get("coin")
            levels = data.get("levels")
            if not coin or not levels or len(levels) < 2:
                return
            now = time.time()
            if now - self._last_snap.get(coin, 0.0) < self.snapshot_interval:
                return
            self._last_snap[coin] = now

            def side(raw):
                out = []
                for lv in raw or []:
                    try:
                        px, sz = float(lv["px"]), float(lv["sz"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if px > 0 and sz > 0:
                        out.append((px, sz))
                return out

            bids, asks = side(levels[0]), side(levels[1])
            if not bids or not asks:
                return
            self._books.write(Snapshot(
                ts=now, token_id=coin,
                bids=sorted(bids, key=lambda x: -x[0])[:20],
                asks=sorted(asks, key=lambda x: x[0])[:20],
                tick_size=_infer_tick([p for p, _ in bids[:3]] + [p for p, _ in asks[:3]]),
                min_order_size=0.0,
            ))
            self.stats.snapshots += 1

        elif channel == "trades" and isinstance(data, list):
            for tr in data:
                try:
                    self._trades.write(PublicTrade(
                        ts=float(tr["time"]) / 1000.0,
                        token_id=str(tr["coin"]),
                        price=float(tr["px"]),
                        size=float(tr["sz"]),
                        # Hyperliquid reports the aggressor side.
                        side="BUY" if str(tr.get("side")) == "B" else "SELL",
                    ))
                    self.stats.trades += 1
                except (KeyError, TypeError, ValueError):
                    self.stats.errors += 1


def _infer_tick(prices: list[float]) -> float:
    worst = 0
    for p in prices:
        s = f"{p:.10f}".rstrip("0")
        if "." in s:
            worst = max(worst, len(s.split(".")[1]))
    return 10.0 ** (-worst) if worst else 0.01
