"""
Configuration management for Polymarket Trading Bot
"""
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Configuration class for the Polymarket Trading Bot"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
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


def load_config() -> Config:
    """Load and return configuration"""
    return Config()
