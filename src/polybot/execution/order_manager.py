"""Reconciles desired quotes against what is actually resting on the book.

The naive version -- cancel everything, repost everything, every loop -- is
what most hobby bots do and it is quietly expensive: you lose queue priority
on every cycle, and queue priority is most of the value of a passive
strategy. So we only replace an order when the price has moved enough to
matter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..clients.clob import ClobGateway
from ..strategy.maker import Quote
from .risk import RiskManager

log = logging.getLogger(__name__)


@dataclass
class RestingOrder:
    order_id: str
    token_id: str
    side: str
    price: float
    size: float


@dataclass
class ReconcileResult:
    posted: list[RestingOrder] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    kept: list[RestingOrder] = field(default_factory=list)
    rejected: list[tuple[Quote, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"posted={len(self.posted)} kept={len(self.kept)} "
            f"cancelled={len(self.cancelled)} rejected={len(self.rejected)}"
        )


class OrderManager:
    def __init__(
        self,
        gateway: ClobGateway,
        risk: RiskManager,
        *,
        requote_threshold: float = 0.003,
    ):
        self.gateway = gateway
        self.risk = risk
        self.requote_threshold = requote_threshold
        self._resting: dict[tuple[str, str], RestingOrder] = {}

    def resting_for(self, token_id: str, side: str) -> RestingOrder | None:
        return self._resting.get((token_id, side.upper()))

    def reconcile(self, desired: list[Quote]) -> ReconcileResult:
        """Make the book match `desired` for the tokens it mentions.

        Tokens absent from `desired` are left alone -- callers that want a
        token's quotes pulled should call cancel_token() explicitly. This
        avoids a partial market-data failure silently flattening everything.
        """
        result = ReconcileResult()
        wanted: dict[tuple[str, str], Quote] = {
            (q.token_id, q.side.upper()): q for q in desired
        }

        # Cancel resting orders for touched tokens that are no longer wanted
        # or have drifted too far.
        touched = {q.token_id for q in desired}
        for key, order in list(self._resting.items()):
            token_id, side = key
            if token_id not in touched:
                continue
            want = wanted.get(key)
            if want is None:
                self._cancel(key, result)
            elif abs(want.price - order.price) >= self.requote_threshold:
                self._cancel(key, result)
            else:
                result.kept.append(order)
                wanted.pop(key, None)  # already resting at an acceptable price

        # Post what remains.
        for key, quote in wanted.items():
            allowed, reason = self.risk.check_order(
                quote.token_id, quote.side, quote.price, quote.size
            )
            if not allowed:
                log.debug("rejected %s %s @ %.4f: %s",
                          quote.side, quote.token_id[:10], quote.price, reason)
                result.rejected.append((quote, reason))
                continue

            resp = self.gateway.post_limit(
                quote.token_id, quote.side, quote.price, quote.size, post_only=True
            )
            if resp is None:
                result.rejected.append((quote, "gateway rejected"))
                continue

            order_id = str(resp.get("orderID") or resp.get("orderId") or resp.get("id") or "")
            if not order_id and resp.get("dry_run"):
                order_id = f"dry-{quote.token_id[:8]}-{quote.side}"

            order = RestingOrder(order_id, quote.token_id, quote.side, quote.price, quote.size)
            self._resting[key] = order
            self.risk.record_order_sent()
            result.posted.append(order)

        return result

    def cancel_token(self, token_id: str) -> list[str]:
        cancelled: list[str] = []
        dummy = ReconcileResult()
        for key in list(self._resting):
            if key[0] == token_id:
                self._cancel(key, dummy)
        cancelled.extend(dummy.cancelled)
        return cancelled

    def cancel_all(self) -> None:
        if self.gateway.cancel_all():
            for _ in self._resting:
                self.risk.record_order_closed()
            self._resting.clear()
            log.info("All orders cancelled")

    def on_fill(self, token_id: str, side: str, price: float, size: float,
                fee: float = 0.0) -> float:
        """Record a fill and retire the resting order it came from."""
        key = (token_id, side.upper())
        order = self._resting.get(key)
        if order is not None:
            if size >= order.size - 1e-9:
                del self._resting[key]
                self.risk.record_order_closed()
            else:
                order.size -= size
        return self.risk.record_fill(token_id, side, price, size, fee)

    def _cancel(self, key: tuple[str, str], result: ReconcileResult) -> None:
        order = self._resting.get(key)
        if order is None:
            return
        if self.gateway.cancel(order.order_id):
            result.cancelled.append(order.order_id)
            self.risk.record_order_closed()
            del self._resting[key]
