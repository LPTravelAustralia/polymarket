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

    def trades_deep(
        self,
        user: str,
        *,
        days_back: int = 180,
        window_hours: int = 12,
        max_items: int | None = None,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """Walk history backwards in time, past the offset ceiling.

        `/trades` refuses offsets beyond ~10,000, which on a high-frequency
        wallet is a single day. `/activity` accepts `start`/`end` timestamps,
        so stepping a window backwards reaches arbitrarily deep history.

        Window size is a trade-off: too wide and a busy wallet's window
        exceeds the per-request cap and silently truncates; too narrow and you
        make thousands of requests. 12 hours suits a wallet doing a few
        hundred fills an hour.
        """
        import time as _time

        end = int(now if now is not None else _time.time())
        floor = end - days_back * 86_400
        step = window_hours * 3_600
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        truncated_windows = 0

        while end > floor:
            start = max(floor, end - step)
            rows = list(
                self._c.paginate_offset(
                    "/activity",
                    {"user": user, "type": "TRADE", "start": start, "end": end},
                    max_items=10_000,
                )
            )
            # A full window may mean the window itself was capped, so record
            # it rather than pretending the history is complete.
            if len(rows) >= 10_000:
                truncated_windows += 1

            for row in rows:
                key = (
                    f"{row.get('transactionHash')}|{row.get('asset')}|"
                    f"{row.get('size')}|{row.get('price')}"
                )
                if key in seen:
                    continue
                seen.add(key)
                out.append(row)

            if max_items is not None and len(out) >= max_items:
                return out[:max_items]
            end = start

        if truncated_windows:
            log.warning(
                "%d window(s) hit the record cap; history for those periods is "
                "incomplete. Re-run with a smaller window_hours.", truncated_windows
            )
        return out

    def measure_maker_ratio(
        self, user: str, *, pages: int = 8
    ) -> tuple[int, int, float] | None:
        """Measure maker vs taker fills over a time-aligned window.

        The Data API exposes no maker/taker field, so this differences a
        `takerOnly=true` query against `takerOnly=false`. The subtlety that
        makes a naive version wrong: the two queries return the same *number*
        of rows but cover **different time spans**, because one is a filtered
        subset. Differencing them directly reports the windowing gap as maker
        fills, and if both queries hit the offset ceiling it reports 0% maker
        for everyone.

        So we clip both to the interval each fully covers before comparing.

        Returns (maker_fills, taker_fills, maker_ratio) or None.
        """
        def fetch(taker_only: str) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for offset in range(0, pages * 500, 500):
                try:
                    page = self._c.get(
                        "/trades",
                        {"user": user, "takerOnly": taker_only,
                         "limit": 500, "offset": offset},
                    )
                except Exception:
                    break
                batch = page if isinstance(page, list) else page.get("data", [])
                if not batch:
                    break
                rows.extend(batch)
            return rows

        def key(r: dict[str, Any]) -> str:
            return (
                f"{r.get('transactionHash')}|{r.get('asset')}|"
                f"{r.get('size')}|{r.get('price')}"
            )

        takers = fetch("true")
        allf = fetch("false")
        if not takers or not allf:
            return None

        t_ts = [_as_float(r.get("timestamp")) for r in takers]
        a_ts = [_as_float(r.get("timestamp")) for r in allf]
        lo, hi = max(min(t_ts), min(a_ts)), min(max(t_ts), max(a_ts))
        if hi <= lo:
            return None

        in_window = lambda r: lo <= _as_float(r.get("timestamp")) <= hi  # noqa: E731
        taker_keys = {key(r) for r in takers if in_window(r)}
        all_keys = {key(r) for r in allf if in_window(r)}
        if not all_keys:
            return None

        maker = len(all_keys - taker_keys)
        taker = len(all_keys) - maker
        return maker, taker, maker / len(all_keys)

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
        # /v2/leaderboard is the live one as of this writing. Note that its
        # `window` parameter is accepted but ignored -- every value returns the
        # same rows -- so these are the current top performers, NOT the
        # all-time list. Treat the ordering accordingly.
        attempts = [
            ("/v2/leaderboard", {"window": window, "orderBy": order_by, "limit": limit}),
            ("/leaderboard", {"window": window, "orderBy": order_by, "limit": limit}),
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
            # /v2/leaderboard uses user_id/user_name; older shapes use
            # proxyWallet/name. Accept both rather than silently returning [].
            wallet = (
                row.get("proxyWallet")
                or row.get("wallet")
                or row.get("address")
                or row.get("user_id")
                or row.get("user")
            )
            if not wallet:
                continue
            out.append(
                {
                    "wallet": wallet,
                    "name": (
                        row.get("name")
                        or row.get("user_name")
                        or row.get("pseudonym")
                        or row.get("username")
                    ),
                    "pnl": _as_float(row.get("pnl") or row.get("profit") or row.get("cashPnl")),
                    "volume": _as_float(row.get("volume") or row.get("vol")),
                    "rank": row.get("rank"),
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
