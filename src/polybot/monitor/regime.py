"""Is the market currently paying for carrying risk?

Every strategy measured in this repo either failed outright or, in the case
of the funding carry, earned roughly cash. REGIME.md explains why that is
partly a statement about *when* it was measured: the same carry paid 17.5% in
2024 and 4.1% in 2026, and Hyperliquid's own market-making vault (HLP)
returned 79% in 2024 and roughly 0-3% annualised over the last two quarters.

These are cyclical payoffs. They are close to worthless most of the time and
pay very well in euphoric, volatile markets. So the useful question is not
"is this a good trade" but "is this a good trade *right now*", and that is a
question a scheduled job can answer. This module takes four readings:

- **sUSDe 30-day yield** -- the funding carry, run by Ethena at scale and
  sold as a token. The cleanest read on what the carry pays after
  professional execution.
- **HLP trailing 90-day return** -- the house's side of Hyperliquid:
  market making plus liquidation backstop. Flow-adjusted, annualised.
- **BTC/ETH 30-day funding** -- the raw input to the carry, gross. Thirty
  days because that is the horizon its persistence was measured at; a
  seven-day window flipped level 15-36 times a year near a threshold.
- **BTC/ETH 3-month locked rate** -- the premium on Deribit's dated futures,
  annualised: a rate that can be fixed for months rather than hoped for.
  Six years of history, the longest of the four.

Each is classified QUIET / WARMING / RICH against explicit thresholds.
**sUSDe, funding and the locked rate set the regime.** All three are
persistent -- this month's reading predicts next month's at +0.75, +0.51 and
+0.83 respectively -- so a RICH reading says something about the weeks ahead.
The gap between Hyperliquid funding and the locked rate is shown alongside,
as context.

HLP's trailing return does not. Its gains arrive in single liquidation
cascades (+9.7% in the first fortnight of October 2025, +7.0% in late
January 2026, roughly nothing in between), and trailing 90 days predicts the
next 90 at a correlation of +0.03. Letting it trigger alerts would flag HLP
as attractive immediately after each payday, which is exactly backwards. It
is reported as context and never sets the regime.

Thresholds are calibrated against history in REGIME.md so that 2024 reads
RICH and 2026 reads QUIET.

**The funding thresholds sit well above 11% on purpose.** Hyperliquid's
funding has an interest component of 0.01% per 8 hours, which annualises to
10.95% and is what a perp pays when it trades at fair value. A threshold near
that number would fire in perfectly ordinary markets. `FUNDING.md` found
the same trap in the other direction: an "11% baseline" that was just the
floor.

This module reports. It does not trade, and a RICH reading is information
about what the market is paying, not a recommendation to take the risk
that earns it.
"""

from __future__ import annotations

import json
import os
import statistics
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum

HYPERLIQUID_INFO = "https://api.hyperliquid.xyz/info"
HLP_VAULT = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
SUSDE_POOL = "66985a81-9c51-46ca-9977-42b4fe7bc6df"   # DefiLlama: Ethena sUSDe
SUSDE_CHART = f"https://yields.llama.fi/chart/{SUSDE_POOL}"
USER_AGENT = "polybot-regime-monitor/0.1"
HOURS_PER_YEAR = 24 * 365

# What a perp pays at fair value on Hyperliquid, annualised.
FUNDING_INTEREST_BASELINE = 0.0001 / 8 * HOURS_PER_YEAR     # 10.95%

# The 3-month US T-bill on 18 Sep 2026. Every yield watched here is in US
# dollars, so US cash is the like-for-like comparison; an AUD term-deposit
# rate only compares fairly if the currency is hedged (REGIME.md, Currency).
DEFAULT_HURDLE = 0.0408


class Level(IntEnum):
    QUIET = 0
    WARMING = 1
    RICH = 2


MEANING = {
    Level.QUIET: ("Nothing here is paying meaningfully more than cash. "
                  "This is the regime every strategy in this repo was tested "
                  "in, and none of them beat a term deposit by much."),
    Level.WARMING: ("At least one of these is paying noticeably more than "
                    "cash. Worth a look; nothing urgent."),
    Level.RICH: ("The market is paying well for carrying risk. This is the "
                 "regime in which the carry historically paid 15-35% a "
                 "year. The risks in REGIME.md apply in full -- a RICH market "
                 "is also the one most likely to produce the next liquidation "
                 "cascade."),
}


