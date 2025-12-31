"""
Tests for fee collector
"""
import pytest
from src.core.fee_collector import FeeCollector
from src.core.config import Config


@pytest.fixture
def fee_collector():
    """Create fee collector for testing"""
    config = Config(fee_percentage=0.02)
    return FeeCollector(config)


def test_calculate_fee_positive_profit(fee_collector):
    """Test fee calculation on positive profit"""
    profit = 100.0
    fee = fee_collector.calculate_fee(profit)
    
    assert fee == 2.0  # 2% of 100


def test_calculate_fee_zero_profit(fee_collector):
    """Test fee calculation on zero profit"""
    profit = 0.0
    fee = fee_collector.calculate_fee(profit)
    
    assert fee == 0.0


def test_calculate_fee_negative_profit(fee_collector):
    """Test fee calculation on negative profit (loss)"""
    profit = -50.0
    fee = fee_collector.calculate_fee(profit)
    
    assert fee == 0.0  # No fee on losses


def test_collect_fee(fee_collector):
    """Test fee collection"""
    record = fee_collector.collect_fee(
        from_address="0xabc123",
        amount=2.0,
        transaction_hash="0xdef456"
    )
    
    assert record["amount"] == 2.0
    assert record["from_address"] == "0xabc123"
    assert record["transaction_hash"] == "0xdef456"
    assert fee_collector.get_total_fees() == 2.0


def test_fee_history(fee_collector):
    """Test fee history tracking"""
    fee_collector.collect_fee("0xabc123", 2.0)
    fee_collector.collect_fee("0xdef456", 3.0)
    
    history = fee_collector.get_fee_history()
    
    assert len(history) == 2
    assert fee_collector.get_total_fees() == 5.0
