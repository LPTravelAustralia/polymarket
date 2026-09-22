"""What it actually costs to put the carry trade on, measured from live books.

`FUNDING.md` rested on one assumed number: slippage per leg. Every verdict in
it -- including the finding that the excess over cash lives only in the
illiquid tail -- inherits that assumption, so this replaces it with a
measurement. Each leg is priced by walking the real book:

- **spot leg**: buy `notional` on Coinbase, walking the ask side
- **perp leg**: sell `notional` on Hyperliquid, walking the bid side

Cost is reported against the mid, so it includes the half-spread as well as
depth impact. That is the right reference: the mid is what the funding model
implicitly assumes you trade at.

Two things this deliberately does not do:

1. **It does not pick a spot fee.** Coinbase's schedule varies by region and
   volume tier, from well over 0.5% taker at entry to under 0.1% at the top,
   and the published page could not be retrieved from here to confirm which
   applies to an Australian entity. So the fee is left as a parameter and the
   result is reported as the break-even fee instead -- a number you can hold
   against whatever tier you actually get.
2. **It does not treat one snapshot as the book.** Depth moves minute to
   minute. Several snapshots are taken and the median is used.

A walk that runs out of visible book before filling is reported as such
rather than extrapolated. Hyperliquid's `l2Book` returns only 20 levels a
side, so on thin names a large size exhausts it -- which is itself the
answer at that size.
"""

from __future__ import annotations

import json
import logging
import statistics
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable

log = logging.getLogger(__name__)

COINBASE_BOOK = "https://api.exchange.coinbase.com/products/{product}/book?level=2"
HYPERLIQUID_INFO = "https://api.hyperliquid.xyz/info"

# Coinbase rejects requests without a User-Agent with a bare 403, which reads
# like a network-policy denial and is not one.
USER_AGENT = "polybot-research/0.1"

# Hyperliquid perp symbol -> Coinbase spot product, where they differ.
# kPEPE is 1,000 PEPE per contract; slippage is in bps, so scale is irrelevant.
SPOT_SYMBOL = {"kPEPE": "PEPE"}


@dataclass(frozen=True)
class Walk:
    """The result of filling `notional` against one side of a book."""

    notional: float
    filled: float          # notional actually filled from visible levels
    vwap: float | None
    mid: float
    cost_bps: float | None  # vs mid, including half-spread; None if unfilled

    @property
    def exhausted(self) -> bool:
        return self.filled < self.notional * 0.999


def walk_book(
    levels: Iterable[tuple[float, float]], notional: float, mid: float,
    *, side: str,
) -> Walk:
    """Fill `notional` (in quote currency) against sorted price levels.

    `levels` must be ordered best-first: ascending asks for a buy, descending
    bids for a sell. `side` is the taker's side, and cost is signed so that a
    positive number is always a cost to the taker.
    """
    if mid <= 0:
        raise ValueError("mid must be positive")
    remaining = notional
    qty = 0.0
    spent = 0.0
    for px, sz in levels:
        if remaining <= 0:
            break
        take = min(remaining, px * sz)
        qty += take / px
        spent += take
        remaining -= take

    filled = notional - max(remaining, 0.0)
    if qty <= 0:
        return Walk(notional, 0.0, None, mid, None)
    vwap = spent / qty
    if filled < notional * 0.999:
        return Walk(notional, filled, vwap, mid, None)
    sign = 1.0 if side == "buy" else -1.0
    return Walk(notional, filled, vwap, mid, sign * (vwap - mid) / mid * 1e4)


def _get_json(url: str, body: dict | None = None, timeout: float = 20.0):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


Levels = list[tuple[float, float]]


def coinbase_asks(product: str) -> tuple[Levels, float]:
    """Ask side of a Coinbase spot book, and its mid."""
    book = _get_json(COINBASE_BOOK.format(product=product))
    bids = [(float(p), float(s)) for p, s, *_ in book["bids"]]
    asks = [(float(p), float(s)) for p, s, *_ in book["asks"]]
    return asks, (bids[0][0] + asks[0][0]) / 2.0


def hyperliquid_bids(coin: str) -> tuple[Levels, float]:
    """Bid side of a Hyperliquid perp book (20 visible levels), and its mid."""
    book = _get_json(HYPERLIQUID_INFO, {"type": "l2Book", "coin": coin})
    bids = [(float(l["px"]), float(l["sz"])) for l in book["levels"][0]]
    asks = [(float(l["px"]), float(l["sz"])) for l in book["levels"][1]]
    return bids, (bids[0][0] + asks[0][0]) / 2.0


def coinbase_spot_buy(product: str, notional: float) -> Walk:
    asks, mid = coinbase_asks(product)
    return walk_book(asks, notional, mid, side="buy")


