"""CLOB wrapper: order books, quoting, cancelling.

Wraps the official py-clob-client so the strategies never touch it directly,
and so dry-run/paper modes can short-circuit order submission in exactly one
place rather than being sprinkled with `if mode == LIVE` checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import Mode, Settings
from ..economics import FeeBook, FeeSchedule

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Level:
    price: float
    size: float


@dataclass
class Book:
    """A normalised order book snapshot.

    py-clob-client returns bids/asks as strings in unspecified order, so we
    parse and sort once here rather than everywhere downstream.
    """

    token_id: str
    bids: list[Level]   # descending price
    asks: list[Level]   # ascending price
    tick_size: float = 0.001
    min_order_size: float = 5.0
    neg_risk: bool = False

    @classmethod
    def from_summary(cls, summary: Any, token_id: str) -> "Book":
        def levels(raw: Any) -> list[Level]:
            out = []
            for lvl in raw or []:
                try:
                    price = float(getattr(lvl, "price", None) or lvl["price"])
                    size = float(getattr(lvl, "size", None) or lvl["size"])
                except (TypeError, ValueError, KeyError):
                    continue
                if size > 0:
                    out.append(Level(price, size))
            return out

        bids = sorted(levels(getattr(summary, "bids", None)), key=lambda l: -l.price)
        asks = sorted(levels(getattr(summary, "asks", None)), key=lambda l: l.price)

        def _f(v: Any, d: float) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return d

        return cls(
            token_id=token_id,
            bids=bids,
            asks=asks,
            tick_size=_f(getattr(summary, "tick_size", None), 0.001),
            min_order_size=_f(getattr(summary, "min_order_size", None), 5.0),
            neg_risk=bool(getattr(summary, "neg_risk", False)),
        )

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def depth(self, side: str) -> float:
        levels = self.bids if side.upper() == "BUY" else self.asks
        return sum(l.size for l in levels)

    def vwap_for_size(self, side: str, shares: float) -> float | None:
        """Average price to fill `shares` by crossing.

        Returns None when the book cannot fill the whole size -- callers must
        treat that as "do not trade", not as "fill what you can".
        """
        levels = self.asks if side.upper() == "BUY" else self.bids
        remaining, cost = shares, 0.0
        for lvl in levels:
            take = min(remaining, lvl.size)
            cost += take * lvl.price
            remaining -= take
            if remaining <= 1e-9:
                return cost / shares
        return None

    def microprice(self) -> float | None:
        """Size-weighted mid: leans toward the side with less size resting.

        A better short-horizon fair-value anchor than the plain mid, because
        it reflects where the book is likely to move next.
        """
        if not self.bids or not self.asks:
            return None
        bb, ba = self.bids[0], self.asks[0]
        total = bb.size + ba.size
        if total <= 0:
            return self.mid
        return (bb.price * ba.size + ba.price * bb.size) / total


class ClobGateway:
    """All CLOB access goes through here."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fees = FeeBook()
        self._client: Any = None
        self._dry = settings.mode is not Mode.LIVE

    # ----------------------------------------------------------- lifecycle

    def connect(self) -> None:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds

        s = self.settings
        if s.private_key:
            creds = None
            if s.api_key and s.api_secret and s.api_passphrase:
                creds = ApiCreds(s.api_key, s.api_secret, s.api_passphrase)

            self._client = ClobClient(
                s.clob_host,
                chain_id=s.chain_id,
                key=s.private_key,
                creds=creds,
                signature_type=s.signature_type,
                funder=s.funder_address or None,
            )
            if creds is None:
                log.info("Deriving L2 API credentials from private key")
                self._client.set_api_creds(self._client.create_or_derive_api_creds())
        else:
            # Read-only: enough for books, fees and dry-run quoting.
            self._client = ClobClient(s.clob_host, chain_id=s.chain_id)
            log.warning("No private key -- read-only mode, orders will not be sent")

        log.info("CLOB connected (mode=%s)", s.mode.value)

    @property
    def client(self) -> Any:
        if self._client is None:
            self.connect()
        return self._client

    # -------------------------------------------------------- market data

    def book(self, token_id: str) -> Book | None:
        try:
            summary = self.client.get_order_book(token_id)
        except Exception as exc:
            log.warning("get_order_book(%s) failed: %s", token_id, exc)
            return None
        if summary is None:
            return None
        return Book.from_summary(summary, token_id)

    def books(self, token_ids: list[str]) -> dict[str, Book]:
        """Batch fetch. Materially faster than looping when quoting many
        markets, and the CLOB prefers it."""
        from py_clob_client.clob_types import BookParams

        if not token_ids:
            return {}
        try:
            summaries = self.client.get_order_books([BookParams(token_id=t) for t in token_ids])
        except Exception as exc:
            log.warning("batch get_order_books failed (%s), falling back", exc)
            return {t: b for t in token_ids if (b := self.book(t)) is not None}

        out: dict[str, Book] = {}
        for summary in summaries or []:
            tid = str(getattr(summary, "asset_id", "") or "")
            if tid:
                out[tid] = Book.from_summary(summary, tid)
        return out

    def fee_schedule(self, token_id: str, category: str | None = None) -> FeeSchedule:
        return self.fees.load_from_clob(self.client, token_id, category)

    def tick_size(self, token_id: str) -> float:
        try:
            return float(self.client.get_tick_size(token_id))
        except Exception:
            return 0.001

    # -------------------------------------------------------------- orders

    def post_limit(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        *,
        post_only: bool = True,
    ) -> dict[str, Any] | None:
        """Place a resting limit order.

        post_only defaults to True and should stay that way. A "maker" order
        that crosses the book is a taker order, pays the taker fee, and
        silently converts a positive-edge quote into a negative-edge trade.
        """
        from py_clob_client.clob_types import OrderArgs, OrderType

        if self._dry:
            log.info(
                "[%s] would post %s %.1f @ %.4f on %s",
                self.settings.mode.value, side, size, price, token_id[:12],
            )
            return {"dry_run": True, "side": side, "price": price, "size": size}

        try:
            order = self.client.create_order(
                OrderArgs(token_id=token_id, price=price, size=size, side=side.upper())
            )
            return self.client.post_order(order, OrderType.GTC, post_only=post_only)
        except Exception as exc:
            log.error("post_limit failed (%s %.1f @ %.4f): %s", side, size, price, exc)
            return None

    def cancel(self, order_id: str) -> bool:
        if self._dry:
            log.info("[%s] would cancel %s", self.settings.mode.value, order_id)
            return True
        try:
            self.client.cancel(order_id)
            return True
        except Exception as exc:
            log.error("cancel(%s) failed: %s", order_id, exc)
            return False

    def cancel_all(self) -> bool:
        if self._dry:
            log.info("[%s] would cancel all orders", self.settings.mode.value)
            return True
        try:
            self.client.cancel_all()
            return True
        except Exception as exc:
            log.error("cancel_all failed: %s", exc)
            return False

    def open_orders(self) -> list[dict[str, Any]]:
        try:
            resp = self.client.get_orders()
            return resp if isinstance(resp, list) else resp.get("data", [])
        except Exception as exc:
            log.warning("get_orders failed: %s", exc)
            return []
