"""Fee-aware trade economics.

Everything in this bot routes through here, because on Polymarket in 2026 the
fee is not a rounding error -- it is the single biggest determinant of whether
a strategy makes money.

The taker fee formula is:

    fee = shares * rate * p * (1 - p)

which is a bell curve peaking at p = 0.50. Cross-checks against Polymarket's
published examples:

    100 shares @ 0.50, rate 0.04 -> 100 * 0.04 * 0.25 = $1.00
    100 shares @ 0.50, rate 0.07 -> 100 * 0.07 * 0.25 = $1.75
    500 shares @ 0.50, rate 0.04 -> 500 * 0.04 * 0.25 = $5.00

Two consequences drive the entire design:

1. At mid prices a taker pays ~1.25c/share (5% rate). A taker-in/taker-out
   round trip at 0.50 costs ~2.5c/share -- 5% of a 50c position. You need more
   than 2.5c of genuine edge just to break even. Almost nobody has that
   repeatably.

2. Makers pay zero and are additionally paid a share of the taker fee pool.
   The published academic result that profitable wallets are makers and
   unprofitable wallets are takers is, in large part, just this arithmetic.

So: quote, don't cross, unless the edge clears the fee explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Fallback taker rates by Polymarket category, used only when neither the
# market's own `feeSchedule` nor the live /fee-rate endpoint is available.
# These move -- treat them as a safety net, not as truth.
#
# Checked against live market records on 23 Sep 2026: sports is now 5%
# (sports_fees_v3), not the 3% first recorded here. Geopolitics and world
# events are no longer blanket fee-free -- new markets there carry
# politics_fees at 4%, and only older markets created before fees existed
# are exempt. The fee-free universe today is almost entirely NFL and college
# football (feeType "zero_fees"), which `from_market` reads directly.
# A fallback of zero is the dangerous failure, so neither falls back to it.
FALLBACK_TAKER_RATES: dict[str, float] = {
    "crypto": 0.07,
    "sports": 0.05,
    "finance": 0.04,
    "politics": 0.04,
    "mentions": 0.04,
    "tech": 0.04,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "geopolitics": 0.04,
    "world": 0.04,
}
DEFAULT_TAKER_RATE = 0.05

# Share of the collected taker fee pool redistributed to makers, by category.
MAKER_REBATE_SHARE: dict[str, float] = {
    "sports": 0.15,
    "crypto": 0.20,
}
DEFAULT_MAKER_REBATE_SHARE = 0.25


def _clamp_price(price: float) -> float:
    return min(max(price, 0.0), 1.0)


def taker_fee(size: float, price: float, rate: float) -> float:
    """Fee in USDC for taking `size` shares at `price`.

    Symmetric in price by construction: buying YES at p costs the same fee as
    buying NO at 1-p, which is what makes the two economically identical.
    """
    p = _clamp_price(price)
    return abs(size) * rate * p * (1.0 - p)


def taker_fee_per_share(price: float, rate: float) -> float:
    """Fee per share -- the number to compare directly against edge in cents."""
    p = _clamp_price(price)
    return rate * p * (1.0 - p)


def round_trip_taker_cost_per_share(entry: float, exit_: float, rate: float) -> float:
    """Cost of entering AND exiting as a taker. The number most bots ignore."""
    return taker_fee_per_share(entry, rate) + taker_fee_per_share(exit_, rate)


@dataclass(frozen=True)
class FeeSchedule:
    """Fee terms for one market."""

    taker_rate: float = DEFAULT_TAKER_RATE
    maker_rebate_share: float = DEFAULT_MAKER_REBATE_SHARE

    @classmethod
    def for_category(cls, category: str | None) -> "FeeSchedule":
        key = (category or "").strip().lower()
        return cls(
            taker_rate=FALLBACK_TAKER_RATES.get(key, DEFAULT_TAKER_RATE),
            maker_rebate_share=MAKER_REBATE_SHARE.get(key, DEFAULT_MAKER_REBATE_SHARE),
        )

    @classmethod
    def from_market(cls, market: dict, category: str | None = None) -> "FeeSchedule":
        """Read the fee terms a gamma market record carries about itself.

        Since 2026 every market publishes `feeType` and a `feeSchedule` with
        its taker `rate` and maker `rebateRate`. That is the authoritative
        figure for that market. Markets created before fees existed carry
        neither and pay nothing. Anything else falls back by category.
        """
        sched = market.get("feeSchedule") or {}
        if "rate" in sched:
            return cls(
                taker_rate=float(sched["rate"]),
                maker_rebate_share=float(sched.get("rebateRate", 0.0)),
            )
        if market.get("feeType") is None and not market.get("feesEnabled"):
            return cls(taker_rate=0.0, maker_rebate_share=0.0)
        return cls.for_category(category)

    @classmethod
    def from_bps(cls, base_fee_bps: int, category: str | None = None) -> "FeeSchedule":
        """Build from the CLOB /fee-rate response, which reports basis points."""
        key = (category or "").strip().lower()
        return cls(
            taker_rate=base_fee_bps / 10_000.0,
            maker_rebate_share=MAKER_REBATE_SHARE.get(key, DEFAULT_MAKER_REBATE_SHARE),
        )

    def fee(self, size: float, price: float) -> float:
        return taker_fee(size, price, self.taker_rate)

    def fee_per_share(self, price: float) -> float:
        return taker_fee_per_share(price, self.taker_rate)


@dataclass
class FeeBook:
    """Per-token fee rates, fetched live and cached.

    The live rate is authoritative. Hardcoded category rates are only a
    fallback, because Polymarket has changed them repeatedly.
    """

    _rates: dict[str, FeeSchedule] = field(default_factory=dict)
    default: FeeSchedule = field(default_factory=FeeSchedule)

    def put(self, token_id: str, schedule: FeeSchedule) -> None:
        self._rates[token_id] = schedule

    def get(self, token_id: str) -> FeeSchedule:
        return self._rates.get(token_id, self.default)

    def load_from_clob(self, clob, token_id: str, category: str | None = None) -> FeeSchedule:
        """Fetch the authoritative rate for a token, falling back on failure."""
        try:
            bps = clob.get_fee_rate_bps(token_id)
            schedule = FeeSchedule.from_bps(int(bps or 0), category)
        except Exception:
            schedule = FeeSchedule.for_category(category)
        self.put(token_id, schedule)
        return schedule


@dataclass(frozen=True)
class TradeEconomics:
    """The decision object: is this trade worth doing, and by how much."""

    side: str            # "BUY" or "SELL"
    price: float         # price we would transact at
    size: float          # shares
    fair_value: float    # model's probability estimate
    is_maker: bool
    gross_edge_per_share: float
    fee_per_share: float
    net_edge_per_share: float
    net_edge_total: float

    @property
    def is_profitable(self) -> bool:
        return self.net_edge_total > 0.0


def evaluate_trade(
    side: str,
    price: float,
    size: float,
    fair_value: float,
    schedule: FeeSchedule,
    is_maker: bool,
) -> TradeEconomics:
    """Net edge on a single trade, after fees.

    Gross edge is signed by side: buying is good when fair value is above the
    price you pay, selling is good when it is below. Makers pay no fee; the
    rebate is deliberately NOT credited here, because rebates are paid
    pro-rata from a pool days later and treating them as certain income at
    decision time is how market makers talk themselves into negative-edge
    quotes. See expected_maker_rebate() to account for them separately.
    """
    side_u = side.upper()
    if side_u == "BUY":
        gross = fair_value - price
    elif side_u == "SELL":
        gross = price - fair_value
    else:
        raise ValueError(f"side must be BUY or SELL, got {side!r}")

    fee_ps = 0.0 if is_maker else taker_fee_per_share(price, schedule.taker_rate)
    net_ps = gross - fee_ps
    return TradeEconomics(
        side=side_u,
        price=price,
        size=size,
        fair_value=fair_value,
        is_maker=is_maker,
        gross_edge_per_share=gross,
        fee_per_share=fee_ps,
        net_edge_per_share=net_ps,
        net_edge_total=net_ps * size,
    )


def min_profitable_taker_price(
    fair_value: float, schedule: FeeSchedule, safety_margin: float = 0.0
) -> float:
    """Highest price at which BUYING as a taker still nets positive edge.

    Solves fair - p - rate*p*(1-p) = margin for p. The fee term depends on p,
    so this is a quadratic; we solve it directly rather than iterating.

        rate*p^2 - (1 + rate)*p + (fair - margin) = 0
    """
    r = schedule.taker_rate
    target = fair_value - safety_margin
    if r <= 0:
        return target

    a, b, c = r, -(1.0 + r), target
    disc = b * b - 4 * a * c
    if disc < 0:
        return 0.0
    root = (-b - disc**0.5) / (2 * a)
    return _clamp_price(root)


def expected_maker_rebate(
    size: float,
    price: float,
    schedule: FeeSchedule,
    pool_capture: float,
) -> float:
    """Expected rebate for a maker fill.

    `pool_capture` is your estimated share of the rebate pool for this market
    -- i.e. your quoted volume divided by total maker volume. It must be
    measured from actual payouts, not assumed. Default callers pass a
    deliberately pessimistic value.
    """
    notional_fee = taker_fee(size, price, schedule.taker_rate)
    return notional_fee * schedule.maker_rebate_share * max(0.0, min(pool_capture, 1.0))


def breakeven_win_rate(price: float, schedule: FeeSchedule, is_maker: bool) -> float:
    """Fraction of the time a binary bet at `price` must win to break even.

    Without fees this is just `price`. Fees push it up, and the gap is the
    edge you must have over the market merely to not lose money.
    """
    fee_ps = 0.0 if is_maker else taker_fee_per_share(price, schedule.taker_rate)
    cost = price + fee_ps
    return _clamp_price(cost)
