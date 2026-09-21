"""Sportsbook odds as an independent probability source.

This is where a real edge comes from. The Polymarket price is one opinion;
a devigged consensus of sharp sportsbooks is another, built by people who
price these events for a living and settle billions on the results. Where
they disagree materially, one of them is wrong, and on liquid sports the
prior should usually favour the books.

**Order of operations matters and is commonly got wrong.** You must devig
each bookmaker's own prices first, then average the fair probabilities
across books. Averaging raw implied probabilities and devigging the average
mixes together books with different margins and produces a number that is
not any book's opinion. The difference is small on a two-way market with
similar margins and large as soon as one book is fatter than the others.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from ..clients.http import JsonClient
from ..strategy.fair_value import devig_power

log = logging.getLogger(__name__)

THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Sharper books get more weight. Pinnacle is the reference sharp book: low
# margin, high limits, and it moves first. Retail books largely follow.
DEFAULT_BOOK_WEIGHTS: dict[str, float] = {
    "pinnacle": 3.0,
    "betfair_ex_uk": 2.0,
    "betfair_ex_eu": 2.0,
    "circasports": 2.0,
    "lowvig": 1.5,
    "betonlineag": 1.5,
}
DEFAULT_BOOK_WEIGHT = 1.0


@dataclass
class OddsEvent:
    """One sporting event with a devigged consensus probability per team."""

    event_id: str
    sport_key: str
    commence_time: float          # epoch seconds
    home_team: str
    away_team: str
    consensus: dict[str, float] = field(default_factory=dict)
    book_count: int = 0
    spread: float = 0.0           # disagreement across books, for uncertainty

    @property
    def teams(self) -> list[str]:
        return [self.home_team, self.away_team]

    @property
    def is_usable(self) -> bool:
        """At least two books, and probabilities that actually sum to one."""
        if self.book_count < 2 or len(self.consensus) < 2:
            return False
        return abs(sum(self.consensus.values()) - 1.0) < 0.02

    def probability(self, team: str) -> float | None:
        return self.consensus.get(team)

    def uncertainty(self) -> float:
        """Model error bar, driven by how much the books disagree.

        Books agreeing tightly is evidence the price is right; books spread
        out means genuine uncertainty and the quote should widen.
        """
        base = 0.010
        return max(base, self.spread)

    def to_json(self, ts: float | None = None) -> str:
        """Serialise for recording. Historical odds cannot be bought back
        later, so capture them alongside the books from day one."""
        import json as _json

        return _json.dumps({
            "ts": round(ts if ts is not None else time.time(), 3),
            "id": self.event_id,
            "sk": self.sport_key,
            "ct": self.commence_time,
            "h": self.home_team,
            "a": self.away_team,
            "c": {k: round(v, 5) for k, v in self.consensus.items()},
            "n": self.book_count,
            "sp": round(self.spread, 5),
        }, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> tuple[float, "OddsEvent"]:
        """Returns (recorded_at, event)."""
        import json as _json

        d = _json.loads(line)
        return d.get("ts", 0.0), cls(
            event_id=d["id"],
            sport_key=d.get("sk", ""),
            commence_time=d.get("ct", 0.0),
            home_team=d.get("h", ""),
            away_team=d.get("a", ""),
            consensus=dict(d.get("c", {})),
            book_count=d.get("n", 0),
            spread=d.get("sp", 0.0),
        )


class OddsProvider(Protocol):
    def events(self, sport_key: str) -> list[OddsEvent]: ...


def build_consensus(
    bookmakers: list[dict[str, Any]],
    *,
    weights: dict[str, float] | None = None,
) -> tuple[dict[str, float], int, float]:
    """Devig each book, then take a weighted average.

    Returns (consensus, book_count, spread).
    """
    weights = weights or DEFAULT_BOOK_WEIGHTS
    per_team: dict[str, list[tuple[float, float]]] = {}   # team -> [(prob, weight)]
    used = 0

    for bm in bookmakers:
        key = str(bm.get("key") or "").lower()
        h2h = next(
            (m for m in bm.get("markets", []) or [] if m.get("key") == "h2h"), None
        )
        if not h2h:
            continue

        outcomes = h2h.get("outcomes") or []
        names, implied = [], []
        for o in outcomes:
            try:
                price = float(o["price"])
                name = str(o["name"])
            except (KeyError, TypeError, ValueError):
                continue
            if price <= 1.0:
                continue
            names.append(name)
            implied.append(1.0 / price)

        # Only two-way markets here. A three-way (draw) market needs the draw
        # handled explicitly, and silently dropping it would corrupt the devig.
        if len(names) != 2 or not implied:
            continue

        try:
            fair = devig_power(implied)
        except ValueError:
            continue

        w = weights.get(key, DEFAULT_BOOK_WEIGHT)
        for name, p in zip(names, fair):
            per_team.setdefault(name, []).append((p, w))
        used += 1

    if not per_team or used == 0:
        return {}, 0, 0.0

    consensus: dict[str, float] = {}
    spreads: list[float] = []
    for team, pairs in per_team.items():
        total_w = sum(w for _, w in pairs)
        if total_w <= 0:
            continue
        consensus[team] = sum(p * w for p, w in pairs) / total_w
        probs = [p for p, _ in pairs]
        if len(probs) > 1:
            spreads.append((max(probs) - min(probs)) / 2.0)

    # Renormalise: the weighted average of two devigged books need not sum to
    # exactly 1.
    total = sum(consensus.values())
    if total > 0:
        consensus = {k: v / total for k, v in consensus.items()}

    spread = max(spreads) if spreads else 0.0
    return consensus, used, spread


class TheOddsAPI:
    """Client for the-odds-api.com.

    Free tier is ~500 requests/month, so cache aggressively. The default TTL
    assumes you are quoting pre-game, not in-play; for live markets you need
    a push feed, not this.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        regions: str = "us,eu",
        cache_ttl: float = 120.0,
        book_weights: dict[str, float] | None = None,
    ):
        self.api_key = api_key or os.getenv("POLYBOT_ODDS_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "No odds API key. Set POLYBOT_ODDS_API_KEY or pass api_key."
            )
        self.regions = regions
        self.cache_ttl = cache_ttl
        self.book_weights = book_weights or DEFAULT_BOOK_WEIGHTS
        self._client = JsonClient(THE_ODDS_API_BASE, rate_per_sec=2.0)
        self._cache: dict[str, tuple[float, list[OddsEvent]]] = {}
        self.requests_remaining: int | None = None

    def close(self) -> None:
        self._client.close()

    def events(self, sport_key: str) -> list[OddsEvent]:
        cached = self._cache.get(sport_key)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            return cached[1]

        try:
            raw = self._client.get(
                f"/sports/{sport_key}/odds",
                {
                    "apiKey": self.api_key,
                    "regions": self.regions,
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
            )
        except Exception as exc:
            log.error("Odds fetch failed for %s: %s", sport_key, exc)
            # Serve stale rather than nothing -- but never silently: a stale
            # model quoting a moving game is how you get run over.
            if cached:
                log.warning("Serving stale odds for %s (%.0fs old)",
                            sport_key, time.monotonic() - cached[0])
                return cached[1]
            return []

        events = [e for e in (self._parse(row, sport_key) for row in raw or []) if e]
        self._cache[sport_key] = (time.monotonic(), events)
        log.info("Fetched %d events for %s", len(events), sport_key)
        return events

    def _parse(self, row: dict[str, Any], sport_key: str) -> OddsEvent | None:
        try:
            home = str(row["home_team"])
            away = str(row["away_team"])
            commence = _parse_iso(row.get("commence_time"))
        except (KeyError, TypeError):
            return None

        consensus, count, spread = build_consensus(
            row.get("bookmakers", []) or [], weights=self.book_weights
        )
        if not consensus:
            return None

        return OddsEvent(
            event_id=str(row.get("id") or f"{home}-{away}-{commence}"),
            sport_key=sport_key,
            commence_time=commence,
            home_team=home,
            away_team=away,
            consensus=consensus,
            book_count=count,
            spread=spread,
        )


class StaticOddsProvider:
    """In-memory provider for tests and offline replay."""

    def __init__(self, events: list[OddsEvent]):
        self._events = events

    def events(self, sport_key: str) -> list[OddsEvent]:
        return [e for e in self._events if e.sport_key == sport_key or not sport_key]


def _parse_iso(value: Any) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0
