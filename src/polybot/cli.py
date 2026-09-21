"""Command line entry point.

    polybot research --top 5              # profile the top wallets
    polybot profile 0xabc...              # profile one wallet
    polybot markets --limit 20            # what the bot would quote
    polybot economics --price 0.5         # fee arithmetic for a trade

    polybot record --duration 3600        # collect books/trades for backtests
    polybot backtest --data out/rec/...   # replay the strategy over a recording
    polybot calibrate --data out/rec/...  # measure adverse selection

    polybot run --dry-run --cycles 5      # quoting loop, sends nothing
    polybot run --sports                  # quote using the odds-based model
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


def cmd_hl_research(args: argparse.Namespace, settings: Settings) -> int:
    import json

    from .venues.hl_profiler import HyperliquidProfiler, render_hl_report

    profiler = HyperliquidProfiler(days_back=args.days, max_fills=args.max_fills)
    try:
        profiles = profiler.profile_top(args.top)
    finally:
        profiler.close()

    if not profiles:
        log.error(
            "No profiles produced. Check network access to api.hyperliquid.xyz, "
            "or pass an address directly with `polybot hl-profile <address>`."
        )
        return 1

    report = render_hl_report(profiles)
    print(report)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "hyperliquid_report.md").write_text(report, encoding="utf-8")
    (out / "hyperliquid_profiles.json").write_text(
        json.dumps([p.to_dict() for p in profiles], indent=2, default=str),
        encoding="utf-8",
    )
    log.info("Wrote %s", out / "hyperliquid_report.md")
    return 0


def cmd_hl_profile(args: argparse.Namespace, settings: Settings) -> int:
    from .venues.hl_profiler import HyperliquidProfiler, render_hl_profile

    profiler = HyperliquidProfiler(days_back=args.days, max_fills=args.max_fills)
    try:
        profile = profiler.profile(args.wallet)
    finally:
        profiler.close()

    print(render_hl_profile(profile))
    return 0


def cmd_shock(args: argparse.Namespace, settings: Settings) -> int:
    """Test whether news-driven moves are tradeable after they start."""
    from .research.event_study import Candle, render_event_study, run_event_study
    from .venues.hyperliquid import HyperliquidAPI

    horizons = tuple(int(h) for h in args.horizons.split(",") if h.strip())

    api = HyperliquidAPI()
    pooled: list = []
    try:
        any_data = False
        for coin in [c.strip().upper() for c in args.coins.split(",") if c.strip()]:
            raw = api.candles_deep(coin, args.interval, days_back=args.days)
            if not raw:
                log.error("No candles for %s -- check access to api.hyperliquid.xyz", coin)
                continue
            any_data = True
            candles = [Candle.from_hyperliquid(c) for c in raw]
            study = run_event_study(
                coin, candles, threshold_sigma=args.sigma, horizons=horizons
            )
            pooled.append(study)
            print(render_event_study(study, round_trip_cost=args.cost))
            print()
    finally:
        api.close()

    if not any_data:
        return 1

    # Per-coin samples are usually too small for a verdict. Pooling across
    # coins is the only way to reach a sample that supports one -- at the
    # cost of assuming the effect is common across them.
    if len(pooled) > 1:
        from .research.event_study import pool_studies

        combined = pool_studies(pooled)
        print(render_event_study(combined, round_trip_cost=args.cost))
        print()

    print("Reminder: a drift that is statistically real but smaller than the")
    print("round-trip cost is a statistically real way to lose money.")
    return 0


def cmd_hl_quote(args: argparse.Namespace, settings: Settings) -> int:
    """Dry-run the existing maker strategy against live Hyperliquid books."""
    from .strategy.fair_value import MicropriceModel
    from .strategy.maker import MakerStrategy
    from .venues.hl_market import HyperliquidMarketData

    md = HyperliquidMarketData()
    try:
        coins = (
            [c.strip().upper() for c in args.coins.split(",") if c.strip()]
            if args.coins else md.universe(limit=args.limit)
        )
        if not coins:
            log.error("No symbols available -- check access to api.hyperliquid.xyz")
            return 1

        from .config import MakerParams

        fees = md.fee_schedule(args.address or None)
        # Perp defaults: thresholds as fractions of price, no probability
        # bounds. Using the prediction-market defaults here quotes DYDX 9%
        # below the market and rejects BTC outright.
        params = MakerParams.for_perps(order_size_shares=settings.maker.order_size_shares)
        model = MicropriceModel(min_uncertainty=0.0002, relative=True)
        maker = MakerStrategy(params)

        print(f"Fee tier: taker {fees.taker_rate * 100:.4f}%  "
              f"maker {fees.maker_rate * 100:.4f}%"
              + ("  (REBATE)" if fees.maker_is_rebated else ""))
        print(f"Strategy: min edge {params.min_edge_per_share * 100:.3f}%, "
              f"adverse selection {params.adverse_selection_per_share * 100:.3f}%")
        print()
        print(f"{'symbol':<10} {'bid':>12} {'ask':>12} {'spread':>9} "
              f"{'fair':>12} {'action':>28}")
        print("-" * 90)

        quoted = skipped = 0
        for coin in coins:
            book = md.book(coin)
            if book is None or book.best_bid is None:
                print(f"{coin:<10} {'no book':>12}")
                continue

            spread_pct = (book.spread / book.mid * 100) if book.mid else 0.0
            fair = model.estimate(coin, book)
            if fair is None:
                print(f"{coin:<10} {book.best_bid:>12.4f} {book.best_ask:>12.4f} "
                      f"{spread_pct:>8.3f}% {'-':>12} {'no fair value':>28}")
                continue

            # The strategy is used unmodified. Inventory is assumed flat, so
            # only the bid side is quoted -- it does not short.
            decision = maker.quote(
                coin, book, fair, fees,
                inventory_shares=0.0,
                max_inventory_shares=args.max_size,
                tick=book.tick_size,
            )
            if decision.quotes:
                quoted += 1
                for q in decision.quotes:
                    edge_pct = q.edge_per_share / fair.price * 100
                    action = f"{q.side} {q.size:g} @ {q.price:.4f} (+{edge_pct:.3f}%)"
                    print(f"{coin:<10} {book.best_bid:>12.4f} {book.best_ask:>12.4f} "
                          f"{spread_pct:>8.3f}% {fair.price:>12.4f} {action:>28}")
            else:
                skipped += 1
                why = decision.skipped[0][:28] if decision.skipped else "no quote"
                print(f"{coin:<10} {book.best_bid:>12.4f} {book.best_ask:>12.4f} "
                      f"{spread_pct:>8.3f}% {fair.price:>12.4f} {why:>28}")

        print("-" * 90)
        print(f"would quote {quoted}, declined {skipped}")
        print()
        print("NOTE: MicropriceModel has NO informational edge by construction.")
        print("These quotes capture spread only. A high decline rate here is the")
        print("strategy correctly refusing to quote inside its own uncertainty.")
    finally:
        md.close()
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


def _build_sports_model(markets, settings: Settings):
    """Wire the odds-based fair value model, or return None with a reason."""
    from .models.odds_feed import TheOddsAPI
    from .models.sports import SportsFairValue
    from .strategy.fair_value import ExternalModel

    try:
        provider = TheOddsAPI()
    except RuntimeError as exc:
        log.error("%s", exc)
        return None

    sports = SportsFairValue(provider)
    bound = sports.register(markets)
    print(sports.coverage_report())
    if bound == 0:
        log.error(
            "No markets could be bound to sportsbook events. The bot would "
            "quote nothing; refusing to start."
        )
        return None
    return ExternalModel(sports.probability_fn)


def cmd_record(args: argparse.Namespace, settings: Settings) -> int:
    from .clients.clob import ClobGateway
    from .clients.gamma import GammaAPI
    from .marketdata.recorder import MarketRecorder

    with GammaAPI() as gamma:
        markets = gamma.tradeable_markets(
            min_liquidity=args.min_liquidity, min_volume_24h=args.min_volume
        )
    markets.sort(key=lambda m: m.volume_24h, reverse=True)
    markets = markets[: args.markets]

    if not markets:
        log.error("No markets matched the filters")
        return 1

    token_ids = [t for m in markets for t in m.token_ids]
    condition_ids = [m.condition_id for m in markets if m.condition_id]
    log.info("Recording %d markets (%d tokens)", len(markets), len(token_ids))

    odds_provider = None
    sport_keys: list[str] = []
    if args.odds:
        from .models.odds_feed import TheOddsAPI
        from .models.sports import SPORT_KEYS

        try:
            odds_provider = TheOddsAPI()
            sport_keys = list(SPORT_KEYS.values())
        except RuntimeError as exc:
            log.warning("Odds recording disabled: %s", exc)

    gateway = ClobGateway(settings)
    recorder = MarketRecorder(
        gateway,
        Path(args.out),
        interval=args.interval,
        odds_provider=odds_provider,
        sport_keys=sport_keys,
    )
    recorder.install_signal_handlers()
    recorder.run(token_ids, condition_ids, duration_seconds=args.duration)
    return 0


def _load_and_replay(args: argparse.Namespace, settings: Settings):
    from .backtest.engine import ReplayEngine
    from .marketdata.store import load_session
    from .strategy.fair_value import MicropriceModel

    snapshots, trades = load_session(Path(args.data))
    if not snapshots:
        log.error("No snapshots found in %s -- run `polybot record` first.", args.data)
        return None

    engine = ReplayEngine(MicropriceModel(), params=settings.maker)
    return engine.run(snapshots, trades)


def cmd_backtest(args: argparse.Namespace, settings: Settings) -> int:
    from .simulation.markout import render_markout_report

    result = _load_and_replay(args, settings)
    if result is None:
        return 1

    print(result.summary())
    print()
    if result.calibration:
        print(render_markout_report(result.markouts, result.calibration))

    print()
    print(
        "NOTE: this replays the microprice baseline, which has no informational\n"
        "edge by construction. A near-zero or negative PnL here is the expected\n"
        "result, and it still gives you the real number that matters: the\n"
        "adverse selection above. Plug a genuine model in to test for edge."
    )
    return 0


def cmd_calibrate(args: argparse.Namespace, settings: Settings) -> int:
    from .simulation.markout import render_markout_report

    result = _load_and_replay(args, settings)
    if result is None:
        return 1
    if not result.fills:
        log.error(
            "No simulated fills in this recording, so adverse selection cannot "
            "be measured. Record for longer, or across more active markets."
        )
        return 1

    print(render_markout_report(result.markouts, result.calibration))
    print()
    cal = result.calibration
    if cal and cal.confident:
        print(f"Set in .env:  POLYBOT_ADVERSE_SELECTION={cal.suggested:.4f}")
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

    if args.sports:
        model = _build_sports_model(markets, settings)
        if model is None:
            return 1
        runner.model = model

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

    hlr = sub.add_parser("hl-research",
                         help="profile top Hyperliquid accounts (perps)")
    hlr.add_argument("--top", type=int, default=5)
    hlr.add_argument("--days", type=int, default=90, help="history window")
    hlr.add_argument("--max-fills", type=int, default=40_000)
    hlr.add_argument("--out", default="out")
    hlr.set_defaults(func=cmd_hl_research)

    sh = sub.add_parser(
        "shock",
        help="test whether news-driven price shocks drift or mean-revert",
    )
    sh.add_argument("--coins", default="BTC,ETH,SOL")
    sh.add_argument("--days", type=int, default=30)
    sh.add_argument("--interval", default="1m",
                    help="1m retains ~4d, 5m ~30d, 15m ~90d, 1h ~365d")
    sh.add_argument("--horizons", default="1,5,15,60,240",
                    help="forward horizons in bars")
    sh.add_argument("--sigma", type=float, default=4.0,
                    help="how many sigma counts as a shock")
    sh.add_argument("--cost", type=float, default=0.001,
                    help="round-trip cost as a fraction (0.001 = 0.10%%)")
    sh.set_defaults(func=cmd_shock)

    hq = sub.add_parser("hl-quote",
                        help="dry-run the maker strategy on live Hyperliquid books")
    hq.add_argument("--coins", default="", help="comma list; default = top universe")
    hq.add_argument("--limit", type=int, default=20)
    hq.add_argument("--address", default="", help="your address, for a real fee tier")
    hq.add_argument("--max-size", type=float, default=100.0)
    hq.set_defaults(func=cmd_hl_quote)

    hlp = sub.add_parser("hl-profile", help="profile one Hyperliquid address")
    hlp.add_argument("wallet")
    hlp.add_argument("--days", type=int, default=90)
    hlp.add_argument("--max-fills", type=int, default=40_000)
    hlp.set_defaults(func=cmd_hl_profile)

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

    rec = sub.add_parser("record", help="record books and trades for backtesting")
    rec.add_argument("--markets", type=int, default=20)
    rec.add_argument("--interval", type=float, default=2.0)
    rec.add_argument("--duration", type=float, default=None,
                     help="seconds to record (default: until interrupted)")
    rec.add_argument("--out", default="data", help="output directory")
    rec.add_argument("--min-liquidity", type=float, default=5_000.0)
    rec.add_argument("--min-volume", type=float, default=10_000.0)
    rec.add_argument("--odds", action="store_true",
                     help="also record sportsbook odds (needs POLYBOT_ODDS_API_KEY)")
    rec.set_defaults(func=cmd_record)

    bt = sub.add_parser("backtest", help="replay the strategy over a recording")
    bt.add_argument("--data", required=True, help="a recording session directory")
    bt.set_defaults(func=cmd_backtest)

    cal = sub.add_parser("calibrate",
                         help="measure adverse selection from a recording")
    cal.add_argument("--data", required=True, help="a recording session directory")
    cal.set_defaults(func=cmd_calibrate)

    run = sub.add_parser("run", help="run the quoting loop")
    run.add_argument("--dry-run", action="store_true", help="force dry-run mode")
    run.add_argument("--markets", type=int, default=15)
    run.add_argument("--interval", type=float, default=5.0)
    run.add_argument("--cycles", type=int, default=None, help="stop after N cycles")
    run.add_argument("--yes", action="store_true", help="skip the live confirmation")
    run.add_argument("--sports", action="store_true",
                     help="use the odds-based fair value model instead of microprice")
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
