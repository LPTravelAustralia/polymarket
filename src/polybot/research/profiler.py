"""Pull the top wallets and profile them.

Usage:

    python -m polybot.cli research --top 5 --max-trades 20000

Requires network access to data-api.polymarket.com and gamma-api.polymarket.com.
Nothing here needs an API key -- every endpoint used is public read.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..clients.data_api import DataAPI
from ..clients.gamma import GammaAPI
from .fingerprint import Archetype, Fingerprint, build_fingerprint, classify

log = logging.getLogger(__name__)


@dataclass
class WalletProfile:
    wallet: str
    name: str | None
    leaderboard_pnl: float
    leaderboard_volume: float
    fingerprint: Fingerprint
    archetype: Archetype
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "name": self.name,
            "leaderboard_pnl": self.leaderboard_pnl,
            "leaderboard_volume": self.leaderboard_volume,
            "fingerprint": asdict(self.fingerprint),
            "archetype": asdict(self.archetype),
            "warnings": self.warnings,
        }


class TraderProfiler:
    def __init__(
        self,
        data: DataAPI | None = None,
        gamma: GammaAPI | None = None,
        *,
        max_trades: int = 20_000,
    ):
        self.data = data or DataAPI()
        self.gamma = gamma or GammaAPI()
        self.max_trades = max_trades
        self._category_cache: dict[str, str] = {}

    def close(self) -> None:
        self.data.close()
        self.gamma.close()

    # ------------------------------------------------------------ discovery

    def top_wallets(self, n: int = 5, window: str = "all") -> list[dict[str, Any]]:
        """Top wallets by PnL, with a bottom-up fallback.

        The leaderboard is the obvious source but it is not part of the
        documented API surface and has moved before. If it is unavailable we
        discover whales from the holder lists of high-volume markets instead,
        which is slower but cannot be turned off.
        """
        rows = self.data.fetch_leaderboard(window=window, order_by="pnl", limit=max(n * 3, 25))
        if rows:
            return rows[:n]

        log.info("Falling back to bottom-up discovery from market holders")
        markets = self.gamma.tradeable_markets(min_liquidity=0, min_volume_24h=0, max_events=150)
        condition_ids = [m.condition_id for m in markets if m.condition_id][:150]
        counts = self.data.discover_wallets_from_markets(condition_ids)
        return [
            {"wallet": w, "name": None, "pnl": 0.0, "volume": 0.0, "appearances": c}
            for w, c in list(counts.items())[:n]
        ]

    # ------------------------------------------------------------- profiling

    def profile(self, wallet: str, name: str | None = None,
                lb_pnl: float = 0.0, lb_volume: float = 0.0) -> WalletProfile:
        warnings: list[str] = []

        log.info("Pulling trade history for %s", wallet)
        trades = list(self.data.trades(user=wallet, taker_only=False, max_items=self.max_trades))
        if len(trades) >= self.max_trades:
            warnings.append(
                f"History truncated at {self.max_trades:,} fills -- statistics cover "
                "only the most recent slice, so lifetime figures will understate."
            )

        # Maker/taker split by differencing. This is the key measurement and
        # the API gives us no direct field for it.
        taker_count: int | None = None
        try:
            takers = list(
                self.data.trades(user=wallet, taker_only=True, max_items=self.max_trades)
            )
            taker_count = len(takers)
        except Exception as exc:
            warnings.append(f"Could not determine maker/taker split: {exc}")
            log.warning("takerOnly query failed for %s: %s", wallet, exc)

        activity: list[dict[str, Any]] = []
        try:
            activity = list(self.data.activity(wallet, max_items=self.max_trades))
        except Exception as exc:
            warnings.append(f"Activity feed unavailable: {exc}")

        positions: list[dict[str, Any]] = []
        try:
            positions = self.data.positions(wallet, max_items=5_000)
        except Exception as exc:
            warnings.append(f"Positions unavailable: {exc}")

        categories = self._categories_for(trades)

        fp = build_fingerprint(
            wallet,
            trades,
            name=name,
            activity=activity,
            taker_fill_count=taker_count,
            positions=positions,
            category_of_market=categories,
        )
        arch = classify(fp)

        if fp.maker_fills == 0 and fp.taker_fills == 0:
            warnings.append(
                "Maker/taker posture unknown -- the archetype call is weaker without it."
            )

        return WalletProfile(
            wallet=wallet,
            name=name,
            leaderboard_pnl=lb_pnl,
            leaderboard_volume=lb_volume,
            fingerprint=fp,
            archetype=arch,
            warnings=warnings,
        )

    def profile_top(self, n: int = 5) -> list[WalletProfile]:
        out: list[WalletProfile] = []
        for row in self.top_wallets(n):
            try:
                out.append(
                    self.profile(
                        row["wallet"],
                        name=row.get("name"),
                        lb_pnl=float(row.get("pnl") or 0.0),
                        lb_volume=float(row.get("volume") or 0.0),
                    )
                )
            except Exception as exc:
                log.error("Failed to profile %s: %s", row.get("wallet"), exc)
        return out

    # ------------------------------------------------------------- internals

    def _categories_for(self, trades: list[dict[str, Any]]) -> dict[str, str]:
        """Best-effort conditionId -> category map.

        Gamma has no bulk lookup by conditionId, so we resolve via slug where
        the trade carries one and leave the rest 'unknown' rather than firing
        thousands of requests.
        """
        out: dict[str, str] = {}
        for t in trades:
            cid = str(t.get("conditionId") or "")
            if not cid or cid in out:
                continue
            if cid in self._category_cache:
                out[cid] = self._category_cache[cid]
                continue
            slug = t.get("slug") or t.get("eventSlug")
            if not slug:
                out[cid] = "unknown"
                continue
            try:
                m = self.gamma.market_by_slug(str(slug))
                cat = ((m or {}).get("category") or "unknown").strip().lower() or "unknown"
            except Exception:
                cat = "unknown"
            self._category_cache[cid] = cat
            out[cid] = cat
        return out


def save_profiles(profiles: list[WalletProfile], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([p.to_dict() for p in profiles], indent=2, default=str),
        encoding="utf-8",
    )
    log.info("Wrote %d profiles to %s", len(profiles), path)
