"""Fair-value models.

Read this before deploying anything.

A market maker's profit has two completely different sources, and conflating
them is the most common way these bots lose money:

1. **Spread capture.** Quote both sides around the book's own midpoint, earn
   the spread plus rebates. Requires no view. But you are adversely selected:
   you get filled on the side that is about to be wrong, because the person
   crossing to you usually knows something. Net of adverse selection, pure
   spread capture around the microprice is roughly a coin flip, and the
   rebate is what makes it marginally positive -- which is exactly why the
   biggest systematic accounts on the platform look like liquidity providers.

2. **Informational edge.** Your fair value is genuinely better than the
   market's. This is what separates a wallet doing $45 average trades 150,000
   times and netting millions from one doing the same thing and netting zero.

`MicropriceModel` below gives you (1) and explicitly not (2). It is a
baseline and a plumbing test. To actually make money you need to supply (2)
via `ExternalModel` -- a devigged sportsbook consensus, your own Elo, a
pricing model for the category you understand. The bot cannot invent that for
you, and any framework that implies otherwise is selling something.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, Protocol

from ..clients.clob import Book

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FairValue:
    """A probability estimate with an honest error bar.

    `uncertainty` drives quote width. If you do not know it, you should be
    quoting wider, not pretending it is zero.
    """

    price: float
    uncertainty: float
    source: str = "unknown"

    @property
    def is_usable(self) -> bool:
        return 0.0 < self.price < 1.0 and self.uncertainty >= 0.0


class FairValueModel(Protocol):
    def estimate(self, token_id: str, book: Book) -> FairValue | None: ...


class MicropriceModel:
    """Baseline: size-weighted mid, shrunk toward 0.5.

    NO informational edge. Spread capture only. Use it to verify the
    machinery works, then replace it.
    """

    def __init__(self, shrink: float = 0.0, min_uncertainty: float = 0.008):
        self.shrink = shrink
        self.min_uncertainty = min_uncertainty

    def estimate(self, token_id: str, book: Book) -> FairValue | None:
        mp = book.microprice()
        if mp is None:
            return None

        price = mp * (1 - self.shrink) + 0.5 * self.shrink

        # Wider book => less certain. Half-spread is a sane floor for error.
        spread = book.spread or 0.02
        uncertainty = max(self.min_uncertainty, spread / 2.0)

        return FairValue(price=price, uncertainty=uncertainty, source="microprice")


class ExternalModel:
    """Blend an external probability with the book.

    This is where a real edge enters the system. `probability_fn` returns your
    independent estimate for a token, or None when you have no view -- in
    which case the bot does not quote, which is the correct behaviour.

    The blend weight matters. Weighting your own model at 1.0 means ignoring
    the market entirely, which is overconfident. Weighting it low means you
    barely deviate from consensus and earn nothing. `model_weight` around
    0.6-0.7 is a reasonable start when the model is genuinely independent.
    """

    def __init__(
        self,
        probability_fn: Callable[[str], tuple[float, float] | None],
        *,
        model_weight: float = 0.65,
        disagreement_cap: float = 0.15,
    ):
        self.probability_fn = probability_fn
        self.model_weight = max(0.0, min(model_weight, 1.0))
        self.disagreement_cap = disagreement_cap

    def estimate(self, token_id: str, book: Book) -> FairValue | None:
        try:
            result = self.probability_fn(token_id)
        except Exception as exc:
            log.warning("external model raised for %s: %s", token_id[:12], exc)
            return None
        if result is None:
            return None

        model_p, model_sigma = result
        anchor = book.microprice()
        if anchor is None:
            return FairValue(model_p, max(model_sigma, 0.01), source="external")

        # A large disagreement with the market usually means the model is
        # stale or the market knows something (injury, news, settlement
        # detail). Refuse rather than bet the whole gap.
        if abs(model_p - anchor) > self.disagreement_cap:
            log.info(
                "Skipping %s: model %.3f vs book %.3f exceeds cap %.3f",
                token_id[:12], model_p, anchor, self.disagreement_cap,
            )
            return None

        w = self.model_weight
        blended = w * model_p + (1 - w) * anchor

        # Blending two partly-independent estimates shrinks error, but not as
        # much as if they were independent. Stay conservative.
        spread_term = (book.spread or 0.02) / 2.0
        uncertainty = max(0.006, math.sqrt((w * model_sigma) ** 2 + ((1 - w) * spread_term) ** 2))

        return FairValue(price=blended, uncertainty=uncertainty, source="external+book")


# ------------------------------------------------------------------- devig


def devig_multiplicative(implied: list[float]) -> list[float]:
    """Remove bookmaker vig by proportional scaling.

    The simplest devig: divide each implied probability by the overround.
    Fast and reasonable near even money, but on lopsided markets it leaves
    longshots overpriced and favourites underpriced, because real bookmaker
    margin is not applied proportionally across outcomes.

    Use for quick work; prefer devig_power() for anything you trade on.
    """
    total = sum(implied)
    if total <= 0:
        raise ValueError("implied probabilities must sum to something positive")
    return [p / total for p in implied]


def devig_power(implied: list[float], tolerance: float = 1e-9, max_iter: int = 100) -> list[float]:
    """Remove vig by solving for k in sum(p_i ^ k) = 1.

    Handles the favourite-longshot skew in bookmaker margin far better than
    proportional scaling, which matters a lot on Polymarket because the fee
    curve makes the tails the cheapest place to trade -- so tail mispricing is
    where the money is, and that is exactly where multiplicative devig is
    worst.

    Solved by bisection on k; monotonic, so this always converges.
    """
    ps = [p for p in implied if p > 0]
    if len(ps) != len(implied) or not ps:
        raise ValueError("all implied probabilities must be positive")
    if abs(sum(ps) - 1.0) < tolerance:
        return list(ps)

    lo, hi = 0.0001, 10.0

    def total(k: float) -> float:
        return sum(p**k for p in ps)

    if total(hi) > 1.0 or total(lo) < 1.0:
        return devig_multiplicative(ps)

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        t = total(mid)
        if abs(t - 1.0) < tolerance:
            break
        # sum(p^k) decreases as k increases (all p < 1).
        if t > 1.0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2.0
    out = [p**k for p in ps]
    s = sum(out)
    return [p / s for p in out]


def american_to_implied(odds: int) -> float:
    """American odds -> implied probability (still includes vig)."""
    if odds == 0:
        raise ValueError("american odds cannot be zero")
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def decimal_to_implied(odds: float) -> float:
    if odds <= 1.0:
        raise ValueError("decimal odds must exceed 1.0")
    return 1.0 / odds
