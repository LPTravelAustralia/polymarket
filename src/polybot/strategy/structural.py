"""Structural arbitrage: complete-set mispricings.

Two forms:

  **Complement (binary).** YES and NO together always pay exactly $1. If you
  can buy both for less than $1 after fees, that is riskless.

  **Negative-risk basket (multi-outcome).** Exactly one outcome in the event
  resolves YES. If all outcomes together cost less than $1, same trade.

  **Reverse.** If all outcomes together *bid* more than $1, mint a complete
  set for $1 via SPLIT and sell the legs.

Set expectations honestly: published measurements put the median arbitrage
window at roughly 2.7 seconds, down from ~12 seconds in 2024, with the large
majority of the profit going to sub-100ms infrastructure. A Python bot
polling REST will mostly see opportunities that are already gone, or that are
stale quotes nobody can actually fill.

So this module is deliberately opportunistic, not the primary strategy. It
exists because the checks are cheap and occasionally a genuinely wide
mispricing appears in an illiquid multi-outcome market that the fast bots are
not watching. It is gated hard on post-fee profit and assumes slippage on
every leg, because a multi-leg trade where one leg misses is not arbitrage --
it is an accidental naked position.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..clients.clob import Book
from ..config import ArbParams
from ..economics import FeeSchedule, taker_fee_per_share

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArbLeg:
    token_id: str
    side: str
    price: float
    size: float


@dataclass(frozen=True)
class ArbOpportunity:
    kind: str                  # "complement_buy", "basket_buy", "basket_sell"
    legs: list[ArbLeg]
    size_shares: float
    gross_profit_per_share: float
    fee_per_share: float
    slippage_per_share: float
    net_profit_per_share: float
    notes: list[str] = field(default_factory=list)

    @property
    def net_profit_total(self) -> float:
        return self.net_profit_per_share * self.size_shares

    @property
    def notional(self) -> float:
        return sum(l.price * l.size for l in self.legs)


def _fillable_size(books: list[Book], side: str, cap_shares: float) -> float:
    """Largest size fillable on every leg simultaneously at the top level.

    Uses top-of-book only. Walking deeper levels raises the average price and
    usually destroys the edge, so if the top level is too thin the trade is
    not there.
    """
    sizes = []
    for b in books:
        levels = b.asks if side == "BUY" else b.bids
        if not levels:
            return 0.0
        sizes.append(levels[0].size)
    return min([cap_shares, *sizes])


def find_complement_arb(
    yes_book: Book,
    no_book: Book,
    yes_fees: FeeSchedule,
    no_fees: FeeSchedule,
    params: ArbParams | None = None,
) -> ArbOpportunity | None:
    """Buy YES + NO for under $1."""
    p = params or ArbParams()

    ya, na = yes_book.best_ask, no_book.best_ask
    if ya is None or na is None:
        return None

    gross = 1.0 - (ya + na)
    if gross <= 0:
        return None

    fee = taker_fee_per_share(ya, yes_fees.taker_rate) + taker_fee_per_share(na, no_fees.taker_rate)
    slip = 2 * p.slippage_per_leg
    net = gross - fee - slip
    if net < p.min_profit_per_share:
        return None

    max_by_notional = p.max_notional_usd / max(ya + na, 1e-6)
    size = _fillable_size([yes_book, no_book], "BUY", max_by_notional)
    if size < max(yes_book.min_order_size, no_book.min_order_size):
        return None

    return ArbOpportunity(
        kind="complement_buy",
        legs=[
            ArbLeg(yes_book.token_id, "BUY", ya, size),
            ArbLeg(no_book.token_id, "BUY", na, size),
        ],
        size_shares=size,
        gross_profit_per_share=gross,
        fee_per_share=fee,
        slippage_per_share=slip,
        net_profit_per_share=net,
        notes=[f"YES {ya:.4f} + NO {na:.4f} = {ya + na:.4f}"],
    )


def find_basket_arb(
    books: list[Book],
    schedules: list[FeeSchedule],
    params: ArbParams | None = None,
) -> ArbOpportunity | None:
    """Neg-risk basket: buy every outcome for under $1, or sell every outcome
    for over $1.

    Only valid on markets flagged neg_risk, where exactly one outcome can
    resolve YES. Applying this to a set of independent markets is not
    arbitrage -- it is a guess that they are mutually exclusive.
    """
    p = params or ArbParams()
    if len(books) < 2 or len(books) != len(schedules):
        return None
    if not all(b.neg_risk for b in books):
        return None

    n = len(books)

    # ---- Buy side
    asks = [b.best_ask for b in books]
    if all(a is not None for a in asks):
        total = sum(asks)  # type: ignore[arg-type]
        gross = 1.0 - total
        if gross > 0:
            fee = sum(
                taker_fee_per_share(a, s.taker_rate)  # type: ignore[arg-type]
                for a, s in zip(asks, schedules)
            )
            slip = n * p.slippage_per_leg
            net = gross - fee - slip
            if net >= p.min_profit_per_share:
                size = _fillable_size(books, "BUY", p.max_notional_usd / max(total, 1e-6))
                if size >= max(b.min_order_size for b in books):
                    return ArbOpportunity(
                        kind="basket_buy",
                        legs=[
                            ArbLeg(b.token_id, "BUY", a, size)  # type: ignore[arg-type]
                            for b, a in zip(books, asks)
                        ],
                        size_shares=size,
                        gross_profit_per_share=gross,
                        fee_per_share=fee,
                        slippage_per_share=slip,
                        net_profit_per_share=net,
                        notes=[f"{n} outcomes sum to {total:.4f}"],
                    )

    # ---- Sell side: mint a complete set for $1, sell the legs.
    bids = [b.best_bid for b in books]
    if all(bd is not None for bd in bids):
        total = sum(bids)  # type: ignore[arg-type]
        gross = total - 1.0
        if gross > 0:
            fee = sum(
                taker_fee_per_share(bd, s.taker_rate)  # type: ignore[arg-type]
                for bd, s in zip(bids, schedules)
            )
            slip = n * p.slippage_per_leg
            net = gross - fee - slip
            if net >= p.min_profit_per_share:
                size = _fillable_size(books, "SELL", p.max_notional_usd)
                if size >= max(b.min_order_size for b in books):
                    return ArbOpportunity(
                        kind="basket_sell",
                        legs=[
                            ArbLeg(b.token_id, "SELL", bd, size)  # type: ignore[arg-type]
                            for b, bd in zip(books, bids)
                        ],
                        size_shares=size,
                        gross_profit_per_share=gross,
                        fee_per_share=fee,
                        slippage_per_share=slip,
                        net_profit_per_share=net,
                        notes=[
                            f"{n} outcomes bid {total:.4f}",
                            "Requires SPLIT to mint the complete set first "
                            "(gas + latency, not modelled here)",
                        ],
                    )

    return None
