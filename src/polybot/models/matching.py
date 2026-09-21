"""Match a Polymarket market to a sportsbook event.

The most dangerous code in the model layer. Every other component fails
gracefully -- a bad fair value quotes badly and loses a little. A bad *match*
prices one game with another game's probability and can be confidently,
catastrophically wrong while every log line looks healthy.

So the rules here are deliberately paranoid:

  - Both outcomes must map to distinct teams. A market where both sides
    matched the same team is a bug, not a near miss.
  - The match must beat the runner-up by a margin. Two events matching
    equally well means ambiguity (doubleheaders, tournaments where the same
    teams meet twice), and ambiguity is refused rather than resolved by
    coin flip.
  - Event time must be close to the market's resolution time.
  - Below the confidence floor, return nothing. No quoting is always
    better than quoting the wrong game.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .odds_feed import OddsEvent

log = logging.getLogger(__name__)

# Words that carry no identifying information for a team.
STOPWORDS = {
    "the", "at", "vs", "v", "versus", "fc", "afc", "cf", "sc",
    "will", "win", "beat", "defeat", "game", "match", "to",
}

_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def normalize(name: str) -> str:
    text = _PUNCT.sub(" ", str(name).lower())
    return _WS.sub(" ", text).strip()


def token_set(name: str) -> frozenset[str]:
    return frozenset(t for t in normalize(name).split() if t and t not in STOPWORDS)


def similarity(a: str, b: str) -> float:
    """Similarity in [0, 1], tolerant of one name being a subset of the other.

    Polymarket says "Lakers" where a sportsbook says "Los Angeles Lakers",
    so containment matters more than Jaccard here: plain Jaccard would score
    that pair 0.33 and reject a perfect match.
    """
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0

    inter = len(ta & tb)
    if inter == 0:
        return 0.0

    jaccard = inter / len(ta | tb)
    containment = inter / min(len(ta), len(tb))
    # Containment is the stronger signal but shouldn't fully mask a weak
    # overlap, so blend with a bias toward containment.
    return max(jaccard, 0.5 + 0.5 * containment if containment >= 1.0 else containment * 0.9)


@dataclass
class MatchResult:
    event: OddsEvent
    outcome_to_team: dict[str, str]
    confidence: float
    runner_up_confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def margin(self) -> float:
        return self.confidence - self.runner_up_confidence

    def probability_for(self, outcome: str) -> float | None:
        team = self.outcome_to_team.get(outcome)
        if team is None:
            return None
        return self.event.probability(team)


def _score_event(outcomes: list[str], event: OddsEvent) -> tuple[float, dict[str, str]]:
    """Best assignment of market outcomes to event teams.

    Only two-outcome markets are handled; a draw or multi-way market needs
    its own treatment and is rejected by the caller.
    """
    if len(outcomes) != 2:
        return 0.0, {}

    teams = event.teams
    direct = (
        similarity(outcomes[0], teams[0]) + similarity(outcomes[1], teams[1])
    ) / 2.0
    swapped = (
        similarity(outcomes[0], teams[1]) + similarity(outcomes[1], teams[0])
    ) / 2.0

    if direct >= swapped:
        return direct, {outcomes[0]: teams[0], outcomes[1]: teams[1]}
    return swapped, {outcomes[0]: teams[1], outcomes[1]: teams[0]}


def match_market(
    outcomes: list[str],
    events: list[OddsEvent],
    *,
    market_end_ts: float | None = None,
    min_confidence: float = 0.80,
    min_margin: float = 0.15,
    max_time_delta_hours: float = 48.0,
) -> MatchResult | None:
    """Find the event this market refers to, or None if unsure.

    Returning None is a success, not a failure, whenever the evidence is
    thin: the caller simply does not quote that market.
    """
    if len(outcomes) != 2:
        log.debug("Refusing match: %d outcomes, only two-way supported", len(outcomes))
        return None

    scored: list[tuple[float, dict[str, str], OddsEvent]] = []
    for event in events:
        if not event.is_usable:
            continue
        if market_end_ts and event.commence_time:
            delta_hours = abs(event.commence_time - market_end_ts) / 3600.0
            if delta_hours > max_time_delta_hours:
                continue
        score, mapping = _score_event(outcomes, event)
        if score > 0:
            scored.append((score, mapping, event))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_map, best_event = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0

    reasons = []
    if best_score < min_confidence:
        log.debug("Refusing match: confidence %.2f < %.2f", best_score, min_confidence)
        return None

    # Distinct teams: mapping both outcomes to one team is a bug.
    if len(set(best_map.values())) != 2:
        log.warning("Refusing match: both outcomes mapped to the same team (%s)", best_map)
        return None

    if len(scored) > 1 and (best_score - runner_up) < min_margin:
        log.warning(
            "Refusing ambiguous match: %.2f vs runner-up %.2f for outcomes %s. "
            "Likely a repeated fixture -- refusing rather than guessing.",
            best_score, runner_up, outcomes,
        )
        return None

    reasons.append(f"matched {outcomes} to {best_event.teams} at {best_score:.2f}")
    if market_end_ts and best_event.commence_time:
        reasons.append(
            f"event starts {abs(best_event.commence_time - market_end_ts) / 3600:.1f}h "
            "from market end"
        )
    reasons.append(f"{best_event.book_count} books, spread {best_event.spread:.3f}")

    return MatchResult(
        event=best_event,
        outcome_to_team=best_map,
        confidence=best_score,
        runner_up_confidence=runner_up,
        reasons=reasons,
    )
