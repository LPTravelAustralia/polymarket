"""Risk limits and the kill switch.

The strategies decide what is attractive. This decides what is allowed. They
are kept separate on purpose: a bug in a fair-value model should cost a
bounded amount of money, and the only way to guarantee that is for the
bounding code to know nothing about the model.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

from ..config import RiskLimits

log = logging.getLogger(__name__)


@dataclass
class Position:
    token_id: str
    shares: float = 0.0
    avg_price: float = 0.0
    realised_pnl: float = 0.0

    @property
    def notional(self) -> float:
        return abs(self.shares) * self.avg_price

    def apply_fill(self, side: str, price: float, size: float, fee: float = 0.0) -> float:
        """Update the position, returning realised PnL from this fill."""
        realised = 0.0
        if side.upper() == "BUY":
            total_cost = self.avg_price * self.shares + price * size
            self.shares += size
            self.avg_price = total_cost / self.shares if self.shares > 0 else 0.0
        else:
            # Only the portion that closes an existing long realises PnL.
            closed = min(size, max(self.shares, 0.0))
            realised = (price - self.avg_price) * closed
            self.shares -= size
            if abs(self.shares) < 1e-9:
                self.shares = 0.0
                self.avg_price = 0.0
            elif self.shares < 0:
                # The bot does not short, so this means an oversell slipped
                # through. Leave it negative rather than silently zeroing it:
                # a wrong position that is visible can be fixed.
                log.error(
                    "Position %s is short %.2f shares -- this bot does not short",
                    self.token_id, -self.shares,
                )

        realised -= fee
        self.realised_pnl += realised
        return realised


class RiskManager:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self.positions: dict[str, Position] = {}
        self.session_realised_pnl = 0.0
        self.open_order_count = 0
        self._order_times: deque[float] = deque()
        self._halted = False
        self._halt_reason = ""
        self._day_started = time.time()

    # ---------------------------------------------------------------- state

    def position(self, token_id: str) -> Position:
        if token_id not in self.positions:
            self.positions[token_id] = Position(token_id)
        return self.positions[token_id]

    @property
    def total_exposure(self) -> float:
        return sum(p.notional for p in self.positions.values())

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def halt(self, reason: str) -> None:
        if not self._halted:
            log.error("TRADING HALTED: %s", reason)
        self._halted = True
        self._halt_reason = reason

    def resume(self) -> None:
        log.warning("Trading resumed (was halted: %s)", self._halt_reason)
        self._halted = False
        self._halt_reason = ""

    def roll_day(self) -> None:
        """Reset the daily loss counter. Call from a scheduler at UTC midnight."""
        self.session_realised_pnl = 0.0
        self._day_started = time.time()
        if self._halted and "daily loss" in self._halt_reason:
            self.resume()

    # ----------------------------------------------------------- gatekeeping

    def check_order(
        self, token_id: str, side: str, price: float, size: float
    ) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        if self._halted:
            return False, f"halted: {self._halt_reason}"

        if not self._rate_ok():
            return False, "order rate limit exceeded"

        if self.open_order_count >= self.limits.max_open_orders:
            return False, f"max open orders ({self.limits.max_open_orders}) reached"

        notional = price * size
        pos = self.position(token_id)

        # Project the position forward. Only block orders that INCREASE risk --
        # a sell that reduces a long must always be allowed through, otherwise
        # hitting a limit traps you in the position.
        if side.upper() == "BUY":
            projected = (pos.shares + size) * price
            if projected > self.limits.max_position_usd_per_market:
                return False, (
                    f"position cap: ${projected:,.0f} would exceed "
                    f"${self.limits.max_position_usd_per_market:,.0f}"
                )
            if self.total_exposure + notional > self.limits.max_total_exposure_usd:
                return False, (
                    f"exposure cap: ${self.total_exposure + notional:,.0f} would exceed "
                    f"${self.limits.max_total_exposure_usd:,.0f}"
                )

        if not 0.0 < price < 1.0:
            return False, f"price {price} outside (0, 1)"
        if size <= 0:
            return False, "non-positive size"

        return True, "ok"

    def _rate_ok(self) -> bool:
        now = time.monotonic()
        while self._order_times and now - self._order_times[0] > 60.0:
            self._order_times.popleft()
        return len(self._order_times) < self.limits.max_orders_per_minute

    def record_order_sent(self) -> None:
        self._order_times.append(time.monotonic())
        self.open_order_count += 1

    def record_order_closed(self) -> None:
        self.open_order_count = max(0, self.open_order_count - 1)

    # --------------------------------------------------------------- fills

    def record_fill(self, token_id: str, side: str, price: float, size: float,
                    fee: float = 0.0) -> float:
        realised = self.position(token_id).apply_fill(side, price, size, fee)
        self.session_realised_pnl += realised

        if self.session_realised_pnl <= -abs(self.limits.daily_loss_limit_usd):
            self.halt(
                f"daily loss limit hit (${self.session_realised_pnl:,.2f})"
            )
        return realised

    def max_inventory_shares(self, price: float) -> float:
        """Position cap expressed in shares at the current price."""
        if price <= 0:
            return 0.0
        return self.limits.max_position_usd_per_market / price

    def snapshot(self) -> dict[str, float | int | str]:
        return {
            "exposure_usd": round(self.total_exposure, 2),
            "session_pnl_usd": round(self.session_realised_pnl, 2),
            "open_orders": self.open_order_count,
            "positions": len([p for p in self.positions.values() if abs(p.shares) > 1e-9]),
            "halted": str(self._halted),
        }
