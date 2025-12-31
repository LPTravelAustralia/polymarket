"""
Configuration management for Polymarket Trading Bot
"""
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Configuration class for the Polymarket Trading Bot"""
    
    # Polymarket API Configuration
    polymarket_api_key: str = Field(default="", env="POLYMARKET_API_KEY")
    polymarket_secret: str = Field(default="", env="POLYMARKET_SECRET")
    polymarket_passphrase: str = Field(default="", env="POLYMARKET_PASSPHRASE")
    
    # Wallet Configuration
    wallet_private_key: str = Field(default="", env="WALLET_PRIVATE_KEY")
    wallet_address: str = Field(default="", env="WALLET_ADDRESS")
    
    # AI Configuration
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    
    # Trading Configuration
    default_trade_size: float = Field(default=10.0, env="DEFAULT_TRADE_SIZE")
    max_position_size: float = Field(default=1000.0, env="MAX_POSITION_SIZE")
    risk_percentage: float = Field(default=0.02, env="RISK_PERCENTAGE")
    min_liquidity: float = Field(default=1000.0, env="MIN_LIQUIDITY")
    
    # Fee Configuration
    fee_percentage: float = Field(default=0.01, env="FEE_PERCENTAGE")
    fee_wallet_address: str = Field(default="", env="FEE_WALLET_ADDRESS")
    
    # Network Configuration
    polygon_rpc_url: str = Field(default="https://polygon-rpc.com", env="POLYGON_RPC_URL")
    chain_id: int = Field(default=137, env="CHAIN_ID")
    
    # Bot Configuration
    bot_mode: str = Field(default="testnet", env="BOT_MODE")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    dry_run: bool = Field(default=True, env="DRY_RUN")
    
    # Database Configuration
    database_url: str = Field(default="sqlite:///polymarket_bot.db", env="DATABASE_URL")
    
    # Advanced Configuration
    use_ai_predictions: bool = Field(default=False, env="USE_AI_PREDICTIONS")
    auto_trade: bool = Field(default=False, env="AUTO_TRADE")
    monitoring_interval: int = Field(default=60, env="MONITORING_INTERVAL")
    max_concurrent_trades: int = Field(default=5, env="MAX_CONCURRENT_TRADES")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_config() -> Config:
    """Load and return configuration"""
    return Config()