def hyperliquid_perp_sell(coin: str, notional: float) -> Walk:
    bids, mid = hyperliquid_bids(coin)
    return walk_book(bids, notional, mid, side="sell")


@dataclass
class LegCost:
    """Median measured cost for one coin, one leg, one size."""

    coin: str
    venue: str
    notional: float
    samples: list[float] = field(default_factory=list)
    exhausted: int = 0

    @property
    def median_bps(self) -> float | None:
        return statistics.median(self.samples) if self.samples else None

    @property
    def usable(self) -> bool:
        # A size that exhausted the visible book in any snapshot is not a size
        # this leg can be relied on to fill.
        return bool(self.samples) and self.exhausted == 0


@dataclass
class HedgeCostSurvey:
    sizes: tuple[float, ...]
    spot: dict[tuple[str, float], LegCost] = field(default_factory=dict)
    perp: dict[tuple[str, float], LegCost] = field(default_factory=dict)
    unlisted: list[str] = field(default_factory=list)
    snapshots: int = 0

    def one_leg_slippage(self, coin: str, notional: float) -> float | None:
        """Spot buy + perp sell, as a fraction of notional. None if either
        leg could not fill at this size."""
        s = self.spot.get((coin, notional))
        p = self.perp.get((coin, notional))
        if not (s and p and s.usable and p.usable):
            return None
        return (s.median_bps + p.median_bps) / 1e4


def survey(
    coins: list[str],
    spot_products: set[str],
    *,
    sizes: tuple[float, ...] = (10_000.0, 50_000.0, 250_000.0),
    snapshots: int = 5,
    interval: float = 60.0,
    pause: float = 0.25,
) -> HedgeCostSurvey:
    """Sample both books for every coin, several times, and keep the median."""
    out = HedgeCostSurvey(sizes=sizes, snapshots=snapshots)
    hedgeable = []
    for c in coins:
        product = f"{SPOT_SYMBOL.get(c, c)}-USD"
        if product in spot_products:
            hedgeable.append((c, product))
        else:
            out.unlisted.append(c)

    for n in range(snapshots):
        t0 = time.time()
        for coin, product in hedgeable:
            # One fetch per book per snapshot, walked at every size, so the
            # sizes within a snapshot are priced off the same book.
            for venue, fetch, key, side, store in (
                ("coinbase", coinbase_asks, product, "buy", out.spot),
                ("hyperliquid", hyperliquid_bids, coin, "sell", out.perp),
            ):
                try:
                    levels, mid = fetch(key)
                except Exception as exc:              # noqa: BLE001
                    log.warning("%s %s: %s", venue, coin, exc)
                    continue
                for size in sizes:
                    leg = store.setdefault((coin, size), LegCost(coin, venue, size))
                    w = walk_book(levels, size, mid, side=side)
                    if w.cost_bps is None:
                        leg.exhausted += 1
                    else:
                        leg.samples.append(w.cost_bps)
            time.sleep(pause)
        log.info("snapshot %d/%d done", n + 1, snapshots)
        if n + 1 < snapshots:
            time.sleep(max(0.0, interval - (time.time() - t0)))
    return out


def render_survey(s: HedgeCostSurvey) -> str:
    lines = [
        "Measured hedge execution: Coinbase spot buy + Hyperliquid perp sell",
        "=" * 78,
        f"  median of {s.snapshots} snapshots, cost vs mid incl. half-spread, "
        "in bps per leg",
        "",
        f"  {'coin':<10}" + "".join(
            f"{'$' + format(int(x), ','):>22}" for x in s.sizes),
        f"  {'':<10}" + "".join(f"{'spot + perp = pair':>22}" for _ in s.sizes),
    ]
    coins = sorted({k[0] for k in s.spot})
    for c in coins:
        cells = []
        for size in s.sizes:
            sp, pp = s.spot.get((c, size)), s.perp.get((c, size))
            def fmt(leg):
                if leg is None or not leg.samples and not leg.exhausted:
                    return "  ?"
                return " ---" if not leg.usable else f"{leg.median_bps:4.1f}"
            pair = s.one_leg_slippage(c, size)
            tot = f"{pair * 1e4:5.1f}" if pair is not None else "  ---"
            cells.append(f"{fmt(sp):>6} + {fmt(pp):>5} = {tot:>5}")
        lines.append(f"  {c:<10}" + "".join(f"{x:>22}" for x in cells))
    if s.unlisted:
        lines += ["", f"  no Coinbase spot market (cannot hedge here): "
                      f"{', '.join(s.unlisted)}"]
    lines += ["", "  --- = the size exhausted the visible book in at least "
                  "one snapshot"]
    return "\n".join(lines)
