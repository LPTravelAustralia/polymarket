"""Venue adapters.

The research and simulation code is venue-agnostic; this package holds the
parts that aren't. Adding a venue means implementing an adapter here, not
touching the analysis.
"""

from .hl_profiler import (
    HLProfile,
    HyperliquidProfiler,
    render_hl_profile,
    render_hl_report,
)
from .hyperliquid import (
    HyperliquidAPI,
    HyperliquidStats,
    summarise_fills,
    to_common_fills,
)

__all__ = [
    "HLProfile",
    "HyperliquidAPI",
    "HyperliquidProfiler",
    "HyperliquidStats",
    "render_hl_profile",
    "render_hl_report",
    "summarise_fills",
    "to_common_fills",
]
