"""Render profiles as a readable markdown report."""

from __future__ import annotations

from .profiler import WalletProfile


def _fmt_hold(seconds: float | None) -> str:
    if seconds is None:
        return "n/a (no closed round trips)"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    if seconds < 86_400:
        return f"{seconds / 3600:.1f} hours"
    return f"{seconds / 86_400:.1f} days"


def render_profile(p: WalletProfile) -> str:
    fp, arch = p.fingerprint, p.archetype
    name = p.name or fp.wallet[:10] + "..."

    lines = [
        f"### {name}  `{fp.wallet}`",
        "",
        f"**Archetype: {arch.label}** "
        f"(confidence {arch.confidence:.0%}, "
        f"{'REPLICABLE' if arch.replicable else 'NOT replicable by a bot'})",
        "",
    ]

    if p.leaderboard_pnl:
        lines.append(f"- Leaderboard PnL: ${p.leaderboard_pnl:,.0f}")
    if p.leaderboard_volume:
        lines.append(f"- Leaderboard volume: ${p.leaderboard_volume:,.0f}")

    lines += [
        f"- Fills analysed: {fp.total_trades:,} across {fp.distinct_markets:,} markets",
        f"- Volume: ${fp.total_volume_usd:,.0f} "
        f"(mean ${fp.mean_trade_usd:,.0f}, median ${fp.median_trade_usd:,.0f}, "
        f"max ${fp.max_trade_usd:,.0f})",
    ]

    if fp.maker_fills or fp.taker_fills:
        lines.append(
            f"- **Posture: {fp.maker_ratio:.0%} maker** "
            f"({fp.maker_fills:,} passive / {fp.taker_fills:,} aggressive)"
        )
    else:
        lines.append("- Posture: unknown")

    lines += [
        f"- Median hold: {_fmt_hold(fp.median_hold_seconds)} "
        f"({fp.round_trips:,} closed round trips)",
        f"- Activity: {fp.trades_per_active_day:.1f} fills/day over {fp.active_days:,} days",
        f"- Concentration: top market {fp.top_market_volume_share:.1%} of volume "
        f"(HHI {fp.herfindahl:.3f})",
        f"- Mean entry price: {fp.mean_entry_price:.3f}",
    ]

    if fp.win_rate is not None:
        lines.append(f"- Win rate on decided positions: {fp.win_rate:.1%}")
    if fp.realised_pnl:
        lines.append(f"- PnL across sampled positions: ${fp.realised_pnl:,.0f}")

    if fp.category_volume:
        top = sorted(fp.category_volume.items(), key=lambda kv: kv[1], reverse=True)[:4]
        total = sum(fp.category_volume.values()) or 1.0
        mix = ", ".join(f"{k} {v / total:.0%}" for k, v in top)
        lines.append(f"- Category mix: {mix}")

    inc = fp.income
    if inc.reward_events or inc.structural_events:
        lines.append(
            f"- Non-trading income: ${inc.reward_usd:,.0f} rewards "
            f"({inc.reward_events} payouts), {inc.structural_events} split/merge events"
        )

    hist = fp.entry_price_histogram
    if hist and any(hist.values()):
        total = sum(hist.values())
        bars = ", ".join(f"{k} {v / total:.0%}" for k, v in hist.items() if v)
        lines.append(f"- Price placement: {bars}")

    lines += ["", "**Why:**"]
    lines += [f"- {r}" for r in arch.rationale]
    lines += ["", f"**Bot translation:** {arch.bot_translation}"]

    if p.warnings:
        lines += ["", "**Caveats:**"]
        lines += [f"- {w}" for w in p.warnings]

    return "\n".join(lines)


def render_report(profiles: list[WalletProfile]) -> str:
    replicable = [p for p in profiles if p.archetype.replicable]
    makers = [p for p in profiles if p.archetype.label == "SYSTEMATIC_MAKER"]

    header = [
        "# Polymarket top-trader teardown",
        "",
        f"Profiled {len(profiles)} wallets. "
        f"{len(replicable)} show patterns a bot can reproduce; "
        f"{len(profiles) - len(replicable)} do not.",
        "",
    ]

    if makers:
        avg_maker = sum(p.fingerprint.maker_ratio for p in makers) / len(makers)
        header += [
            f"The {len(makers)} systematic maker(s) average {avg_maker:.0%} passive fills. "
            "That is the pattern worth copying.",
            "",
        ]

    body = "\n\n---\n\n".join(render_profile(p) for p in profiles)
    return "\n".join(header) + "\n" + body + "\n"
