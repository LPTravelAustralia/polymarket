"""Configuration, loaded from environment with conservative defaults.

Defaults are deliberately timid. Every limit here exists because the
alternative is discovering the number empirically with real money.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional
    pass

POLYGON_CHAIN_ID = 137
CLOB_HOST = "https://clob.polymarket.com"


class Mode(str, Enum):
    DRY_RUN = "dry_run"   # compute quotes, send nothing
    PAPER = "paper"       # simulate fills against the live book
    LIVE = "live"         # real orders


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, "") or default)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, "") or default)
    except ValueError:
        return default


@dataclass
class RiskLimits:
    """Hard caps. The bot refuses to breach these regardless of signal."""

    max_position_usd_per_market: float = 250.0
    max_total_exposure_usd: float = 2_500.0
    max_open_orders: int = 60
    max_orders_per_minute: int = 30

    # Stop trading for the day after this much realised loss.
    daily_loss_limit_usd: float = 250.0

    # Refuse to quote a market resolving sooner than this. Late in a market's
    # life the fair-value model is worst and adverse selection is worst, which
    # is exactly the wrong combination.
    min_seconds_to_resolution: int = 3_600

    # Never quote more than this fraction of the visible book depth.
    max_book_share: float = 0.25

    @classmethod
    def from_env(cls) -> "RiskLimits":
        return cls(
            max_position_usd_per_market=_env_float("POLYBOT_MAX_POSITION_USD", 250.0),
            max_total_exposure_usd=_env_float("POLYBOT_MAX_EXPOSURE_USD", 2_500.0),
            max_open_orders=_env_int("POLYBOT_MAX_OPEN_ORDERS", 60),
            max_orders_per_minute=_env_int("POLYBOT_MAX_ORDERS_PER_MIN", 30),
            daily_loss_limit_usd=_env_float("POLYBOT_DAILY_LOSS_LIMIT", 250.0),
            min_seconds_to_resolution=_env_int("POLYBOT_MIN_SECONDS_TO_RESOLUTION", 3_600),
            max_book_share=_env_float("POLYBOT_MAX_BOOK_SHARE", 0.25),
        )


@dataclass
class MakerParams:
    """Quoting parameters for the systematic maker strategy."""

    # Minimum net edge per share required to post a quote, in probability
    # units. 0.005 = half a cent. Below ~0.003 you are quoting inside your own
    # model error and adverse selection eats the difference.
    min_edge_per_share: float = 0.005

    # Estimated adverse selection cost per maker fill. You get filled
    # preferentially when you are wrong; this is the haircut for that. Measure
    # it from your own fills (realised markout) and update it -- the default is
    # a placeholder, not a measurement.
    adverse_selection_per_share: float = 0.004

    # Half-width of the quoted band around fair value.
    base_half_spread: float = 0.010

    # Widen quotes proportionally to model uncertainty.
    uncertainty_multiplier: float = 1.5

    # Order size in shares.
    order_size_shares: float = 20.0

    # Skew quotes to mean-revert inventory. At full position limit, shift
    # quotes by this much to encourage flattening.
    inventory_skew_max: float = 0.015

    # Only quote inside this price band. Outside it the fee is cheap but the
    # payoff is highly asymmetric and model error dominates.
    #
    # These are PROBABILITY bounds and only make sense on a prediction
    # market. Set max_price to inf for an asset quoted in dollars.
    min_price: float = 0.05
    max_price: float = 0.95

    # When True, `base_half_spread`, `min_edge_per_share` and
    # `adverse_selection_per_share` are read as FRACTIONS OF PRICE rather
    # than absolute amounts.
    #
    # This exists because absolute thresholds are a prediction-market
    # assumption: on a 0-1 probability scale 0.010 means one cent and also
    # one percent, and those coincide. On a perp they do not -- 0.010 is
    # 1% of a $1 token and 0.00001% of BTC. The first live run on
    # Hyperliquid quoted DYDX 9% below the market because of exactly this.
    relative_thresholds: bool = False

    @classmethod
    def for_perps(cls, **overrides) -> "MakerParams":
        """Defaults sane for an asset quoted in dollars.

        Values are fractions of price: 10bp half-spread, 5bp minimum edge,
        8bp assumed adverse selection. The adverse-selection figure is still
        a placeholder and still needs measuring per venue.
        """
        base = dict(
            base_half_spread=0.0010,
            min_edge_per_share=0.0005,
            adverse_selection_per_share=0.0008,
            inventory_skew_max=0.0015,
            min_price=0.0,
            max_price=float("inf"),
            relative_thresholds=True,
            requote_threshold=0.0003,
        )
        base.update(overrides)
        return cls(**base)

    # Re-quote when fair value moves more than this.
    requote_threshold: float = 0.003

    @classmethod
    def from_env(cls) -> "MakerParams":
        return cls(
            min_edge_per_share=_env_float("POLYBOT_MIN_EDGE", 0.005),
            adverse_selection_per_share=_env_float("POLYBOT_ADVERSE_SELECTION", 0.004),
            base_half_spread=_env_float("POLYBOT_HALF_SPREAD", 0.010),
            order_size_shares=_env_float("POLYBOT_ORDER_SIZE", 20.0),
        )


@dataclass
class ArbParams:
    """Structural arbitrage gating."""

    # Minimum profit per share after fees, in probability units.
    min_profit_per_share: float = 0.004

    # Assume this much slippage per leg. Multi-leg arb that ignores the
    # possibility of one leg missing is not arbitrage, it is naked risk.
    slippage_per_leg: float = 0.002

    max_notional_usd: float = 500.0

    @classmethod
    def from_env(cls) -> "ArbParams":
        return cls(
            min_profit_per_share=_env_float("POLYBOT_ARB_MIN_PROFIT", 0.004),
            slippage_per_leg=_env_float("POLYBOT_ARB_SLIPPAGE", 0.002),
            max_notional_usd=_env_float("POLYBOT_ARB_MAX_NOTIONAL", 500.0),
        )


@dataclass
class Settings:
    mode: Mode = Mode.DRY_RUN
    private_key: str = ""
    funder_address: str = ""
    signature_type: int = 2
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    clob_host: str = CLOB_HOST
    chain_id: int = POLYGON_CHAIN_ID
    log_level: str = "INFO"

    risk: RiskLimits = field(default_factory=RiskLimits)
    maker: MakerParams = field(default_factory=MakerParams)
    arb: ArbParams = field(default_factory=ArbParams)

    @classmethod
    def from_env(cls) -> "Settings":
        raw_mode = _env("POLYBOT_MODE", "dry_run").lower()
        try:
            mode = Mode(raw_mode)
        except ValueError:
            logging.getLogger(__name__).warning(
                "Unknown POLYBOT_MODE=%r, defaulting to dry_run", raw_mode
            )
            mode = Mode.DRY_RUN

        return cls(
            mode=mode,
            private_key=_env("POLYBOT_PRIVATE_KEY"),
            funder_address=_env("POLYBOT_FUNDER_ADDRESS"),
            signature_type=_env_int("POLYBOT_SIGNATURE_TYPE", 2),
            api_key=_env("POLYBOT_API_KEY"),
            api_secret=_env("POLYBOT_API_SECRET"),
            api_passphrase=_env("POLYBOT_API_PASSPHRASE"),
            clob_host=_env("POLYBOT_CLOB_HOST", CLOB_HOST),
            chain_id=_env_int("POLYBOT_CHAIN_ID", POLYGON_CHAIN_ID),
            log_level=_env("POLYBOT_LOG_LEVEL", "INFO").upper(),
            risk=RiskLimits.from_env(),
            maker=MakerParams.from_env(),
            arb=ArbParams.from_env(),
        )

    def require_credentials(self) -> None:
        if not self.private_key:
            raise RuntimeError(
                "POLYBOT_PRIVATE_KEY is required for paper and live modes. "
                "Copy .env.example to .env and fill it in."
            )

    def setup_logging(self) -> None:
        logging.basicConfig(
            level=getattr(logging, self.log_level, logging.INFO),
            format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
