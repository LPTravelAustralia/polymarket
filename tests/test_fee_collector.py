"""
Tests for fee collector
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.core.fee_collector import FeeCollector
from src.core.config import Config


@pytest.fixture
def fee_collector():
    """Create fee collector for testing with mocked Web3"""
    config = Config(fee_percentage=0.02)
    
    with patch('src.core.fee_collector.Web3') as mock_web3:
        # Mock the Web3 instance and its methods
        mock_w3_instance = MagicMock()
        mock_web3.return_value = mock_w3_instance
        mock_web3.HTTPProvider = Mock()
        
        # Mock get_block to return a fake timestamp
        mock_w3_instance.eth.get_block.return_value = {'timestamp': 1234567890}
        
        collector = FeeCollector(config)
        # Keep the mock active for the tests
        collector.w3 = mock_w3_instance
        yield collector


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
