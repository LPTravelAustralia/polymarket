"""Command line entry point.

    polybot research --top 5              # profile the top wallets
    polybot profile 0xabc...              # profile one wallet
    polybot markets --limit 20            # what the bot would quote
    polybot run --dry-run --cycles 5      # quoting loop, sends nothing
    polybot economics --price 0.5         # fee arithmetic for a trade
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Mode, Settings

log = logging.getLogger("polybot")


def cmd_research(args: argparse.Namespace, settings: Settings) -> int:
    from .research.profiler import TraderProfiler, save_profiles
    from .research.report import render_report

    profiler = TraderProfiler(max_trades=args.max_trades)
    try:
        profiles = profiler.profile_top(args.top)
    finally:
        profiler.close()

    if not profiles:
        log.error(
            "No profiles produced. The leaderboard endpoint and the bottom-up "
            "fallback both failed -- check network access to data-api.polymarket.com."
        )
        return 1

    report = render_report(profiles)
    print(report)

    out = Path(args.out)
    save_profiles(profiles, out / "profiles.json")
    (out / "report.md").write_text(report, encoding="utf-8")
    log.info("Wrote %s and %s", out / "profiles.json", out / "report.md")
    return 0


def cmd_profile(args: argparse.Namespace, settings: Settings) -> int:
    from .research.profiler import TraderProfiler
    from .research.report import render_profile

    profiler = TraderProfiler(max_trades=args.max_trades)
    try:
        profile = profiler.profile(args.wallet)
    finally:
        profiler.close()

    print(render_profile(profile))
    return 0


def cmd_markets(args: argparse.Namespace, settings: Settings) -> int:
    from .clients.gamma import GammaAPI

    with GammaAPI() as gamma:
        markets = gamma.tradeable_markets(
            min_liquidity=args.min_liquidity, min_volume_24h=args.min_volume
        )
    markets.sort(key=lambda m: m.volume_24h, reverse=True)

    print(f"{len(markets)} tradeable markets\n")
    for m in markets[: args.limit]:
        flags = []
        if m.neg_risk:
            flags.append("neg-risk")
        if not m.is_binary:
            flags.append(f"{len(m.token_ids)}-way")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  {m.question[:66]:<66} liq ${m.liquidity:>10,.0f}  "
              f"24h ${m.volume_24h:>10,.0f}  {m.category or '?':<10}{suffix}")
    return 0


def cmd_economics(args: argparse.Namespace, settings: Settings) -> int:
    from .economics import (
        FeeSchedule,
        breakeven_win_rate,
        min_profitable_taker_price,
        round_trip_taker_cost_per_share,
    )

    schedule = FeeSchedule.for_category(args.category)
    p = args.price
    size = args.size

    fee = schedule.fee(size, p)
    fee_ps = schedule.fee_per_share(p)
    rt = round_trip_taker_cost_per_share(p, p, schedule.taker_rate)

    print(f"Category:            {args.category} (taker rate {schedule.taker_rate:.2%})")
    print(f"Trade:               {size:,.0f} shares @ {p:.3f}  (${size * p:,.2f} notional)")
    print()
    print(f"Taker fee:           ${fee:,.4f}  ({fee_ps * 100:.3f}c/share)")
    print(f"Round-trip cost:     {rt * 100:.3f}c/share  "
          f"({rt / p:.2%} of notional)")
    print(f"Maker fee:           $0.0000  (plus {schedule.maker_rebate_share:.0%} "
          f"rebate share of the taker pool)")
    print()
    print(f"Breakeven as taker:  {breakeven_win_rate(p, schedule, is_maker=False):.4f}")
    print(f"Breakeven as maker:  {breakeven_win_rate(p, schedule, is_maker=True):.4f}")
    print()
    print("To profit by CROSSING, you must believe fair value exceeds:")
    print(f"  {min_profitable_taker_price(p, schedule):.4f} "
          f"(vs the {p:.4f} you would pay)")
    return 0


def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    from .runner import BotRunner

    if args.dry_run:
        settings.mode = Mode.DRY_RUN
    if settings.mode is not Mode.DRY_RUN:
        settings.require_credentials()

    if settings.mode is Mode.LIVE:
        log.warning("LIVE MODE -- real orders with real money")
        if not args.yes:
            reply = input("Type 'live' to confirm: ").strip().lower()
            if reply != "live":
                log.info("Aborted")
                return 1

    runner = BotRunner(settings)
    runner.install_signal_handlers()
    markets = runner.select_markets(limit=args.markets)
    runner.run(markets, interval=args.interval, max_cycles=args.cycles)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="polybot", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("research", help="profile the top wallets by PnL")
    r.add_argument("--top", type=int, default=5)
    r.add_argument("--max-trades", type=int, default=20_000,
                   help="cap on fills pulled per wallet")
    r.add_argument("--out", default="out", help="output directory")
    r.set_defaults(func=cmd_research)

    pr = sub.add_parser("profile", help="profile one wallet")
    pr.add_argument("wallet")
    pr.add_argument("--max-trades", type=int, default=20_000)
    pr.set_defaults(func=cmd_profile)

    m = sub.add_parser("markets", help="list markets worth quoting")
    m.add_argument("--limit", type=int, default=30)
    m.add_argument("--min-liquidity", type=float, default=5_000.0)
    m.add_argument("--min-volume", type=float, default=10_000.0)
    m.set_defaults(func=cmd_markets)

    e = sub.add_parser("economics", help="fee arithmetic for a hypothetical trade")
    e.add_argument("--price", type=float, default=0.5)
    e.add_argument("--size", type=float, default=100.0)
    e.add_argument("--category", default="sports")
    e.set_defaults(func=cmd_economics)

    run = sub.add_parser("run", help="run the quoting loop")
    run.add_argument("--dry-run", action="store_true", help="force dry-run mode")
    run.add_argument("--markets", type=int, default=15)
    run.add_argument("--interval", type=float, default=5.0)
    run.add_argument("--cycles", type=int, default=None, help="stop after N cycles")
    run.add_argument("--yes", action="store_true", help="skip the live confirmation")
    run.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    settings.setup_logging()
    try:
        return args.func(args, settings)
    except KeyboardInterrupt:
        log.info("Interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
