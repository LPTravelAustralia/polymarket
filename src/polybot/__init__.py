"""polybot -- a maker-side Polymarket bot and a toolkit for profiling the
wallets that actually make money.

Start with `polybot economics --price 0.5` to see why the strategy is what it
is, then `polybot research --top 5` to see who is doing it.
"""

__version__ = "0.1.0"

from .config import Mode, Settings

__all__ = ["Mode", "Settings", "__version__"]