@dataclass(frozen=True)
class Thresholds:
    warm: float
    rich: float

    def classify(self, value: float, slack: float = 0.0) -> Level:
        """`slack` lowers both thresholds; used only to decide whether an
        alert that is already open should be downgraded (hysteresis)."""
        if value >= self.rich - slack:
            return Level.RICH
        if value >= self.warm - slack:
            return Level.WARMING
        return Level.QUIET


DEFAULT_THRESHOLDS = {
    "sUSDe 30d yield": Thresholds(warm=0.065, rich=0.10),
    "HLP 90d return": Thresholds(warm=0.10, rich=0.20),
    "BTC/ETH 30d funding": Thresholds(warm=0.15, rich=0.25),
    # The ~3-month rate lockable on Deribit dated futures, 30-day mean of the
    # BTC/ETH average. Calibrated on 2020-2026: in sUSDe's QUIET months it
    # averaged 4.5%, WARMING 7.4%, RICH 13.2%. Replayed daily, these
    # thresholds read RICH on 58% of 2021 and 51% of 2024 and QUIET on every
    # day of 2022 and 2026, changing level about four times a year.
    "BTC/ETH 3m locked rate": Thresholds(warm=0.08, rich=0.11),
}

# An open alert is only downgraded once the reading is this far below the
# threshold that raised it. Measured on the last year of 30-day funding with
# a threshold placed inside its range, this cuts level changes from 11-12 a
# year to 4-7. It cannot delay an escalation.
HYSTERESIS = 0.01

_ENV_KEYS = {
    "sUSDe 30d yield": "SUSDE",
    "HLP 90d return": "HLP",
    "BTC/ETH 30d funding": "FUNDING",
    "BTC/ETH 3m locked rate": "BASIS",
}


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    v = float(raw.rstrip("%"))
    # Accept "4.5" and "4.5%" as well as "0.045": nobody means a 450% hurdle.
    return v / 100.0 if v >= 1.0 or raw.endswith("%") else v


def thresholds_from_env() -> dict[str, Thresholds]:
    """Defaults, overridden by REGIME_<SIGNAL>_WARM / _RICH if set."""
    out = {}
    for name, t in DEFAULT_THRESHOLDS.items():
        key = _ENV_KEYS[name]
        warm = _env_float(f"REGIME_{key}_WARM")
        rich = _env_float(f"REGIME_{key}_RICH")
        out[name] = Thresholds(warm=warm if warm is not None else t.warm,
                               rich=rich if rich is not None else t.rich)
    return out


def hurdle_from_env() -> float:
    v = _env_float("REGIME_HURDLE")
    return v if v is not None else DEFAULT_HURDLE


@dataclass
class Signal:
    name: str
    thresholds: Thresholds
    value: float | None = None
    detail: str = ""
    error: str | None = None
    # False for raw inputs such as gross funding, which is not comparable to
    # cash until execution is paid (FUNDING.md: roughly 3-4 points of it).
    is_net: bool = True
    # False for signals with no demonstrated persistence, which are shown
    # for context but must not open, escalate or close an alert.
    drives_regime: bool = True
    # False for gauges that are not yields at all (trend, volatility), so
    # comparing them with cash would be meaningless.
    is_yield: bool = True

    @property
    def available(self) -> bool:
        return self.value is not None and self.error is None

    @property
    def level(self) -> Level | None:
        return self.thresholds.classify(self.value) if self.available else None


@dataclass
class Reading:
    signals: list[Signal]
    hurdle: float = DEFAULT_HURDLE
    taken_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    @property
    def drivers(self) -> list[Signal]:
        return [s for s in self.signals if s.drives_regime]

    @property
    def level(self) -> Level | None:
        levels = [s.level for s in self.drivers if s.level is not None]
        return max(levels) if levels else None

    def level_with_slack(self, slack: float) -> Level | None:
        levels = [s.thresholds.classify(s.value, slack)
                  for s in self.drivers if s.available]
        return max(levels) if levels else None

    def held_level(self, previous: Level | None) -> Level | None:
        """The level an open alert should now show, given hysteresis.

        Rises immediately. Falls only when the reading is more than
        HYSTERESIS below the relevant threshold, and never below the raw
        reading.
        """
        raw = self.level
        if raw is None or previous is None or raw >= previous:
            return raw
        sticky = self.level_with_slack(HYSTERESIS)
        return min(previous, sticky) if sticky is not None else raw

    @property
    def complete(self) -> bool:
        return all(s.available for s in self.drivers)


