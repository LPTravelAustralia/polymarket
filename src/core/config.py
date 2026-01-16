"""
Configuration management for Polymarket Trading Bot
"""
import os
from typing import Optional
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the .env file path (project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Config(BaseSettings):
    """Configuration class for the Polymarket Trading Bot"""
    
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True
    )
    
    # Polymarket API Configuration
    polymarket_api_key: str = Field(default="")
    polymarket_secret: str = Field(default="")
    polymarket_passphrase: str = Field(default="")
    
    # Wallet Configuration
    wallet_private_key: str = Field(default="")
    wallet_address: str = Field(default="")
    
    # AI Configuration
    openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    
    # Trading Configuration
    default_trade_size: float = Field(default=10.0)
    max_position_size: float = Field(default=1000.0)
    risk_percentage: float = Field(default=0.02)
    min_liquidity: float = Field(default=1000.0)
    
    # Fee Configuration
    fee_percentage: float = Field(default=0.01)
    fee_wallet_address: str = Field(default="")
    
    # Network Configuration
    polygon_rpc_url: str = Field(default="https://polygon-rpc.com")
    chain_id: int = Field(default=137)
    
    # Bot Configuration
    bot_mode: str = Field(default="testnet")
    log_level: str = Field(default="INFO")
    dry_run: bool = Field(default=True)
    
    # Database Configuration
    database_url: str = Field(default="sqlite:///polymarket_bot.db")
    
    # Advanced Configuration
    use_ai_predictions: bool = Field(default=False)
    auto_trade: bool = Field(default=False)
    monitoring_interval: int = Field(default=60)
    max_concurrent_trades: int = Field(default=5)

    # AI Tuning
    ai_min_confidence: float = Field(default=0.8)
    ai_min_edge: float = Field(default=0.15)
    ai_max_spread_pct: float = Field(default=3.0)
    calibration_log_path: str = Field(default="calibration_logs/ai_calibration.csv")
    
    # News Monitoring Configuration
    newsapi_key: Optional[str] = Field(default=None)
    news_monitoring_interval: int = Field(default=300)  # 5 minutes
    news_min_impact_score: float = Field(default=0.55)  # Improved fallback scoring
    news_min_confidence: float = Field(default=0.50)  # Realistic for keyword-based scoring
    news_max_age_hours: int = Field(default=72)  # 72 hours (NewsAPI free tier has ~24h delay)
    news_use_twitter: bool = Field(default=False)
    
    # Twitter/X Configuration
    twitter_bearer_token: Optional[str] = Field(default=None)


def load_config() -> Config:
    """Load and return configuration"""
    return Config()
