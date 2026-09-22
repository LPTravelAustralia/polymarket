"""Queue-aware fill simulation.

This is the module that decides whether a backtest tells the truth.

The tempting shortcut is: "my bid was 0.48, the book touched 0.48, therefore
I filled." That is wrong, and wrong in the direction that makes a
market-making strategy look great. On a real CLOB you join the back of the
queue at your price. If 800 shares already rest at 0.48 and only 200 trade
there, you get nothing -- but the naive simulator books you a fill, and it
books it precisely in the cases where the price then moved your way, because
a level that trades lightly is one that held.

So this models:

  - **Queue position.** At placement you record how much size is already
    resting at your price. Traded volume consumes that queue before it
    consumes you.
  - **Price-through.** If the market trades clean through your level, you
    fill -- and that is the fill you did not want, because the price kept
    going. This is adverse selection, and it is the majority of what a maker
    actually experiences.
  - **Cancellation credit.** Queue ahead can never exceed the size actually
    resting at your level, so if the level thins out you move up.

The result is pessimistic relative to a naive simulator, which is the
correct bias when the output is going to be used to decide whether to risk
money.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..marketdata.store import PublicTrade, Snapshot

log = logging.getLogger(__name__)


@dataclass
class SimulatedOrder:
    order_id: str
    token_id: str
    side: str            # BUY or SELL
    price: float
    size: float
    placed_ts: float

    queue_ahead: float = 0.0
    filled_size: float = 0.0
    cancelled: bool = False

    # Populated as fills occur.
    fills: list["SimulatedFill"] = field(default_factory=list)

    @property
    def remaining(self) -> float:
        return max(0.0, self.size - self.filled_size)

    @property
    def is_done(self) -> bool:
        return self.cancelled or self.remaining <= 1e-9


@dataclass
class SimulatedFill:
    order_id: str
    token_id: str
    side: str
    price: float
    size: float
    ts: float
    reason: str          # "queue" or "price_through"

    # Mid at fill time, for markout measurement.
    mid_at_fill: float | None = None


class FillSimulator:
    """Tracks resting orders and decides what they would have filled.

    Feed it snapshots and trades in timestamp order.
    """

    def __init__(self, *, allow_price_through: bool = True):
        self.allow_price_through = allow_price_through
        self._orders: dict[str, SimulatedOrder] = {}
        self._last_snapshot: dict[str, Snapshot] = {}
        self.fills: list[SimulatedFill] = []

    # ----------------------------------------------------------- lifecycle

    def place(self, order: SimulatedOrder, snapshot: Snapshot | None = None) -> SimulatedOrder:
        """Rest an order, recording the queue it joins."""
        snap = snapshot or self._last_snapshot.get(order.token_id)
        if snap is not None:
            order.queue_ahead = snap.size_at(order.side, order.price)
        self._orders[order.order_id] = order
        return order

    def cancel(self, order_id: str) -> None:
        order = self._orders.get(order_id)
        if order is not None:
            order.cancelled = True
            del self._orders[order_id]

    def open_orders(self, token_id: str | None = None) -> list[SimulatedOrder]:
        return [
            o for o in self._orders.values()
            if not o.is_done and (token_id is None or o.token_id == token_id)
        ]

    # --------------------------------------------------------------- events

    def on_snapshot(self, snap: Snapshot) -> list[SimulatedFill]:
        """Update queue estimates and detect price-through fills."""
        self._last_snapshot[snap.token_id] = snap
        produced: list[SimulatedFill] = []

        for order in list(self._orders.values()):
            if order.is_done or order.token_id != snap.token_id:
                continue

            # Queue ahead cannot exceed what is actually resting at the level.
            # If the level thinned (cancellations), we have moved up.
            resting = snap.size_at(order.side, order.price)
            if resting < order.queue_ahead:
                order.queue_ahead = resting

            if self.allow_price_through:
                fill = self._check_price_through(order, snap)
                if fill is not None:
                    produced.append(fill)

        return produced

    def on_trade(self, trade: PublicTrade) -> list[SimulatedFill]:
        """Consume traded volume against the queue, then against our order."""
        produced: list[SimulatedFill] = []
        snap = self._last_snapshot.get(trade.token_id)
        mid = snap.mid if snap else None

        for order in list(self._orders.values()):
            if order.is_done or order.token_id != trade.token_id:
                continue
            if trade.ts < order.placed_ts:
                continue
            if not self._trade_reaches(order, trade.price):
                continue

            volume = trade.size

            # The queue ahead of us eats first.
            if order.queue_ahead > 0:
                consumed = min(volume, order.queue_ahead)
                order.queue_ahead -= consumed
                volume -= consumed

            if volume <= 1e-9:
                continue

            fill_size = min(volume, order.remaining)
            if fill_size <= 1e-9:
                continue

            fill = SimulatedFill(
                order_id=order.order_id,
                token_id=order.token_id,
                side=order.side,
                price=order.price,
                size=fill_size,
                ts=trade.ts,
                reason="queue",
                mid_at_fill=mid,
            )
            order.filled_size += fill_size
            order.fills.append(fill)
            self.fills.append(fill)
            produced.append(fill)

            if order.is_done:
                self._orders.pop(order.order_id, None)

        return produced

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _trade_reaches(order: SimulatedOrder, trade_price: float) -> bool:
        """Does a trade at this price touch our resting order?

        A resting bid is hit by sellers at or below its price; a resting
        offer is lifted by buyers at or above it.
        """
        eps = 1e-9
        if order.side.upper() == "BUY":
            return trade_price <= order.price + eps
        return trade_price >= order.price - eps

    def _check_price_through(
        self, order: SimulatedOrder, snap: Snapshot
    ) -> SimulatedFill | None:
        """Fill when the book has moved clean past our price.

        If the best offer is now at or below our bid, the market traded
        through our level -- we were filled on the way down, and the price
        kept going. This is the adverse fill, and a simulator that ignores it
        systematically flatters the strategy.
        """
        if order.side.upper() == "BUY":
            best_ask = snap.best_ask
            crossed = best_ask is not None and best_ask <= order.price - 1e-9
        else:
            best_bid = snap.best_bid
            crossed = best_bid is not None and best_bid >= order.price + 1e-9

        if not crossed:
            return None

        fill_size = order.remaining
        fill = SimulatedFill(
            order_id=order.order_id,
            token_id=order.token_id,
            side=order.side,
            price=order.price,
            size=fill_size,
            ts=snap.ts,
            reason="price_through",
            mid_at_fill=snap.mid,
        )
        order.filled_size += fill_size
        order.queue_ahead = 0.0
        order.fills.append(fill)
        self.fills.append(fill)
        self._orders.pop(order.order_id, None)
        return fill

    # --------------------------------------------------------------- stats

    def fill_rate(self) -> float:
        """Share of filled volume that came from the market running through
        us rather than from ordinary queue turnover.

        A high number means the strategy is mostly being picked off.
        """
        total = sum(f.size for f in self.fills)
        if total <= 0:
            return 0.0
        through = sum(f.size for f in self.fills if f.reason == "price_through")
        return through / total