# --------------------------------------------------------------- data access

def _http_json(url: str, body: dict | None = None, *, retries: int = 3):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as exc:                      # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}") from last


def flow_adjusted_return(
    account_values: list[tuple[int, float]],
    pnl: list[tuple[int, float]],
    *,
    since_ms: int | None = None,
    min_base: float = 1e5,
) -> tuple[float, float] | None:
    """Time-weighted return of a vault from its account-value and PnL series.

    Deposits and withdrawals move account value without being performance,
    so each period's return is the change in cumulative PnL divided by the
    account value at the start of the period. Chained, that is a
    time-weighted return. Returns (total return, days covered).

    Validated against Hyperliquid's own `apr` field for HLP over the most
    recent month: 3.8% annualised by this method against 3.0% reported.
    """
    if len(account_values) != len(pnl) or len(pnl) < 2:
        return None
    nav, start_ts, end_ts = 1.0, None, None
    for i in range(1, len(pnl)):
        t_prev, base = account_values[i - 1]
        if since_ms is not None and t_prev < since_ms:
            continue
        if base < min_base:
            continue
        nav *= 1.0 + (pnl[i][1] - pnl[i - 1][1]) / base
        start_ts = t_prev if start_ts is None else start_ts
        end_ts = pnl[i][0]
    if start_ts is None or end_ts is None or end_ts <= start_ts:
        return None
    return nav - 1.0, (end_ts - start_ts) / 86_400_000


def annualise(total: float, days: float) -> float:
    if days <= 0 or total <= -1.0:
        return float("nan")
    return (1.0 + total) ** (365.0 / days) - 1.0


def read_hlp(thresholds: Thresholds, *, window_days: int = 90) -> Signal:
    s = Signal("HLP 90d return", thresholds, drives_regime=False)
    try:
        d = _http_json(HYPERLIQUID_INFO,
                       {"type": "vaultDetails", "vaultAddress": HLP_VAULT})
        port = dict(d["portfolio"])
        allt = port["allTime"]
        av = [(int(t), float(v)) for t, v in allt["accountValueHistory"]]
        pn = [(int(t), float(v)) for t, v in allt["pnlHistory"]]
        since = av[-1][0] - window_days * 86_400_000
        r = flow_adjusted_return(av, pn, since_ms=since)
        if r is None:
            raise ValueError("not enough history in the window")
        total, days = r
        s.value = annualise(total, days)

        m = port.get("month", {})
        r30 = flow_adjusted_return(
            [(int(t), float(v)) for t, v in m.get("accountValueHistory", [])],
            [(int(t), float(v)) for t, v in m.get("pnlHistory", [])])
        last30 = f", last 30d {annualise(*r30):+.1%}" if r30 else ""
        s.detail = (f"{total:+.2%} over {days:.0f}d{last30}; "
                    f"TVL ${av[-1][1] / 1e6:,.0f}M")
    except Exception as exc:                          # noqa: BLE001
        s.error = str(exc)[:200]
    return s


def read_susde(thresholds: Thresholds, *, window_days: int = 30) -> Signal:
    s = Signal("sUSDe 30d yield", thresholds)
    try:
        rows = [r for r in _http_json(SUSDE_CHART)["data"]
                if r.get("apy") is not None]
        recent = rows[-window_days:]
        if len(recent) < window_days // 2:
            raise ValueError(f"only {len(recent)} daily points")
        s.value = statistics.fmean(r["apy"] for r in recent) / 100.0
        s.detail = (f"latest {recent[-1]['apy']:.2f}%, "
                    f"TVL ${recent[-1].get('tvlUsd', 0) / 1e9:,.2f}B "
                    f"(as of {recent[-1]['timestamp'][:10]})")
    except Exception as exc:                          # noqa: BLE001
        s.error = str(exc)[:200]
    return s


