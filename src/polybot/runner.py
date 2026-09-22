"""The trading loop.

One pass per cycle:
  1. refresh books for the markets we care about
  2. ask the fair-value model for an estimate
  3. ask the maker strategy for quotes
  4. reconcile against what is resting
  5. opportunistically check structural arbitrage
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field

from .clients.clob import ClobGateway
from .clients.gamma import GammaAPI, MarketRef
from .config import Mode, Settings
from .execution.order_manager import OrderManager
from .execution.risk import RiskManager
from .strategy.fair_value import FairValueModel, MicropriceModel
from .strategy.maker import MakerStrategy
from .strategy.structural import find_basket_arb, find_complement_arb

log = logging.getLogger(__name__)


@dataclass
class LoopStats:
    cycles: int = 0
    quotes_posted: int = 0
    quotes_rejected: int = 0
    arbs_found: int = 0
    skips: dict[str, int] = field(default_factory=dict)

    def note_skip(self, reason: str) -> None:
        # Collapse the variable numeric part so the tally stays readable.
        key = reason.split(" <")[0].split(":")[0].strip()
        self.skips[key] = self.skips.get(key, 0) + 1


class BotRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        fair_value_model: FairValueModel | None = None,
        gateway: ClobGateway | None = None,
    ):
        self.settings = settings
        self.gateway = gateway or ClobGateway(settings)
        self.risk = RiskManager(settings.risk)
        self.maker = MakerStrategy(settings.maker)
        self.orders = OrderManager(
            self.gateway, self.risk, requote_threshold=settings.maker.requote_threshold
        )
        self.model = fair_value_model or MicropriceModel()
        self.stats = LoopStats()
        self._stop = False

        if fair_value_model is None:
            log.warning(
                "Running with MicropriceModel: spread capture only, NO informational "
                "edge. Supply an ExternalModel before expecting to make money."
            )

    # --------------------------------------------------------------- control

    def install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("Signal %s received, shutting down", signum)
            self._stop = True

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------ market set

    def select_markets(self, *, category_tag: int | None = None, limit: int = 25) -> list[MarketRef]:
        with GammaAPI() as gamma:
            markets = gamma.tradeable_markets(tag_id=category_tag)

        markets.sort(key=lambda m: m.volume_24h, reverse=True)
        selected = markets[:limit]
        log.info("Selected %d markets to quote", len(selected))
        for m in selected[:5]:
            log.info("  %s (liq $%.0f, 24h $%.0f)", m.question[:60], m.liquidity, m.volume_24h)
        return selected

    # ------------------------------------------------------------- main loop

    def run(self, markets: list[MarketRef], *, interval: float = 5.0,
            max_cycles: int | None = None) -> LoopStats:
        if not markets:
            log.error("No markets to quote")
            return self.stats

        log.info(
            "Starting in %s mode across %d markets (interval %.1fs)",
            self.settings.mode.value, len(markets), interval,
        )

        # Prime the fee cache once; rates rarely change intraday.
        for m in markets:
            for tid in m.token_ids:
                self.gateway.fee_schedule(tid, m.category)

        try:
            while not self._stop:
                if max_cycles is not None and self.stats.cycles >= max_cycles:
                    break

                started = time.monotonic()
                try:
                    self._cycle(markets)
                except Exception:
                    log.exception("Cycle failed; continuing")

                self.stats.cycles += 1

                if self.risk.halted:
                    log.error("Risk halt active (%s) -- pulling quotes and stopping",
                              self.risk.halt_reason)
                    break

                elapsed = time.monotonic() - started
                time.sleep(max(0.0, interval - elapsed))
        finally:
            log.info("Shutting down: cancelling resting orders")
            self.orders.cancel_all()
            log.info("Final state: %s", self.risk.snapshot())
            log.info(
                "Cycles=%d posted=%d rejected=%d arbs=%d",
                self.stats.cycles, self.stats.quotes_posted,
                self.stats.quotes_rejected, self.stats.arbs_found,
            )
            if self.stats.skips:
                top = sorted(self.stats.skips.items(), key=lambda kv: -kv[1])[:6]
                log.info("Top skip reasons: %s", ", ".join(f"{k} x{v}" for k, v in top))

        return self.stats

    def _cycle(self, markets: list[MarketRef]) -> None:
        all_tokens = [tid for m in markets for tid in m.token_ids]
        books = self.gateway.books(all_tokens)

        desired = []
        for market in markets:
            if self._too_close_to_resolution(market):
                continue

            for token_id in market.token_ids:
                book = books.get(token_id)
                if book is None:
                    continue

                fair = self.model.estimate(token_id, book)
                if fair is None:
                    self.stats.note_skip("no fair value")
                    continue

                pos = self.risk.position(token_id)
                decision = self.maker.quote(
                    token_id,
                    book,
                    fair,
                    self.gateway.fees.get(token_id),
                    inventory_shares=pos.shares,
                    max_inventory_shares=self.risk.max_inventory_shares(fair.price),
                    tick=book.tick_size,
                )
                desired.extend(decision.quotes)
                for reason in decision.skipped:
                    self.stats.note_skip(reason)

            self._check_structural(market, books)

        if desired:
            result = self.orders.reconcile(desired)
            self.stats.quotes_posted += len(result.posted)
            self.stats.quotes_rejected += len(result.rejected)
            log.info("Cycle %d: %s | %s",
                     self.stats.cycles, result.summary(), self.risk.snapshot())
            for _, reason in result.rejected:
                self.stats.note_skip(reason)

    def _check_structural(self, market: MarketRef, books: dict) -> None:
        tokens = [books.get(t) for t in market.token_ids]
        if any(b is None for b in tokens):
            return
        schedules = [self.gateway.fees.get(t) for t in market.token_ids]

        opp = None
        if market.is_binary:
            opp = find_complement_arb(tokens[0], tokens[1], schedules[0], schedules[1],
                                      self.settings.arb)
        elif market.neg_risk:
            opp = find_basket_arb(tokens, schedules, self.settings.arb)

        if opp is None:
            return

        self.stats.arbs_found += 1
        log.warning(
            "ARB %s on %s: %.3fc/share net, %.0f shares (~$%.2f). %s",
            opp.kind, market.question[:45],
            opp.net_profit_per_share * 100, opp.size_shares,
            opp.net_profit_total, "; ".join(opp.notes),
        )
        # Execution of structural arb is deliberately not automated: the legs
        # must fill atomically or you are left with naked exposure, and doing
        # that safely needs either an atomic on-chain route or latency this
        # stack does not have. Log it, then decide.
        if self.settings.mode is Mode.LIVE:
            log.warning("Arb execution is manual by design -- not auto-firing")

    def _too_close_to_resolution(self, market: MarketRef) -> bool:
        if not market.end_date:
            return False
        try:
            from datetime import datetime, timezone

            end = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
            remaining = (end - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, AttributeError):
            return False

        if remaining < self.settings.risk.min_seconds_to_resolution:
            self.stats.note_skip("too close to resolution")
            return True
        return False
