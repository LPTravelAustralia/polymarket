"""Hyperliquid adapter for the research toolkit.

Why this venue: the complete-set strategy on Polymarket failed on fee drag
(0.92% of capital deployed, measured) and capital velocity (median position
36 days past resolution, capital frozen). Perps fix both -- 0.02% maker fees
and instant settlement. See VENUE.md.

Why the research code survives the move: Hyperliquid publishes every
account's fills on-chain, free and unauthenticated, same as Polymarket. Most
venues don't.

**The data here is strictly better than Polymarket's**, in three ways that
matter for profiling:

  - `crossed` states maker vs taker **directly**. On Polymarket that had to
    be recovered by differencing two queries over an aligned time window, a
    hack that silently reported 0% maker when both queries hit the offset
    ceiling. Here it is a boolean on every fill.
  - `fee` gives the actual fee paid per fill, so fee drag is measured rather
    than modelled.
  - `closedPnl` gives realised PnL per fill, so win rate comes from closed
    trades rather than marked-open positions -- which is exactly the
    "zombie position" distortion that inflates Polymarket leaderboards.

API shapes verified against hyperliquid-python-sdk 0.24.0.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from ..clients.http import RateLimiter

log = logging.getLogger(__name__)

MAINNET_API = "https://api.hyperliquid.xyz"
STATS_API = "https://stats-data.hyperliquid.xyz/Mainnet"

# userFillsByTime returns at most 2,000 fills per request, so a window that
# returns exactly that many is probably truncated.
FILL_PAGE_LIMIT = 2_000

INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "8h": 480, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}

# Observed retention, measured 2026-09-21: candleSnapshot caps at ~5,000 bars
# per request AND stops serving fine intervals beyond these depths. Older
# requests return an empty list rather than an error, so a naive fetcher
# reports far less data than asked for and says nothing.
OBSERVED_RETENTION_DAYS: dict[str, float] = {
    "1m": 4, "5m": 30, "15m": 90, "1h": 365, "4h": 365, "1d": 365,
}


def retention_days(interval: str) -> float:
    """Roughly how far back this interval is served."""
    return OBSERVED_RETENTION_DAYS.get(interval, 30.0)


class HyperliquidAPI:
    """Read-only client for Hyperliquid's public info endpoint.

    Everything used here is unauthenticated: no key, no account.
    """

    def __init__(
        self,
        base_url: str = MAINNET_API,
        *,
        rate_per_sec: float = 5.0,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.limiter = RateLimiter(rate_per_sec)
        self._client = httpx.Client(
            timeout=timeout, headers={"Content-Type": "application/json"}
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HyperliquidAPI":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _post(self, body: dict[str, Any], *, retries: int = 4) -> Any:
        last: Exception | None = None
        for attempt in range(retries):
            self.limiter.acquire()
            try:
                r = self._client.post(f"{self.base_url}/info", json=body)
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"retryable {r.status_code}", request=r.request, response=r
                    )
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                if attempt == retries - 1:
                    break
                time.sleep(2.0**attempt)
        raise RuntimeError(f"Hyperliquid /info {body.get('type')} failed") from last

    # ------------------------------------------------------------- account

    def user_state(self, address: str) -> dict[str, Any]:
        """Open positions and margin summary."""
        return self._post({"type": "clearinghouseState", "user": address})

    def user_fees(self, address: str) -> dict[str, Any]:
        """The account's actual fee tier -- what they really pay."""
        return self._post({"type": "userFees", "user": address})

    def user_funding(self, address: str, start_ms: int) -> list[dict[str, Any]]:
        """Funding payments received or paid.

        Worth pulling: on perps, funding is a real income line that looks
        like trading profit on a leaderboard and is not. Same trap as
        liquidity rewards on Polymarket.
        """
        out = self._post({"type": "userFunding", "user": address, "startTime": start_ms})
        return out if isinstance(out, list) else []

    def user_fills(self, address: str) -> list[dict[str, Any]]:
        out = self._post({"type": "userFills", "user": address})
        return out if isinstance(out, list) else []

    def user_fills_by_time(
        self, address: str, start_ms: int, end_ms: int | None = None
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "type": "userFillsByTime",
            "user": address,
            "startTime": start_ms,
            "aggregateByTime": False,
        }
        if end_ms is not None:
            body["endTime"] = end_ms
        out = self._post(body)
        return out if isinstance(out, list) else []

    def fills_deep(
        self,
        address: str,
        *,
        days_back: int = 90,
        window_hours: int = 24,
        max_items: int | None = None,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        """Walk fills backwards in time.

        Unlike Polymarket's offset paging, this has no ceiling -- time
        windowing is the documented access path rather than a workaround.
        A window returning the page limit is flagged as probably truncated
        rather than assumed complete.
        """
        end = int(now_ms if now_ms is not None else time.time() * 1000)
        floor = end - days_back * 86_400_000
        step = window_hours * 3_600_000

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        truncated = 0

        while end > floor:
            start = max(floor, end - step)
            try:
                batch = self.user_fills_by_time(address, start, end)
            except Exception as exc:
                log.warning("fills window %d-%d failed: %s", start, end, exc)
                end = start
                continue

            if len(batch) >= FILL_PAGE_LIMIT:
                truncated += 1

            for f in batch:
                k = f"{f.get('hash')}|{f.get('oid')}|{f.get('time')}|{f.get('sz')}"
                if k in seen:
                    continue
                seen.add(k)
                out.append(f)

            if max_items is not None and len(out) >= max_items:
                return out[:max_items]
            end = start

        if truncated:
            log.warning(
                "%d window(s) returned the %d-fill page limit and are probably "
                "truncated; re-run with a smaller window_hours.",
                truncated, FILL_PAGE_LIMIT,
            )
        return out

    # ------------------------------------------------------------- candles

    def candles(
        self, coin: str, interval: str, start_ms: int, end_ms: int
    ) -> list[dict[str, Any]]:
        """OHLCV. Fields: t (ms), o, h, l, c, v."""
        out = self._post({
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval,
                    "startTime": start_ms, "endTime": end_ms},
        })
        return out if isinstance(out, list) else []

    def candles_deep(
        self,
        coin: str,
        interval: str = "1m",
        *,
        days_back: int = 30,
        now_ms: int | None = None,
        bars_per_request: int = 4_000,
    ) -> list[dict[str, Any]]:
        """Walk candles backwards, de-duplicated, oldest-first.

        Two venue limits make the naive version silently return a fraction
        of what you asked for, which is how a 30-day request quietly became
        3.6 days of data and an underpowered study:

        1. **~5,000 bars per request, whatever the interval.** Window size
           must therefore be derived from the interval, not fixed in hours.
        2. **Fine intervals are not retained for long.** 1m data stops at
           roughly 4 days; anything older returns an empty list rather than
           an error. `retention_days()` documents the observed limits.

        Requesting history older than the interval retains simply yields
        nothing, so callers get a short series and no warning. This logs
        when the returned span falls well short of the request.
        """
        end = int(now_ms if now_ms is not None else time.time() * 1000)
        floor = end - days_back * 86_400_000

        minutes = INTERVAL_MINUTES.get(interval)
        if minutes is None:
            raise ValueError(f"unsupported interval {interval!r}")
        step = bars_per_request * minutes * 60_000

        by_ts: dict[int, dict[str, Any]] = {}
        empty_windows = 0
        while end > floor:
            start = max(floor, end - step)
            try:
                batch = self.candles(coin, interval, start, end)
            except Exception as exc:
                log.warning("candles %s %d-%d failed: %s", coin, start, end, exc)
                batch = []

            if not batch:
                empty_windows += 1
                # Older windows are empty once retention runs out; keep
                # going a little in case of a transient gap, then stop.
                if empty_windows >= 2 and by_ts:
                    log.info(
                        "%s %s: history ends around %d days back (retention).",
                        coin, interval, int((int(time.time() * 1000) - end) / 86_400_000),
                    )
                    break
            else:
                empty_windows = 0
                for c in batch:
                    t = int(c.get("t", 0))
                    if t:
                        by_ts[t] = c
            end = start

        out = [by_ts[t] for t in sorted(by_ts)]
        if out:
            span_days = (out[-1]["t"] - out[0]["t"]) / 86_400_000
            if span_days < days_back * 0.5:
                log.warning(
                    "%s %s: asked for %d days, got %.1f. Fine intervals are "
                    "not retained long -- use a coarser interval for more history.",
                    coin, interval, days_back, span_days,
                )
        return out

    # --------------------------------------------------------- leaderboard

    def leaderboard(self, limit: int = 25, *, order_by: str = "pnl",
                    window: str = "month") -> list[dict[str, Any]]:
        """Top accounts.

        The leaderboard lives on a separate stats host and is not part of the
        documented /info surface, so it is treated as best-effort: on failure
        callers should fall back to supplying addresses directly.

        `window` is one of day / week / month / allTime.
        """
        try:
            r = self._client.get(f"{STATS_API}/leaderboard")
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:
            log.warning("Hyperliquid leaderboard unavailable: %s", exc)
            return []

        rows = payload.get("leaderboardRows", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []

        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            addr = row.get("ethAddress") or row.get("address") or row.get("user")
            if not addr:
                continue
            perf = _window_performance(row, window)
            out.append(
                {
                    "wallet": addr,
                    "name": row.get("displayName") or None,
                    "pnl": _f(perf.get("pnl")),
                    "volume": _f(perf.get("vlm")),
                    "roi": _f(perf.get("roi")),
                    "account_value": _f(row.get("accountValue")),
                    "raw": row,
                }
            )

        key = {"pnl": "pnl", "volume": "volume", "roi": "roi"}.get(order_by, "pnl")
        out.sort(key=lambda r: r.get(key) or 0.0, reverse=True)
        return out[:limit]


def _window_performance(row: dict[str, Any], window: str) -> dict[str, Any]:
    """Pull the requested window out of windowPerformances.

    Shape is [["day", {...}], ["week", {...}], ...].
    """
    perfs = row.get("windowPerformances")
    if isinstance(perfs, list):
        for entry in perfs:
            if isinstance(entry, (list, tuple)) and len(entry) == 2 and entry[0] == window:
                return entry[1] if isinstance(entry[1], dict) else {}
    return {}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        out = float(v)
        return out if out == out else default   # reject NaN
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------ normalisation


@dataclass
class HyperliquidStats:
    """Facts Hyperliquid gives directly that Polymarket did not."""

    total_fills: int = 0
    maker_fills: int = 0
    taker_fills: int = 0
    total_fees_usd: float = 0.0
    total_notional_usd: float = 0.0
    realised_pnl_usd: float = 0.0
    winning_closes: int = 0
    losing_closes: int = 0

    @property
    def maker_ratio(self) -> float:
        n = self.maker_fills + self.taker_fills
        return self.maker_fills / n if n else 0.0

    @property
    def fee_drag_pct(self) -> float:
        """Fees as a share of notional traded -- the number that killed the
        Polymarket strategy, here measured exactly rather than inferred."""
        return (self.total_fees_usd / self.total_notional_usd * 100.0
                if self.total_notional_usd else 0.0)

    @property
    def close_win_rate(self) -> float | None:
        n = self.winning_closes + self.losing_closes
        return self.winning_closes / n if n else None

    @property
    def net_pnl_after_fees(self) -> float:
        return self.realised_pnl_usd - self.total_fees_usd


def summarise_fills(fills: list[dict[str, Any]]) -> HyperliquidStats:
    """Exact statistics straight off the fill records.

    `closedPnl` is only meaningful on closing fills, so win rate is counted
    over closes rather than over every fill -- counting opens would report a
    win rate over trades that have not yet had an outcome, which is the
    distortion that inflates leaderboard win rates.
    """
    s = HyperliquidStats()
    for f in fills:
        s.total_fills += 1
        px, sz = _f(f.get("px")), abs(_f(f.get("sz")))
        s.total_notional_usd += px * sz
        s.total_fees_usd += _f(f.get("fee"))

        if f.get("crossed") is True:
            s.taker_fills += 1
        elif f.get("crossed") is False:
            s.maker_fills += 1

        direction = str(f.get("dir") or "")
        if "Close" in direction or "Liquidat" in direction:
            pnl = _f(f.get("closedPnl"))
            s.realised_pnl_usd += pnl
            if pnl > 0:
                s.winning_closes += 1
            elif pnl < 0:
                s.losing_closes += 1
    return s


def to_common_fills(fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Hyperliquid fills into the shape `build_fingerprint` expects.

    Deliberately reuses the existing fingerprint code rather than writing a
    second analyser: the archetype logic, hold-time matching and
    concentration metrics are venue-agnostic and should stay that way.
    """
    out = []
    for f in fills:
        px, sz = _f(f.get("px")), abs(_f(f.get("sz")))
        coin = str(f.get("coin") or "")
        out.append(
            {
                # Fingerprint works in seconds; Hyperliquid reports ms.
                "timestamp": int(_f(f.get("time")) / 1000),
                "side": "BUY" if str(f.get("side")) == "B" else "SELL",
                "price": px,
                "size": sz,
                "asset": coin,
                "conditionId": coin,
                "usdcSize": px * sz,
                "title": coin,
                # Carried through for venue-specific reporting.
                "_crossed": f.get("crossed"),
                "_fee": _f(f.get("fee")),
                "_closedPnl": _f(f.get("closedPnl")),
                "_dir": f.get("dir"),
            }
        )
    return out


def iter_windows(start_ms: int, end_ms: int, step_hours: int = 24) -> Iterator[tuple[int, int]]:
    """Yield (start, end) windows walking backwards."""
    step = step_hours * 3_600_000
    end = end_ms
    while end > start_ms:
        s = max(start_ms, end - step)
        yield s, end
        end = s