def read_funding(thresholds: Thresholds, *, days: int = 30,
                 coins: tuple[str, ...] = ("BTC", "ETH")) -> Signal:
    s = Signal("BTC/ETH 30d funding", thresholds, is_net=False)
    try:
        now = int(time.time() * 1000)
        per = {}
        for c in coins:
            # 30 days of hourly prints is 720 rows; the endpoint returns at
            # most 500, so page forward from the start.
            rates: dict[int, float] = {}
            cursor = now - days * 86_400_000
            while cursor < now:
                rows = _http_json(HYPERLIQUID_INFO, {
                    "type": "fundingHistory", "coin": c,
                    "startTime": cursor, "endTime": now})
                if not rows:
                    break
                for r in rows:
                    rates[int(r["time"])] = float(r["fundingRate"])
                last = max(int(r["time"]) for r in rows)
                if len(rows) < 500 or last <= cursor:
                    break
                cursor = last + 1
                time.sleep(0.3)
            if len(rates) < days * 24 * 0.8:
                raise ValueError(f"{c}: only {len(rates)} hourly prints")
            per[c] = statistics.fmean(rates.values()) * HOURS_PER_YEAR
            time.sleep(0.3)
        s.value = statistics.fmean(per.values())
        s.detail = ", ".join(f"{c} {v:+.1%}" for c, v in per.items()) + \
            f" (fair-value baseline {FUNDING_INTEREST_BASELINE:.2%})"
    except Exception as exc:                          # noqa: BLE001
        s.error = str(exc)[:200]
    return s


def basis_30d_mean(futures: dict[str, dict], spot_close: dict[str, float],
                   *, days: int = 30) -> tuple[float, int] | None:
    """Mean of the constant-maturity ~3m locked rate over the last `days`.

    Daily readings are too noisy to alert on -- replayed over 2020-2026 the
    raw daily rate changed level ~130 times a year and even a 7-day median
    ~20-28 times -- because thin daily closes on the quarterlies produce
    spikes. The 30-day mean is the horizon the persistence (+0.83) was
    measured at. Returns (mean, observations) or None.
    """
    from ..venues.deribit import constant_maturity

    pts = constant_maturity(futures, spot_close)[-days:]
    if len(pts) < days // 2:
        return None
    return statistics.fmean(p.basis for p in pts), len(pts)


def _coinbase_daily_closes(product: str, days: int) -> dict[str, float]:
    end = datetime.now(timezone.utc)
    start = end.timestamp() - (days + 2) * 86400
    url = (f"https://api.exchange.coinbase.com/products/{product}/candles?"
           f"granularity=86400&start={datetime.fromtimestamp(start, timezone.utc).isoformat()}"
           f"&end={end.isoformat()}")
    out = {}
    for t, _lo, _hi, _op, close, _vol in _http_json(url):
        out[datetime.fromtimestamp(t, timezone.utc).date().isoformat()] = float(close)
    return out


def _deribit_quarterlies(currency: str, days: int) -> dict[str, dict]:
    """Daily closes for every quarterly that could be ~3 months out at some
    point in the window: the next three quarterly expiries."""
    from ..venues.deribit import last_friday, quarterly_name

    today = datetime.now(timezone.utc).date()
    out = {}
    y, found = today.year, 0
    while found < 3:
        for m in (3, 6, 9, 12):
            exp = last_friday(y, m)
            if exp <= today or found >= 3:
                continue
            found += 1
            name = quarterly_name(currency, exp)
            start_ms = int((time.time() - (days + 2) * 86400) * 1000)
            r = _http_json(
                "https://www.deribit.com/api/v2/public/get_tradingview_chart_data?"
                f"instrument_name={name}&start_timestamp={start_ms}"
                f"&end_timestamp={int(time.time() * 1000)}&resolution=1D")["result"]
            if r.get("status") == "ok" and r.get("ticks"):
                exp_ms = int(datetime(exp.year, exp.month, exp.day, 8,
                                      tzinfo=timezone.utc).timestamp() * 1000)
                out[name] = {"expiry_ms": exp_ms, "ticks": r["ticks"],
                             "close": r["close"]}
            time.sleep(0.2)
        y += 1
    return out


