"""Deribit dated futures: the carry you can lock in, rather than hope for.

Funding on a perpetual floats. It is paid hourly at whatever rate the market
sets, and `FUNDING.md` showed that the same trade paid 30% in one half-year
and 3% in another. A dated future fixes the answer at entry: buy spot, sell
the September future at a premium, and at expiry the two converge. The
premium, annualised, is a rate you know on day one.

That makes the dated basis two things at once:

- **A regime reading that is itself a price.** In euphoric markets
  leveraged longs pay up for exposure and the basis widens; in quiet markets
  it sits near the cash rate. Unlike funding, what it reads is what you get.
- **A way to act on a RICH reading without betting it lasts.** Funding and
  sUSDe pay tomorrow's rate. The basis pays today's, for months.

Prices here are daily closes from Deribit's own chart history for each
quarterly contract, including expired ones (served by history.deribit.com),
against Coinbase spot closes for the same UTC day. The spot series is not
Deribit's index; the mismatch is a few basis points on a quarterly premium
of one to five percent, well inside the effects measured.
"""

from __future__ import annotations

import bisect
import calendar
import datetime as dt
import json
import statistics
import urllib.request
from dataclasses import dataclass

DERIBIT = "https://www.deribit.com/api/v2/public"
USER_AGENT = "polybot-research/0.1"
DAY_MS = 86_400_000


def last_friday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, calendar.monthrange(year, month)[1])
    while d.weekday() != 4:
        d -= dt.timedelta(days=1)
    return d


def quarterly_name(currency: str, expiry: dt.date) -> str:
    """Deribit's instrument name, e.g. BTC-27DEC24 (no zero padding)."""
    return f"{currency}-{expiry.day}{expiry.strftime('%b').upper()}{expiry.strftime('%y')}"


def annualised_basis(future: float, spot: float, days: float) -> float:
    """Simple annualisation of the futures premium over its remaining life."""
    if spot <= 0 or days <= 0:
        raise ValueError("spot and days must be positive")
    return (future / spot - 1.0) * 365.0 / days


@dataclass(frozen=True)
class BasisPoint:
    date: str
    contract: str
    days: float
    basis: float          # annualised
    expiry_ms: int


def constant_maturity(
    futures: dict[str, dict],
    spot_close: dict[str, float],
    *,
    target_days: float = 90.0,
    min_days: float = 45.0,
    max_days: float = 150.0,
) -> list[BasisPoint]:
    """A daily series of the ~3-month locked rate.

    Each day uses the contract whose remaining life is closest to
    `target_days`, within [min_days, max_days]. Days with no such contract
    are skipped rather than filled from a short-dated one, whose annualised
    premium is dominated by noise.
    """
    by_date: dict[str, list[tuple[str, float, float, int]]] = {}
    for name, f in futures.items():
        exp = int(f["expiry_ms"])
        for t, close in zip(f["ticks"], f["close"]):
            day = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date()
            # A daily bar's close is at the end of its UTC day.
            close_ms = (t + DAY_MS)
            days = (exp - close_ms) / DAY_MS
            if min_days <= days <= max_days and close:
                by_date.setdefault(day.isoformat(), []).append((name, float(close), days, exp))
    out = []
    for day in sorted(by_date):
        s = spot_close.get(day)
        if not s:
            continue
        name, fut, days, exp = min(by_date[day], key=lambda r: abs(r[2] - target_days))
        out.append(BasisPoint(day, name, days, annualised_basis(fut, s, days), exp))
    return out


@dataclass(frozen=True)
class LockVsFloat:
    """One entry: lock the basis, or collect floating funding instead."""

    start: str
    contract: str
    days: float
    locked: float        # annualised basis at entry
    floating: float      # realised annualised funding over the same span

    @property
    def spread(self) -> float:
        """Floating minus locked: what shorting the perp against a long
        future would have earned, annualised, before costs."""
        return self.floating - self.locked


def lock_vs_float(
    basis: list[BasisPoint],
    hourly_funding: list[tuple[int, float]],
    *,
    step_days: int = 7,
) -> list[LockVsFloat]:
    """Compare the locked rate at each entry with the funding that followed.

    Entries are spaced `step_days` apart and each runs to its contract's
    expiry, so consecutive entries overlap; the caller must judge
    significance on non-overlapping entries (see `non_overlapping`).
    """
    fund = sorted(hourly_funding)
    times = [t for t, _ in fund]

    out = []
    for i in range(0, len(basis), step_days):
        b = basis[i]
        start_ms = int(dt.datetime.fromisoformat(b.date).replace(
            tzinfo=dt.timezone.utc).timestamp() * 1000) + DAY_MS
        lo = bisect.bisect_left(times, start_ms)
        hi = bisect.bisect_right(times, b.expiry_ms)
        span = fund[lo:hi]
        # Require near-complete coverage of the holding period.
        if len(span) < 0.9 * (b.expiry_ms - start_ms) / 3_600_000:
            continue
        floating = statistics.fmean(r for _, r in span) * 24 * 365
        out.append(LockVsFloat(b.date, b.contract, b.days, b.basis, floating))
    return out


def non_overlapping(rows: list[LockVsFloat]) -> list[LockVsFloat]:
    """Keep one entry per contract: the first. Contracts do not overlap each
    other's holding periods by more than the roll, so this is close to
    independent."""
    seen, out = set(), []
    for r in rows:
        if r.contract not in seen:
            seen.add(r.contract)
            out.append(r)
    return out


# ------------------------------------------------------------------- live

def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def live_basis(currency: str, *, target_days: float = 90.0,
               min_days: float = 45.0, max_days: float = 150.0) -> BasisPoint | None:
    """The current ~3-month locked rate from Deribit's live books."""
    idx = _get(f"{DERIBIT}/get_index_price?index_name={currency.lower()}_usd")
    spot = float(idx["result"]["index_price"])
    rows = _get(f"{DERIBIT}/get_book_summary_by_currency?currency={currency}"
                f"&kind=future")["result"]
    now = dt.datetime.now(dt.timezone.utc)
    best = None
    for r in rows:
        name = r["instrument_name"]
        if "PERPETUAL" in name:
            continue
        exp = dt.datetime.strptime(name.split("-")[1], "%d%b%y").replace(
            hour=8, tzinfo=dt.timezone.utc)
        days = (exp - now).total_seconds() / 86400
        px = r.get("mid_price") or r.get("mark_price")
        if not px or not (min_days <= days <= max_days):
            continue
        cand = BasisPoint(now.date().isoformat(), name, days,
                          annualised_basis(float(px), spot, days),
                          int(exp.timestamp() * 1000))
        if best is None or abs(days - target_days) < abs(best.days - target_days):
            best = cand
    return best
