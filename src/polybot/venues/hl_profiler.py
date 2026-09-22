"""Profile Hyperliquid accounts using the existing fingerprint engine.

    polybot hl-research --top 5
    polybot hl-profile 0xabc...

Reuses `research/fingerprint.py` rather than reimplementing it. The archetype
classifier, FIFO hold-time matching and concentration metrics describe trader
*behaviour*, not a venue, and keeping one implementation means a fix to the
analysis benefits both venues.

What is venue-specific, and handled here: Hyperliquid states maker/taker and
per-fill fees directly, so those are passed in as exact measurements rather
than inferred.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from ..research.fingerprint import Archetype, Fingerprint, build_fingerprint, classify
from .hyperliquid import HyperliquidAPI, HyperliquidStats, summarise_fills, to_common_fills

log = logging.getLogger(__name__)


@dataclass
class HLProfile:
    wallet: str
    name: str | None
    leaderboard_pnl: float
    leaderboard_roi: float
    account_value: float
    fingerprint: Fingerprint
    archetype: Archetype
    stats: HyperliquidStats
    funding_usd: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "name": self.name,
            "leaderboard_pnl": self.leaderboard_pnl,
            "leaderboard_roi": self.leaderboard_roi,
            "account_value": self.account_value,
            "fingerprint": asdict(self.fingerprint),
            "archetype": asdict(self.archetype),
            "stats": asdict(self.stats),
            "funding_usd": self.funding_usd,
            "warnings": self.warnings,
        }


class HyperliquidProfiler:
    def __init__(
        self,
        api: HyperliquidAPI | None = None,
        *,
        days_back: int = 90,
        max_fills: int = 40_000,
    ):
        self.api = api or HyperliquidAPI()
        self.days_back = days_back
        self.max_fills = max_fills

    def close(self) -> None:
        self.api.close()

    def top_wallets(self, n: int = 5, window: str = "month") -> list[dict[str, Any]]:
        rows = self.api.leaderboard(limit=max(n * 2, 20), window=window)
        return rows[:n]

    def profile(
        self,
        wallet: str,
        *,
        name: str | None = None,
        lb_pnl: float = 0.0,
        lb_roi: float = 0.0,
        account_value: float = 0.0,
    ) -> HLProfile:
        warnings: list[str] = []

        log.info("Pulling Hyperliquid fills for %s", wallet)
        fills = self.api.fills_deep(
            wallet, days_back=self.days_back, max_items=self.max_fills
        )
        if not fills:
            warnings.append("No fills returned for this address in the window.")

        if len(fills) >= self.max_fills:
            warnings.append(
                f"Truncated at {self.max_fills:,} fills -- lifetime figures understate."
            )

        stats = summarise_fills(fills)
        common = to_common_fills(fills)

        # Exact, not inferred. This is the measurement Polymarket forced us to
        # reconstruct by differencing, and got wrong on the first attempt.
        taker_count = stats.taker_fills if (stats.maker_fills or stats.taker_fills) else None
        if taker_count is None:
            warnings.append("No maker/taker flags present on these fills.")

        fp = build_fingerprint(
            wallet, common, name=name, taker_fill_count=taker_count
        )
        # Prefer realised PnL from closing fills over marked-open positions.
        if stats.winning_closes or stats.losing_closes:
            fp.realised_pnl = stats.realised_pnl_usd
            fp.win_rate = stats.close_win_rate

        funding = 0.0
        try:
            start_ms = int((time.time() - self.days_back * 86_400) * 1000)
            for row in self.api.user_funding(wallet, start_ms):
                delta = row.get("delta") if isinstance(row, dict) else None
                if isinstance(delta, dict):
                    funding += float(delta.get("usdc") or 0.0)
        except Exception as exc:
            warnings.append(f"Funding history unavailable: {exc}")

        if funding and stats.realised_pnl_usd:
            share = abs(funding) / max(abs(stats.realised_pnl_usd), 1.0)
            if share > 0.20:
                warnings.append(
                    f"Funding is ${funding:,.0f} against ${stats.realised_pnl_usd:,.0f} "
                    "realised -- a material share of income is carry, not trading edge."
                )

        return HLProfile(
            wallet=wallet,
            name=name,
            leaderboard_pnl=lb_pnl,
            leaderboard_roi=lb_roi,
            account_value=account_value,
            fingerprint=fp,
            archetype=classify(fp),
            stats=stats,
            funding_usd=funding,
            warnings=warnings,
        )

    def profile_top(self, n: int = 5) -> list[HLProfile]:
        out: list[HLProfile] = []
        rows = self.top_wallets(n)
        if not rows:
            log.error(
                "Leaderboard unavailable. Pass addresses directly with "
                "`polybot hl-profile <address>`."
            )
            return out

        for row in rows:
            try:
                out.append(
                    self.profile(
                        row["wallet"],
                        name=row.get("name"),
                        lb_pnl=float(row.get("pnl") or 0.0),
                        lb_roi=float(row.get("roi") or 0.0),
                        account_value=float(row.get("account_value") or 0.0),
                    )
                )
            except Exception as exc:
                log.error("Failed to profile %s: %s", row.get("wallet"), exc)
        return out


def render_hl_profile(p: HLProfile) -> str:
    fp, s, a = p.fingerprint, p.stats, p.archetype
    name = p.name or p.wallet[:10] + "..."

    lines = [
        f"### {name}  `{p.wallet}`",
        "",
        f"**Archetype: {a.label}** (confidence {a.confidence:.0%}, "
        f"{'REPLICABLE' if a.replicable else 'NOT replicable by a bot'})",
        "",
    ]
    if p.leaderboard_pnl:
        lines.append(f"- Leaderboard PnL: ${p.leaderboard_pnl:,.0f}"
                     + (f" (ROI {p.leaderboard_roi:.1%})" if p.leaderboard_roi else ""))
    if p.account_value:
        lines.append(f"- Account value: ${p.account_value:,.0f}")

    lines += [
        f"- Fills: {s.total_fills:,} across {fp.distinct_markets} markets",
        f"- Notional: ${s.total_notional_usd:,.0f} "
        f"(mean ${fp.mean_trade_usd:,.0f}, median ${fp.median_trade_usd:,.0f})",
        f"- **Posture: {s.maker_ratio:.1%} maker** "
        f"({s.maker_fills:,} passive / {s.taker_fills:,} aggressive) [exact]",
        f"- **Fees paid: ${s.total_fees_usd:,.2f} = {s.fee_drag_pct:.4f}% of notional** [exact]",
        f"- Realised PnL (closes): ${s.realised_pnl_usd:,.2f}",
        f"- Net after fees: ${s.net_pnl_after_fees:,.2f}",
    ]
    if s.close_win_rate is not None:
        lines.append(
            f"- Win rate on CLOSED trades: {s.close_win_rate:.1%} "
            f"({s.winning_closes:,}W / {s.losing_closes:,}L)"
        )
    if p.funding_usd:
        lines.append(f"- Funding received/paid: ${p.funding_usd:,.2f}")
    if fp.median_hold_seconds is not None:
        h = fp.median_hold_seconds
        unit = f"{h/3600:.1f}h" if h >= 3600 else f"{h/60:.0f}m"
        lines.append(f"- Median hold: {unit} ({fp.round_trips:,} round trips)")
    lines.append(f"- Concentration: top market {fp.top_market_volume_share:.1%} "
                 f"(HHI {fp.herfindahl:.3f})")

    lines += ["", "**Why:**"] + [f"- {r}" for r in a.rationale]
    lines += ["", f"**Bot translation:** {a.bot_translation}"]
    if p.warnings:
        lines += ["", "**Caveats:**"] + [f"- {w}" for w in p.warnings]
    return "\n".join(lines)


def render_hl_report(profiles: list[HLProfile]) -> str:
    if not profiles:
        return "# Hyperliquid teardown\n\nNo profiles produced.\n"

    header = [
        "# Hyperliquid top-trader teardown",
        "",
        f"Profiled {len(profiles)} accounts. Maker/taker posture and fee drag are "
        "**exact** here -- Hyperliquid flags every fill -- rather than inferred as "
        "they had to be on Polymarket.",
        "",
    ]
    drags = [p.stats.fee_drag_pct for p in profiles if p.stats.total_notional_usd]
    if drags:
        header += [
            f"Median measured fee drag: **{sorted(drags)[len(drags)//2]:.4f}% of "
            f"notional** (Polymarket, measured: 0.92% of capital deployed).",
            "",
        ]
    return "\n".join(header) + "\n" + "\n\n---\n\n".join(
        render_hl_profile(p) for p in profiles
    ) + "\n"