def read_basis(thresholds: Thresholds, *, days: int = 30,
               coins: tuple[str, ...] = ("BTC", "ETH")) -> Signal:
    s = Signal("BTC/ETH 3m locked rate", thresholds)
    try:
        per = {}
        for c in coins:
            r = basis_30d_mean(_deribit_quarterlies(c, days + 5),
                               _coinbase_daily_closes(f"{c}-USD", days + 5), days=days)
            if r is None:
                raise ValueError(f"{c}: not enough daily readings")
            per[c] = r[0]
        s.value = statistics.fmean(per.values())
        s.detail = (", ".join(f"{c} {v:+.1%}" for c, v in per.items())
                    + " -- a rate you can lock for ~3 months on Deribit")
    except Exception as exc:                          # noqa: BLE001
        s.error = str(exc)[:200]
    return s


def gap_signal(funding: Signal, basis: Signal) -> Signal:
    """Hyperliquid floating funding minus Deribit's locked rate.

    Shorting Hyperliquid's perp against a long Deribit future collected this
    spread, and it was positive in 25 of 26 non-overlapping quarters from
    mid-2023 -- because Hyperliquid funding carries a built-in ~11% interest
    baseline and Deribit does not. But it was +11-12% in 2024 and 1.5-3.5%
    in 2025-26, before fees, margin at two venues, and ADL risk. Context,
    not a trigger: its month-to-month persistence is only +0.3-0.4.
    """
    g = Signal("HL minus Deribit gap", Thresholds(warm=float("inf"), rich=float("inf")),
               is_net=False, drives_regime=False)
    if funding.available and basis.available:
        g.value = funding.value - basis.value
        g.detail = ("what shorting Hyperliquid against a long Deribit future "
                    "collects, gross; see REGIME.md before treating it as free")
    else:
        g.error = "needs both funding and locked rate"
    return g


_NEVER = Thresholds(warm=float("inf"), rich=float("inf"))


def trend_gap(closes: list[float], window: int = 200) -> float | None:
    """Last close relative to its `window`-day simple average."""
    if len(closes) < window:
        return None
    return closes[-1] / statistics.fmean(closes[-window:]) - 1.0


def percentile_rank(history: list[float], value: float) -> float:
    """Share of `history` at or below `value`."""
    if not history:
        return float("nan")
    return sum(1 for h in history if h <= value) / len(history)


def read_trend(coins: tuple[str, ...] = ("BTC", "ETH")) -> Signal:
    """Price against its 200-day average: a risk gauge, not a trigger.

    SIGNALS.md: the gap did not predict next week's or next month's return
    (IC flipped from +0.14 to -0.05 out of sample), but the rule "hold only
    above the average" roughly halved the worst drawdown in both test
    periods for both coins. It is shown so you know which side of it you
    are on; it never raises an alert.
    """
    s = Signal("Trend: price vs 200-day avg", _NEVER, is_net=False,
               drives_regime=False, is_yield=False)
    try:
        per = {}
        for c in coins:
            closes = _coinbase_daily_closes(f"{c}-USD", 210)
            g = trend_gap([closes[d] for d in sorted(closes)])
            if g is None:
                raise ValueError(f"{c}: fewer than 200 daily closes")
            per[c] = g
        s.value = per[coins[0]]
        s.detail = ", ".join(
            f"{c} {g:+.1%} ({'above -- in trend' if g > 0 else 'below -- out of trend'})"
            for c, g in per.items())
    except Exception as exc:                          # noqa: BLE001
        s.error = str(exc)[:200]
    return s


