"""Sports fair value: devigged book consensus, matched to Polymarket markets.

This is the piece that turns the bot from a spread-capture machine into
something with an actual edge -- the swisstony pattern, where you price a
sports market slightly better than the Polymarket consensus and collect the
difference across thousands of small fills.

Plugs into `ExternalModel`:

    from polybot.models.sports import SportsFairValue
    from polybot.strategy.fair_value import ExternalModel

    sports = SportsFairValue(TheOddsAPI(), sport_keys=["basketball_nba"])
    sports.register(markets)
    model = ExternalModel(sports.probability_fn)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..clients.gamma import MarketRef
from .matching import MatchResult, match_market
from .odds_feed import OddsProvider

log = logging.getLogger(__name__)

# Polymarket sport categories -> the-odds-api sport keys.
SPORT_KEYS = {
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "epl": "soccer_epl",
    "ncaab": "basketball_ncaab",
    "ncaaf": "americanfootball_ncaaf",
}


@dataclass
class BoundMarket:
    """A Polymarket market successfully bound to a sportsbook event."""

    market: MarketRef
    match: MatchResult
    token_to_outcome: dict[str, str] = field(default_factory=dict)
    bound_at: float = 0.0

    def outcome_for(self, token_id: str) -> str | None:
        return self.token_to_outcome.get(token_id)


class SportsFairValue:
    def __init__(
        self,
        provider: OddsProvider,
        *,
        sport_keys: list[str] | None = None,
        refresh_seconds: float = 120.0,
        min_confidence: float = 0.80,
        stop_quoting_before_start_seconds: float = 900.0,
    ):
        self.provider = provider
        self.sport_keys = sport_keys or list(SPORT_KEYS.values())
        self.refresh_seconds = refresh_seconds
        self.min_confidence = min_confidence
        # Pre-game odds are worthless once the ball is in the air. Without a
        # live feed, stop quoting well before tip-off rather than discovering
        # this the expensive way.
        self.stop_before_start = stop_quoting_before_start_seconds

        self._bound: dict[str, BoundMarket] = {}     # token_id -> bound market
        self._last_refresh = 0.0
        self.unmatched: list[str] = []

    # ------------------------------------------------------------- binding

    def register(self, markets: list[MarketRef]) -> int:
        """Bind markets to sportsbook events. Returns how many bound."""
        events = []
        for key in self.sport_keys:
            try:
                events.extend(self.provider.events(key))
            except Exception as exc:
                log.error("Could not fetch %s: %s", key, exc)

        if not events:
            log.warning("No odds events available; nothing can be bound")
            return 0

        self._bound.clear()
        self.unmatched.clear()
        bound = 0

        for market in markets:
            if len(market.token_ids) != 2 or len(market.outcomes) != 2:
                self.unmatched.append(f"{market.question[:50]} (not two-way)")
                continue

            result = match_market(
                market.outcomes,
                events,
                market_end_ts=_parse_end(market.end_date),
                min_confidence=self.min_confidence,
            )
            if result is None:
                self.unmatched.append(market.question[:60])
                continue

            token_to_outcome = dict(zip(market.token_ids, market.outcomes))
            bm = BoundMarket(market, result, token_to_outcome, time.time())
            for token_id in market.token_ids:
                self._bound[token_id] = bm
            bound += 1
            log.info("Bound '%s' -> %s (%.2f)",
                     market.question[:45], result.event.teams, result.confidence)

        log.info("Bound %d/%d markets; %d unmatched",
                 bound, len(markets), len(self.unmatched))
        self._last_refresh = time.monotonic()
        return bound

    def refresh_if_stale(self, markets: list[MarketRef]) -> None:
        if time.monotonic() - self._last_refresh > self.refresh_seconds:
            self.register(markets)

    # --------------------------------------------------------------- model

    def probability_fn(self, token_id: str) -> tuple[float, float] | None:
        """Signature expected by `ExternalModel`.

        Returns (probability, uncertainty), or None to decline to quote --
        which is the correct answer far more often than not.
        """
        bound = self._bound.get(token_id)
        if bound is None:
            return None

        outcome = bound.outcome_for(token_id)
        if outcome is None:
            return None

        # Refuse once the event is imminent or underway.
        commence = bound.match.event.commence_time
        if commence:
            remaining = commence - time.time()
            if remaining < self.stop_before_start:
                log.debug(
                    "Declining %s: event starts in %.0fs (cutoff %.0fs)",
                    token_id[:12], remaining, self.stop_before_start,
                )
                return None

        prob = bound.match.probability_for(outcome)
        if prob is None or not 0.0 < prob < 1.0:
            return None

        return prob, bound.match.event.uncertainty()

    # --------------------------------------------------------------- report

    def coverage_report(self) -> str:
        markets = {id(b) for b in self._bound.values()}
        lines = [
            f"Bound {len(markets)} markets covering {len(self._bound)} tokens",
        ]
        if self.unmatched:
            lines.append(f"Unmatched ({len(self.unmatched)}):")
            lines += [f"  - {u}" for u in self.unmatched[:15]]
            if len(self.unmatched) > 15:
                lines.append(f"  ... and {len(self.unmatched) - 15} more")
        return "\n".join(lines)


def _parse_end(end_date: str | None) -> float | None:
    if not end_date:
        return None
    try:
        dt = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None
