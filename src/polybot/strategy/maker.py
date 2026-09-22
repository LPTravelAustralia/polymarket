"""The systematic maker strategy.

This is the reverse-engineered core: the pattern behind the accounts that
grind out millions on hundreds of thousands of small fills rather than a
handful of huge conviction bets.

Shape of it:
  - quote both sides, passively, inside your own uncertainty band
  - size small and uniform
  - never cross the spread
  - skew quotes to bleed inventory back toward flat
  - refuse to quote when the required edge is not there

The edge per trade is tiny. It compounds through turnover, and it survives
only because a maker pays no fee while a taker pays ~1.25c/share at mid
prices.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from ..clients.clob import Book
from ..config import MakerParams
from ..economics import FeeSchedule
from .fair_value import FairValue

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Quote:
    token_id: str
    side: str          # BUY or SELL
    price: float
    size: float
    edge_per_share: float
    reason: str = ""

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(frozen=True)
class QuoteDecision:
    """What we want resting, and why we declined anything we declined."""

    quotes: list[Quote]
    skipped: list[str]


def round_to_tick(price: float, tick: float, *, direction: str) -> float:
    """Round to a valid tick.

    Direction matters and is not cosmetic: rounding a bid up or an ask down
    gives away edge on every single quote, and at these margins that is the
    whole strategy.
    """
    if tick <= 0:
        return price
    steps = price / tick
    if direction == "down":
        rounded = math.floor(steps + 1e-9) * tick
    else:
        rounded = math.ceil(steps - 1e-9) * tick
    # Tick sizes are 0.1/0.01/0.001; float noise needs cleaning up.
    return round(rounded, 6)


class MakerStrategy:
    def __init__(self, params: MakerParams | None = None):
        self.params = params or MakerParams()

    def quote(
        self,
        token_id: str,
        book: Book,
        fair: FairValue,
        schedule: FeeSchedule,
        *,
        inventory_shares: float = 0.0,
        max_inventory_shares: float = 100.0,
        tick: float | None = None,
    ) -> QuoteDecision:
        p = self.params
        skipped: list[str] = []

        if not fair.is_usable:
            return QuoteDecision([], ["fair value unusable"])
        if book.best_bid is None or book.best_ask is None:
            return QuoteDecision([], ["one-sided or empty book"])

        tick = tick or book.tick_size or 0.001

        if not (p.min_price <= fair.price <= p.max_price):
            return QuoteDecision(
                [], [f"fair {fair.price:.3f} outside quotable band "
                     f"[{p.min_price}, {p.max_price}]"]
            )

        # Thresholds may be absolute (prediction markets, where price IS a
        # probability) or fractional (anything quoted in currency). Resolve
        # to absolute once, here, so the rest of the method is unit-agnostic.
        scale = fair.price if p.relative_thresholds else 1.0
        floor_half_spread = p.base_half_spread * scale
        min_edge = p.min_edge_per_share * scale
        adverse = p.adverse_selection_per_share * scale
        skew_max = p.inventory_skew_max * scale

        # Required half-width: the wider of our configured floor and our own
        # model uncertainty. Quoting tighter than your error bar is how a
        # maker gets picked off.
        half_spread = max(floor_half_spread, fair.uncertainty * p.uncertainty_multiplier)

        # Inventory skew: long inventory pushes both quotes down, so we are
        # more likely to sell and less likely to buy more.
        utilisation = 0.0
        if max_inventory_shares > 0:
            utilisation = max(-1.0, min(1.0, inventory_shares / max_inventory_shares))
        skew = -utilisation * skew_max
        centre = fair.price + skew

        raw_bid = centre - half_spread
        raw_ask = centre + half_spread

        bid = round_to_tick(raw_bid, tick, direction="down")
        ask = round_to_tick(raw_ask, tick, direction="up")

        quotes: list[Quote] = []

        # ---- BUY side
        if utilisation >= 1.0:
            skipped.append("at long inventory limit, not bidding")
        else:
            bid = min(bid, book.best_ask - tick)  # never cross
            edge = fair.price - bid - adverse
            if bid < tick:
                skipped.append("bid rounds below one tick")
            elif edge < min_edge:
                skipped.append(
                    f"bid edge {edge / scale * 100:.3f}% < required "
                    f"{min_edge / scale * 100:.3f}%"
                )
            else:
                size = self._size_for(book, "BUY", p.order_size_shares)
                if size <= 0:
                    skipped.append("bid size below market minimum")
                else:
                    quotes.append(
                        Quote(token_id, "BUY", bid, size, edge,
                              f"fair {fair.price:.4f} skew {skew:+.4f}")
                    )

        # ---- SELL side
        if utilisation <= -1.0:
            skipped.append("at short inventory limit, not offering")
        else:
            ask = max(ask, book.best_bid + tick)  # never cross
            edge = ask - fair.price - adverse
            # The 1.0 ceiling is a probability bound and applies only when a
            # finite max_price says we are on a prediction market.
            if math.isfinite(p.max_price) and ask > 1.0 - tick:
                skipped.append("ask rounds above one tick from 1.0")
            elif edge < min_edge:
                skipped.append(
                    f"ask edge {edge / scale * 100:.3f}% < required "
                    f"{min_edge / scale * 100:.3f}%"
                )
            else:
                size = self._size_for(book, "SELL", p.order_size_shares)
                # Only sell what we actually hold. This bot does not short:
                # selling a token you do not own requires minting the complete
                # set first, which is a different strategy with different risk.
                if inventory_shares > 0:
                    size = min(size, inventory_shares)
                else:
                    size = 0.0
                    skipped.append("no inventory to sell (bot does not short)")

                if size > 0:
                    quotes.append(
                        Quote(token_id, "SELL", ask, size, edge,
                              f"fair {fair.price:.4f} skew {skew:+.4f}")
                    )

        if not quotes and not skipped:
            skipped.append("no quotable side")

        return QuoteDecision(quotes, skipped)

    def _size_for(self, book: Book, side: str, desired: float) -> float:
        """Cap size at a fraction of visible depth.

        Quoting size comparable to the whole book means you are the book, and
        your quote becomes the reference price everyone else trades against.
        """
        depth = book.depth(side)
        if depth <= 0:
            return 0.0
        capped = min(desired, depth * 0.25)
        return capped if capped >= book.min_order_size else 0.0

    def should_requote(self, existing_price: float, new_price: float) -> bool:
        """Churning orders costs nothing in fees but loses queue position,
        which on a passive strategy is most of the value."""
        threshold = self.params.requote_threshold
        if self.params.relative_thresholds and existing_price:
            threshold *= abs(existing_price)
        return abs(existing_price - new_price) >= threshold
