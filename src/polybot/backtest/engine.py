"""Replay engine: run the real quoting strategy over recorded market data.

Deliberately drives the same `MakerStrategy` the live bot uses, rather than a
reimplementation. A backtest of a different strategy than the one you deploy
tells you nothing, and reimplementations drift.

PnL is reported three ways, because each hides a different lie:

  - **realised** -- closed round trips only. Honest but ignores the position
    you are still holding, which is where the losses hide when a strategy
    accumulates a losing inventory.
  - **inventory mark** -- open position valued at the final mid. Necessary,
    but flattering if the strategy ends holding something illiquid.
  - **net** -- the two together, after fees. The number that matters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import MakerParams
from ..economics import FeeSchedule
from ..execution.risk import Position
from ..marketdata.store import PublicTrade, Snapshot
from ..simulation.fills import FillSimulator, SimulatedFill, SimulatedOrder
from ..simulation.markout import (
    Calibration,
    MarkoutResult,
    calibrate,
    compute_markouts,
)
from ..strategy.fair_value import FairValueModel
from ..strategy.maker import MakerStrategy

log = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    snapshots_processed: int = 0
    trades_processed: int = 0
    quotes_placed: int = 0
    fills: list[SimulatedFill] = field(default_factory=list)

    realised_pnl: float = 0.0
    inventory_value: float = 0.0
    inventory_cost: float = 0.0
    fees_paid: float = 0.0

    positions: dict[str, Position] = field(default_factory=dict)
    markouts: dict[int, MarkoutResult] = field(default_factory=dict)
    calibration: Calibration | None = None
    skip_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def inventory_pnl(self) -> float:
        return self.inventory_value - self.inventory_cost

    @property
    def net_pnl(self) -> float:
        return self.realised_pnl + self.inventory_pnl - self.fees_paid

    @property
    def filled_volume(self) -> float:
        return sum(f.size for f in self.fills)

    @property
    def fill_ratio(self) -> float:
        """Fills per quote placed. A very low number means the strategy is
        quoting where nobody trades."""
        return len(self.fills) / self.quotes_placed if self.quotes_placed else 0.0

    @property
    def price_through_share(self) -> float:
        total = self.filled_volume
        if total <= 0:
            return 0.0
        return sum(f.size for f in self.fills if f.reason == "price_through") / total

    @property
    def pnl_per_share(self) -> float:
        vol = self.filled_volume
        return self.net_pnl / vol if vol > 0 else 0.0

    def summary(self) -> str:
        lines = [
            "Backtest result",
            "=" * 60,
            f"  snapshots         {self.snapshots_processed:,}",
            f"  trades            {self.trades_processed:,}",
            f"  quotes placed     {self.quotes_placed:,}",
            f"  fills             {len(self.fills):,} "
            f"({self.filled_volume:,.0f} shares, {self.fill_ratio:.1%} of quotes)",
            f"  picked off        {self.price_through_share:.1%} of filled volume",
            "",
            f"  realised PnL      ${self.realised_pnl:>12,.2f}",
            f"  inventory PnL     ${self.inventory_pnl:>12,.2f}",
            f"  fees paid         ${self.fees_paid:>12,.2f}",
            f"  {'net PnL':<17} ${self.net_pnl:>12,.2f}",
            f"  per share         {self.pnl_per_share * 100:>12.4f}c",
        ]
        if self.skip_reasons:
            top = sorted(self.skip_reasons.items(), key=lambda kv: -kv[1])[:5]
            lines += ["", "  top skip reasons:"]
            lines += [f"    {k}: {v:,}" for k, v in top]
        return "\n".join(lines)


class ReplayEngine:
    def __init__(
        self,
        model: FairValueModel,
        *,
        params: MakerParams | None = None,
        fee_schedule: FeeSchedule | None = None,
        max_inventory_shares: float = 200.0,
        quote_ttl_seconds: float = 300.0,
    ):
        self.model = model
        self.params = params or MakerParams()
        self.maker = MakerStrategy(self.params)
        self.fees = fee_schedule or FeeSchedule()
        self.max_inventory = max_inventory_shares
        self.quote_ttl = quote_ttl_seconds

        self._sim = FillSimulator()
        self._positions: dict[str, Position] = {}
        self._order_seq = 0
        self._result = BacktestResult()

    def run(
        self, snapshots: list[Snapshot], trades: list[PublicTrade]
    ) -> BacktestResult:
        """Replay a recorded session."""
        if not snapshots:
            log.warning("No snapshots to replay")
            return self._result

        timeline = self._merge(snapshots, trades)
        by_token: dict[str, list[Snapshot]] = {}

        for kind, item in timeline:
            if kind == "snap":
                snap: Snapshot = item
                by_token.setdefault(snap.token_id, []).append(snap)
                self._on_snapshot(snap)
                self._result.snapshots_processed += 1
            else:
                for fill in self._sim.on_trade(item):
                    self._book_fill(fill)
                self._result.trades_processed += 1

        self._finalise(by_token)
        return self._result

    # ------------------------------------------------------------ internals

    @staticmethod
    def _merge(
        snapshots: list[Snapshot], trades: list[PublicTrade]
    ) -> list[tuple[str, object]]:
        """Interleave by timestamp.

        Snapshots sort before trades at the same instant, so a quote placed
        off a snapshot can be filled by a trade carrying that same timestamp
        rather than being skipped.
        """
        events: list[tuple[float, int, str, object]] = []
        for s in snapshots:
            events.append((s.ts, 0, "snap", s))
        for t in trades:
            events.append((t.ts, 1, "trade", t))
        events.sort(key=lambda e: (e[0], e[1]))
        return [(kind, item) for _, _, kind, item in events]

    def _position(self, token_id: str) -> Position:
        if token_id not in self._positions:
            self._positions[token_id] = Position(token_id)
        return self._positions[token_id]

    def _on_snapshot(self, snap: Snapshot) -> None:
        for fill in self._sim.on_snapshot(snap):
            self._book_fill(fill)

        book = snap.to_book()
        fair = self.model.estimate(snap.token_id, book)
        if fair is None:
            self._note_skip("no fair value")
            self._expire_stale(snap)
            return

        pos = self._position(snap.token_id)
        decision = self.maker.quote(
            snap.token_id,
            book,
            fair,
            self.fees,
            inventory_shares=pos.shares,
            max_inventory_shares=self.max_inventory,
            tick=snap.tick_size,
        )
        for reason in decision.skipped:
            self._note_skip(reason)

        wanted = {q.side.upper(): q for q in decision.quotes}
        resting = {o.side.upper(): o for o in self._sim.open_orders(snap.token_id)}

        for side, order in resting.items():
            want = wanted.get(side)
            stale = snap.ts - order.placed_ts > self.quote_ttl
            if want is None or stale or self.maker.should_requote(order.price, want.price):
                self._sim.cancel(order.order_id)
            else:
                # Already resting at an acceptable price -- keep queue position.
                wanted.pop(side, None)

        for side, quote in wanted.items():
            self._order_seq += 1
            self._sim.place(
                SimulatedOrder(
                    order_id=f"o{self._order_seq}",
                    token_id=quote.token_id,
                    side=side,
                    price=quote.price,
                    size=quote.size,
                    placed_ts=snap.ts,
                ),
                snap,
            )
            self._result.quotes_placed += 1

    def _expire_stale(self, snap: Snapshot) -> None:
        """Pull quotes we can no longer price."""
        for order in self._sim.open_orders(snap.token_id):
            if snap.ts - order.placed_ts > self.quote_ttl:
                self._sim.cancel(order.order_id)

    def _book_fill(self, fill: SimulatedFill) -> None:
        # Maker fills pay no fee; this is the whole point of the strategy.
        realised = self._position(fill.token_id).apply_fill(
            fill.side, fill.price, fill.size, fee=0.0
        )
        self._result.realised_pnl += realised
        self._result.fills.append(fill)

    def _note_skip(self, reason: str) -> None:
        key = reason.split(" <")[0].split(":")[0].strip()
        self._result.skip_reasons[key] = self._result.skip_reasons.get(key, 0) + 1

    def _finalise(self, by_token: dict[str, list[Snapshot]]) -> None:
        r = self._result
        r.positions = dict(self._positions)

        for token_id, pos in self._positions.items():
            if abs(pos.shares) < 1e-9:
                continue
            snaps = by_token.get(token_id) or []
            final_mid = next(
                (s.mid for s in reversed(snaps) if s.mid is not None), None
            )
            if final_mid is None:
                log.warning("No final mid for %s; inventory left unmarked", token_id[:12])
                continue
            r.inventory_value += pos.shares * final_mid
            r.inventory_cost += pos.shares * pos.avg_price

        # Relative markout whenever thresholds are relative -- i.e. whenever
        # instruments are priced in currency rather than probability.
        r.markouts = compute_markouts(
            r.fills, by_token, relative=self.params.relative_thresholds
        )
        r.calibration = calibrate(
            r.markouts, current=self.params.adverse_selection_per_share
        )
