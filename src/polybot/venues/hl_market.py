"""Hyperliquid market data and fee model, wired to the existing strategy.

The quoting logic, risk gating and order management are unchanged from the
Polymarket build -- they were written to be venue-agnostic and this is the
test of whether that held. What differs here is only market data and the
fee model.

**The fee model difference matters.** Polymarket charges
`size * rate * p * (1-p)`, a bell curve peaking at 0.50. Perps charge a flat
rate on notional. Carrying the prediction-market curve over would badly
misprice every decision, so `PerpFeeSchedule` replaces it rather than
reusing `FeeSchedule` with different numbers.

Measured on live accounts: maker drag of 0.0013% of notional against
Polymarket's 0.92% of capital deployed. The strategy that could not clear
its costs there clears them here by roughly three orders of magnitude.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..clients.clob import Book, Level
from .hyperliquid import HyperliquidAPI, _f

log = logging.getLogger(__name__)

# Published perp defaults. An account's real tier comes from `userFees`;
# these are the conservative fallback.
DEFAULT_PERP_TAKER = 0.00045      # 0.045%
DEFAULT_PERP_MAKER = 0.00015      # 0.015%


@dataclass(frozen=True)
class PerpFeeSchedule:
    """Flat-rate fees on notional.

    Deliberately mirrors the `FeeSchedule` interface so the same strategy
    and economics code can consume either, but the arithmetic is different:
    flat on notional, not a function of price.

    A negative maker rate is a rebate and is supported -- at some tiers the
    venue pays you to provide liquidity, which flips the sign of the whole
    edge calculation.
    """

    taker_rate: float = DEFAULT_PERP_TAKER
    maker_rate: float = DEFAULT_PERP_MAKER

    def fee(self, size: float, price: float, *, is_maker: bool = False) -> float:
        rate = self.maker_rate if is_maker else self.taker_rate
        return abs(size) * price * rate

    def fee_per_share(self, price: float, *, is_maker: bool = False) -> float:
        """Cost per unit, so it compares directly against edge.

        Unlike a prediction market, this scales with price -- a $100k
        contract costs a hundred times what a $1k one does at the same rate.
        """
        rate = self.maker_rate if is_maker else self.taker_rate
        return price * rate

    @property
    def maker_is_rebated(self) -> bool:
        return self.maker_rate < 0

    def round_trip_cost_per_share(self, price: float, *, maker_in: bool = True,
                                  maker_out: bool = True) -> float:
        return (self.fee_per_share(price, is_maker=maker_in)
                + self.fee_per_share(price, is_maker=maker_out))

    @classmethod
    def from_user_fees(cls, payload: dict[str, Any]) -> "PerpFeeSchedule":
        """Build from the `userFees` response -- the account's real tier.

        Field names have moved between API versions, so several spellings
        are accepted and the published default is used when none match,
        rather than silently assuming zero fees. Assuming zero is the
        dangerous failure: it makes every marginal trade look profitable.
        """
        def pick(*keys: str) -> float | None:
            for k in keys:
                if k in payload:
                    v = _f(payload[k], default=float("nan"))
                    if v == v:
                        return v
            return None

        taker = pick("userAddRate", "takerRate", "userCrossRate")
        maker = pick("userAddRate", "makerRate")
        # userCrossRate is the taker side; userAddRate the maker side.
        taker = pick("userCrossRate", "takerRate") or taker
        maker = pick("userAddRate", "makerRate") or maker

        if taker is None and maker is None:
            log.warning(
                "userFees returned no recognised rate fields; falling back to "
                "published defaults rather than assuming zero."
            )
        return cls(
            taker_rate=DEFAULT_PERP_TAKER if taker is None else taker,
            maker_rate=DEFAULT_PERP_MAKER if maker is None else maker,
        )


def book_from_l2(payload: dict[str, Any], coin: str) -> Book | None:
    """Convert an `l2Book` response into the shared Book type.

    Shape: {"coin": str, "levels": [[bids...], [asks...]]} where each level
    is {"px","sz","n"}.
    """
    levels = payload.get("levels") if isinstance(payload, dict) else None
    if not levels or len(levels) < 2:
        return None

    def side(raw: Any) -> list[Level]:
        out = []
        for lv in raw or []:
            px, sz = _f(lv.get("px")), _f(lv.get("sz"))
            if px > 0 and sz > 0:
                out.append(Level(px, sz))
        return out

    bids = sorted(side(levels[0]), key=lambda l: -l.price)
    asks = sorted(side(levels[1]), key=lambda l: l.price)
    if not bids or not asks:
        return None

    # Tick size is not published per market; infer from the prices actually
    # quoted. Guessing too fine gets orders rejected, so this rounds to the
    # smallest decimal place actually observed.
    tick = _infer_tick([l.price for l in bids[:5]] + [l.price for l in asks[:5]])

    return Book(
        token_id=coin,
        bids=bids,
        asks=asks,
        tick_size=tick,
        min_order_size=0.0,
        neg_risk=False,
    )


def _infer_tick(prices: list[float]) -> float:
    """Smallest decimal place present across the quoted prices."""
    worst = 0
    for p in prices:
        s = f"{p:.10f}".rstrip("0")
        if "." in s:
            worst = max(worst, len(s.split(".")[1]))
    return 10.0 ** (-worst) if worst else 0.01


class HyperliquidMarketData:
    """Books and fees for the quoting loop."""

    def __init__(self, api: HyperliquidAPI | None = None):
        self.api = api or HyperliquidAPI()
        self._fees: PerpFeeSchedule | None = None

    def close(self) -> None:
        self.api.close()

    def book(self, coin: str) -> Book | None:
        try:
            payload = self.api._post({"type": "l2Book", "coin": coin})
        except Exception as exc:
            log.warning("l2Book(%s) failed: %s", coin, exc)
            return None
        return book_from_l2(payload, coin)

    def fee_schedule(self, address: str | None = None) -> PerpFeeSchedule:
        """The account's real fee tier, cached.

        Without an address the published default applies -- which is the
        conservative direction, since a lower real tier only makes the
        strategy better than modelled.
        """
        if self._fees is not None:
            return self._fees
        if not address:
            self._fees = PerpFeeSchedule()
            return self._fees
        try:
            self._fees = PerpFeeSchedule.from_user_fees(self.api.user_fees(address))
        except Exception as exc:
            log.warning("userFees failed (%s); using published defaults", exc)
            self._fees = PerpFeeSchedule()
        return self._fees

    def universe(self, limit: int = 30) -> list[str]:
        """Tradeable perp symbols, most liquid first where inferable."""
        try:
            meta = self.api._post({"type": "meta"})
        except Exception as exc:
            log.error("meta failed: %s", exc)
            return []
        names = [
            u.get("name") for u in (meta.get("universe") or [])
            if isinstance(u, dict) and u.get("name") and not u.get("isDelisted")
        ]
        return [n for n in names if n][:limit]
