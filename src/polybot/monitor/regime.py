"""Is the market currently paying for carrying risk?

Every strategy measured in this repo either failed outright or, in the case
of the funding carry, earned roughly cash. REGIME.md explains why that is
partly a statement about *when* it was measured: the same carry paid 17.5% in
2024 and 4.1% in 2026, and Hyperliquid's own market-making vault (HLP)
returned 79% in 2024 and roughly 0-3% annualised over the last two quarters.

These are cyclical payoffs. They are close to worthless most of the time and
pay very well in euphoric, volatile markets. So the useful question is not
"is this a good trade" but "is this a good trade *right now*", and that is a
question a scheduled job can answer. This module takes three readings:

- **sUSDe 30-day yield** -- the funding carry, run by Ethena at scale and
  sold as a token. The cleanest read on what the carry pays after
  professional execution.
- **HLP trailing 90-day return** -- the house's side of Hyperliquid:
  market making plus liquidation backstop. Flow-adjusted, annualised.
- **BTC/ETH 30-day funding** -- the raw input to the carry, gross. Thirty
  days because that is the horizon its persistence was measured at; a
  seven-day window flipped level 15-36 times a year near a threshold.

Each is classified QUIET / WARMING / RICH against explicit thresholds.
**Only the first and third set the regime.** Both are persistent -- this
month's sUSDe yield predicts next month's at a correlation of +0.75 over 30
non-overlapping months, and trailing funding predicts forward funding at
+0.51 -- so a RICH reading says something about the weeks ahead.

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

# The 3-month US T-bill on 18 Sep 2026. For an Australian entity the honest
# hurdle is your own term-deposit rate; set REGIME_HURDLE to that.
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


def take_reading(
    thresholds: dict[str, Thresholds] | None = None,
    hurdle: float | None = None,
) -> Reading:
    t = thresholds or thresholds_from_env()
    return Reading(
        signals=[
            read_susde(t["sUSDe 30d yield"]),
            read_hlp(t["HLP 90d return"]),
            read_funding(t["BTC/ETH 30d funding"]),
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
                f"{f'{s.value - r.hurdle:+.2%}' if s.is_net else 'gross, n/a'} "
                f"| {s.level.name if s.drives_regime else 'context only'} "
                + (f"| {s.thresholds.warm:.1%} / {s.thresholds.rich:.1%} |"
                   if s.drives_regime else "| — |"))
        else:
            lines.append(f"| {s.name} | unavailable | — | — | "
                         f"{s.thresholds.warm:.1%} / {s.thresholds.rich:.1%} |")
    lines.append("")
    for s in r.signals:
        if s.available and s.detail:
            lines.append(f"- **{s.name}:** {s.detail}")
        elif s.error:
            lines.append(f"- **{s.name}:** could not be read — `{s.error}`")
    if any(not s.drives_regime for s in r.signals):
        lines += ["", "HLP is shown for context only: its past return has not "
                      "predicted its next one (it is paid by liquidation "
                      "cascades, which do not announce themselves)."]
    lines += [
        "",
        f"Cash hurdle: **{r.hurdle:.2%}** (set `REGIME_HURDLE` to your own "
        "term-deposit rate). "
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