def read_implied_vol(coins: tuple[str, ...] = ("BTC", "ETH")) -> Signal:
    """Deribit implied volatility (DVOL), with its rank over the past year.

    The one feature in SIGNALS.md that predicted anything in both test
    periods: high implied volatility meant high realised volatility the
    following month (BTC IC +0.61, then +0.46 out of sample). It says how
    violent the next month is likely to be, not which way -- a reason to
    size down, never to sell.
    """
    s = Signal("Implied vol (DVOL)", _NEVER, is_net=False, drives_regime=False,
               is_yield=False)
    try:
        now = int(time.time() * 1000)
        per = {}
        for c in coins:
            rows = _http_json(
                "https://www.deribit.com/api/v2/public/get_volatility_index_data?"
                f"currency={c}&start_timestamp={now - 370 * 86_400_000}"
                f"&end_timestamp={now}&resolution=86400")["result"]["data"]
            closes = [r[4] / 100.0 for r in rows]
            if len(closes) < 200:
                raise ValueError(f"{c}: only {len(closes)} days of DVOL")
            per[c] = (closes[-1], percentile_rank(closes, closes[-1]))
            time.sleep(0.2)
        s.value = per[coins[0]][0]
        s.detail = ", ".join(f"{c} {v:.0%} ({pr:.0%} of the past year was lower or equal)"
                             for c, (v, pr) in per.items())
    except Exception as exc:                          # noqa: BLE001
        s.error = str(exc)[:200]
    return s


def take_reading(
    thresholds: dict[str, Thresholds] | None = None,
    hurdle: float | None = None,
) -> Reading:
    t = thresholds or thresholds_from_env()
    funding = read_funding(t["BTC/ETH 30d funding"])
    basis = read_basis(t["BTC/ETH 3m locked rate"])
    return Reading(
        signals=[
            read_susde(t["sUSDe 30d yield"]),
            funding,
            basis,
            read_hlp(t["HLP 90d return"]),
            gap_signal(funding, basis),
            read_trend(),
            read_implied_vol(),
        ],
        hurdle=hurdle_from_env() if hurdle is None else hurdle,
    )


# ------------------------------------------------------------------ report

def render_markdown(r: Reading, *, shown: Level | None = None) -> str:
    """`shown` is the level an open alert is being held at, when hysteresis
    keeps it above the raw reading; the headline then states both."""
    lvl = shown if shown is not None else r.level
    head = lvl.name if lvl is not None else "UNKNOWN"
    held = (shown is not None and r.level is not None and shown != r.level)
    lines = [
        f"## Regime: **{head}**"
        + (f" (raw reading {r.level.name}; held until it is more than "
           f"{HYSTERESIS:.0%} below the threshold)" if held else ""),
        "",
        MEANING[lvl] if lvl is not None else
        "No data source could be read, so no regime can be given.",
        "",
        "| Signal | Reading | vs cash | Level | Warm / rich at |",
        "|---|---|---|---|---|",
    ]
    for s in r.signals:
        if s.available:
            lines.append(
                f"| {s.name} | **{s.value:+.2%}** | "
                + (f"{s.value - r.hurdle:+.2%}" if s.is_net
                   else "gross, n/a" if s.is_yield else "—")
                + " "
                f"| {s.level.name if s.drives_regime else 'context only'} "
                + (f"| {s.thresholds.warm:.1%} / {s.thresholds.rich:.1%} |"
                   if s.drives_regime else "| — |"))
        else:
            lines.append(f"| {s.name} | unavailable | — | — | "
                         + (f"{s.thresholds.warm:.1%} / {s.thresholds.rich:.1%} |"
                            if s.drives_regime else "— |"))
    lines.append("")
    for s in r.signals:
        if s.available and s.detail:
            lines.append(f"- **{s.name}:** {s.detail}")
        elif s.error:
            lines.append(f"- **{s.name}:** could not be read — `{s.error}`")
    if any(not s.drives_regime for s in r.signals):
        lines += ["", "Rows marked *context only* never raise or lower an alert. "
                      "HLP's past return has not predicted its next one; the "
                      "gap is only weakly persistent; trend and implied vol are "
                      "risk gauges -- they tell you how rough the ride is likely "
                      "to be, not which way it goes (SIGNALS.md)."]
    lines += [
        "",
        f"Cash hurdle: **{r.hurdle:.2%}** (US cash by default; `REGIME_HURDLE` "
        "changes it -- see REGIME.md on currency). "
        + ("" if r.complete else
           "**Reading is incomplete**, so an open alert will not be closed "
           "on it. "),
        "",
        f"<sub>Taken {r.taken_at:%Y-%m-%d %H:%M} UTC. This reports what the "
        "market is paying; it is not advice to take the risk that earns it. "
        "See REGIME.md for the risks, including the March 2025 JELLY "
        "incident.</sub>",
    ]
    return "\n".join(lines)
