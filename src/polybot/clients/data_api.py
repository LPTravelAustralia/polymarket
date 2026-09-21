"""Polymarket Data API -- wallet history, positions, leaderboard.

This is the service the research toolkit runs on. Everything here is public
and unauthenticated: you can pull any wallet's complete trade history, which
is exactly what makes reverse-engineering the top accounts possible.

Endpoints and parameters verified against Polymarket's published Data API
reference. `/leaderboard` is not part of the documented v2 surface and has
moved before, so fetch_leaderboard() is written to tolerate several shapes
and degrade to a documented alternative rather than crash a research run.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from .http import JsonClient

log = logging.getLogger(__name__)

DATA_API_BASE = "https://data-api.polymarket.com"


class DataAPI:
    def __init__(self, base_url: str = DATA_API_BASE, rate_per_sec: float = 8.0):
        self._c = JsonClient(base_url, rate_per_sec=rate_per_sec)

    def close(self) -> None:
        self._c.close()

    def __enter__(self) -> "DataAPI":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- wallets

    def positions(
        self,
        user: str,
        *,
        market: str | None = None,
        size_threshold: float | None = None,
        sort_by: str = "CURRENT",
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        """Open positions for a wallet.

        Fields include: asset, conditionId, size, avgPrice, initialValue,
        currentValue, cashPnl, percentPnl, curPrice, redeemable, title,
        outcome, endDate.
        """
        return list(
            self._c.paginate_offset(
                "/positions",
                {
                    "user": user,
                    "market": market,
                    "sizeThreshold": size_threshold,
                    "sortBy": sort_by,
                    "sortDirection": "DESC",
                },
                max_items=max_items,
            )
        )

    def trades(
        self,
        user: str | None = None,
        *,
        market: str | None = None,
        side: str | None = None,
        taker_only: bool | None = None,
        max_items: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Fills, newest first.

        `takerOnly` defaults to true server-side on some deployments, which
        would silently hide exactly the maker fills we care most about. We
        pass it explicitly.

        Fields include: proxyWallet, side, asset, conditionId, size, price,
        timestamp, title, outcome, transactionHash.
        """
        params = {
            "user": user,
            "market": market,
            "side": side,
            "takerOnly": None if taker_only is None else str(taker_only).lower(),
        }
        return self._c.paginate_offset("/trades", params, max_items=max_items)

    def activity(
        self,
        user: str,
        *,
        activity_type: str | None = None,
        start: int | None = None,
        end: int | None = None,
        max_items: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Full chronological activity: TRADE, SPLIT, MERGE, REDEEM, REWARD,
        CONVERSION.

        Richer than /trades for profiling, because SPLIT/MERGE reveal
        structural arbitrage and REWARD reveals liquidity-mining income --
        two things that look like "trading profit" on a leaderboard but are
        not, and that you must separate out before copying anyone.
        """
        params = {
            "user": user,
            "type": activity_type,
            "start": start,
            "end": end,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        }
        return self._c.paginate_offset("/activity", params, max_items=max_items)

    def value(self, user: str, market: str | None = None) -> dict[str, Any]:
        """Current portfolio value for a wallet."""
        return self._c.get("/value", {"user": user, "market": market})

    def holders(self, market: str, limit: int = 100) -> dict[str, Any]:
        """Largest holders for a market -- a way to discover whales bottom-up
        when the leaderboard is unavailable or gameable."""
        return self._c.get("/holders", {"market": market, "limit": limit})

    # ------------------------------------------------------------ leaderboard

    def fetch_leaderboard(
        self,
        *,
        window: str = "all",
        order_by: str = "pnl",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Top wallets by realised PnL.

        The leaderboard endpoint has moved between hosts and shapes. Rather
        than hardcoding one guess, try the known variants and normalise.
        Returns [] if none respond -- callers should fall back to
        discover_wallets_from_markets().
        """
        attempts = [
            ("/leaderboard", {"window": window, "orderBy": order_by, "limit": limit}),
            ("/v2/leaderboard", {"window": window, "orderBy": order_by, "limit": limit}),
            ("/leaderboard", {"period": window, "sortBy": order_by, "limit": limit}),
        ]
        for path, params in attempts:
            try:
                raw = self._c.get(path, params)
            except Exception as exc:
                log.debug("leaderboard attempt %s failed: %s", path, exc)
                continue
            rows = self._normalise_leaderboard(raw)
            if rows:
                return rows

        log.warning(
            "Leaderboard endpoint unavailable. Fall back to "
            "discover_wallets_from_markets() for bottom-up wallet discovery."
        )
        return []

    @staticmethod
    def _normalise_leaderboard(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, dict):
            for key in ("data", "leaderboard", "results", "traders"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
        if not isinstance(raw, list):
            return []

        out = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            wallet = (
                row.get("proxyWallet")
                or row.get("wallet")
                or row.get("address")
                or row.get("user")
            )
            if not wallet:
                continue
            out.append(
                {
                    "wallet": wallet,
                    "name": row.get("name") or row.get("pseudonym") or row.get("username"),
                    "pnl": _as_float(row.get("pnl") or row.get("profit") or row.get("cashPnl")),
                    "volume": _as_float(row.get("volume") or row.get("vol")),
                    "raw": row,
                }
            )
        return out

    def discover_wallets_from_markets(
        self, condition_ids: list[str], *, per_market: int = 50
    ) -> dict[str, int]:
        """Bottom-up whale discovery: count how often a wallet shows up among
        the largest holders across many markets.

        More robust than the leaderboard, and harder to game -- a wallet that
        is a top holder in 40 different resolved markets is doing something
        systematic, whatever the leaderboard says.
        """
        counts: dict[str, int] = {}
        for cid in condition_ids:
            try:
                payload = self.holders(cid, limit=per_market)
            except Exception as exc:
                log.debug("holders(%s) failed: %s", cid, exc)
                continue
            for token in payload.get("holders", []) if isinstance(payload, dict) else []:
                entries = token.get("holders", []) if isinstance(token, dict) else []
                for h in entries:
                    w = h.get("proxyWallet")
                    if w:
                        counts[w] = counts.get(w, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
