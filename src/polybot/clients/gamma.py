"""Gamma API -- market and event metadata.

Used for two things: finding markets worth quoting, and attaching a category
to a market so we can look up the right fee rate.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from .http import JsonClient

log = logging.getLogger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"

VALID_ORDERS = {
    "volume_24hr", "volume", "liquidity",
    "start_date", "end_date", "competitive", "closed_time",
}


class GammaAPI:
    def __init__(self, base_url: str = GAMMA_API_BASE, rate_per_sec: float = 8.0):
        self._c = JsonClient(base_url, rate_per_sec=rate_per_sec)

    def close(self) -> None:
        self._c.close()

    def __enter__(self) -> "GammaAPI":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def events(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        tag_id: int | None = None,
        order: str = "volume_24hr",
        ascending: bool = False,
        max_items: int | None = 500,
    ) -> Iterator[dict[str, Any]]:
        if order not in VALID_ORDERS:
            raise ValueError(f"order must be one of {sorted(VALID_ORDERS)}")
        params = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "tag_id": tag_id,
            "order": order,
            "ascending": str(ascending).lower(),
        }
        # Gamma caps limit at 500.
        return self._c.paginate_offset("/events", params, limit=500, max_items=max_items)

    def market_by_slug(self, slug: str) -> dict[str, Any] | None:
        rows = self._c.get("/markets", {"slug": slug})
        if isinstance(rows, list) and rows:
            return rows[0]
        return None

    def tags(self) -> list[dict[str, Any]]:
        rows = self._c.get("/tags")
        return rows if isinstance(rows, list) else []

    def tradeable_markets(
        self,
        *,
        tag_id: int | None = None,
        min_liquidity: float = 5_000.0,
        min_volume_24h: float = 10_000.0,
        max_events: int = 500,
    ) -> list["MarketRef"]:
        """Markets that are actually worth quoting.

        Filters out the long tail: a market with no liquidity and no volume
        cannot pay for the inventory risk of quoting it, and its rebate share
        rounds to nothing.
        """
        out: list[MarketRef] = []
        for event in self.events(tag_id=tag_id, max_items=max_events):
            category = _event_category(event)
            for m in event.get("markets", []) or []:
                if not m.get("enableOrderBook"):
                    continue
                if m.get("closed") or not m.get("active"):
                    continue
                liq = _as_float(m.get("liquidityNum") or m.get("liquidity"))
                vol = _as_float(m.get("volume24hr") or m.get("volume_24hr"))
                if liq < min_liquidity or vol < min_volume_24h:
                    continue
                token_ids = _parse_token_ids(m)
                if len(token_ids) < 2:
                    continue
                out.append(
                    MarketRef(
                        condition_id=m.get("conditionId", ""),
                        question=m.get("question") or m.get("slug") or "",
                        slug=m.get("slug") or "",
                        category=category,
                        token_ids=token_ids,
                        outcomes=_parse_outcomes(m),
                        neg_risk=bool(m.get("negRisk") or m.get("neg_risk")),
                        min_tick=_as_float(m.get("orderPriceMinTickSize")) or 0.001,
                        min_order_size=_as_float(m.get("orderMinSize")) or 5.0,
                        liquidity=liq,
                        volume_24h=vol,
                        end_date=m.get("endDate"),
                    )
                )
        return out


# --------------------------------------------------------------------- types

from dataclasses import dataclass, field  # noqa: E402


@dataclass
class MarketRef:
    """Everything the strategies need to know about a market."""

    condition_id: str
    question: str
    slug: str
    category: str
    token_ids: list[str]
    outcomes: list[str] = field(default_factory=list)
    neg_risk: bool = False
    min_tick: float = 0.001
    min_order_size: float = 5.0
    liquidity: float = 0.0
    volume_24h: float = 0.0
    end_date: str | None = None

    @property
    def is_binary(self) -> bool:
        return len(self.token_ids) == 2

    def complement(self, token_id: str) -> str | None:
        """The other side of a binary market."""
        if not self.is_binary or token_id not in self.token_ids:
            return None
        a, b = self.token_ids
        return b if token_id == a else a


# ----------------------------------------------------------------- utilities


def _parse_token_ids(market: dict[str, Any]) -> list[str]:
    """Gamma returns clobTokenIds as a JSON-encoded string, not a list."""
    raw = market.get("clobTokenIds") or market.get("clob_token_ids")
    return _parse_maybe_json_list(raw)


def _parse_outcomes(market: dict[str, Any]) -> list[str]:
    return _parse_maybe_json_list(market.get("outcomes"))


def _parse_maybe_json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            log.debug("could not parse list field: %r", raw[:80])
    return []


def _event_category(event: dict[str, Any]) -> str:
    """Best-effort category for fee lookup."""
    for tag in event.get("tags", []) or []:
        label = (tag.get("label") or tag.get("slug") or "").strip().lower()
        if label in {
            "sports", "crypto", "politics", "finance", "economics",
            "culture", "weather", "tech", "geopolitics", "world", "mentions",
        }:
            return label
    return (event.get("category") or "").strip().lower()


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
