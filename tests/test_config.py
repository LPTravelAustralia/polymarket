"""
Basic tests for configuration
"""
import pytest
from src.core.config import Config


def test_config_defaults():
    """Test default configuration values"""
    config = Config()
    
    assert config.default_trade_size == 10.0
    assert config.max_position_size == 1000.0
    assert config.risk_percentage == 0.02
    assert config.min_liquidity == 1000.0
    assert config.fee_percentage == 0.01
    assert config.dry_run is True
    assert config.auto_trade is False


def test_config_override():
    """Test configuration override"""
    config = Config(
        default_trade_size=20.0,
        dry_run=False
    )
    
    assert config.default_trade_size == 20.0
    assert config.dry_run is False


def test_config_validation():
    """Test configuration validation"""
    config = Config()
    
    # Check types
    assert isinstance(config.default_trade_size, float)
    assert isinstance(config.max_position_size, float)
    assert isinstance(config.chain_id, int)
    assert isinstance(config.dry_run, bool)
