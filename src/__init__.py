"""
Polymarket Trading Bot Package
A comprehensive trading bot for Polymarket with AI-powered predictions and fee collection.
"""

__version__ = "0.1.0"
__author__ = "Polymarket Trading Bot Team"

from src.core.client import PolymarketClient
from src.agents.base_agent import BaseAgent
from src.core.config import Config

__all__ = [
    "PolymarketClient",
    "BaseAgent",
    "Config",
]
