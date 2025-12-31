"""
Fee collection mechanism for the trading bot
"""
import logging
from typing import Optional, Dict, Any
from decimal import Decimal
from web3 import Web3
from eth_account import Account

from src.core.config import Config

logger = logging.getLogger(__name__)


class FeeCollector:
    """
    Handle fee collection for bot usage
    """
    
    def __init__(self, config: Config):
        """
        Initialize fee collector
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.polygon_rpc_url))
        self.total_fees_collected = Decimal(0)
        self.fee_transactions = []
    
    def calculate_fee(self, profit_amount: float) -> float:
        """
        Calculate fee based on profit
        
        Args:
            profit_amount: Profit amount in USDC
            
        Returns:
            Fee amount to collect
        """
        if profit_amount <= 0:
            return 0.0
        
        fee = profit_amount * self.config.fee_percentage
        logger.info(f"Calculated fee: {fee} USDC ({self.config.fee_percentage * 100}% of {profit_amount})")
        return fee
    
    def collect_fee(
        self,
        from_address: str,
        amount: float,
        transaction_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record fee collection
        
        Args:
            from_address: Address fees are collected from
            amount: Fee amount in USDC
            transaction_hash: Associated transaction hash
            
        Returns:
            Fee collection record
        """
        fee_record = {
            "from_address": from_address,
            "amount": amount,
            "fee_wallet": self.config.fee_wallet_address,
            "transaction_hash": transaction_hash,
            "timestamp": self.w3.eth.get_block('latest')['timestamp']
        }
        
        self.fee_transactions.append(fee_record)
        self.total_fees_collected += Decimal(str(amount))
        
        logger.info(f"Fee collected: {amount} USDC from {from_address}")
        return fee_record
    
    def get_total_fees(self) -> float:
        """
        Get total fees collected
        
        Returns:
            Total fees in USDC
        """
        return float(self.total_fees_collected)
    
    def get_fee_history(self) -> list:
        """
        Get history of fee collections
        
        Returns:
            List of fee collection records
        """
        return self.fee_transactions
    
    def transfer_fees_to_wallet(self) -> Optional[str]:
        """
        Transfer collected fees to fee wallet
        (Placeholder - actual implementation would use USDC contract)
        
        Returns:
            Transaction hash or None
        """
        if self.config.dry_run:
            logger.info(f"DRY RUN: Would transfer {self.total_fees_collected} USDC to {self.config.fee_wallet_address}")
            return "dry_run_tx_hash"
        
        # TODO: Implement actual USDC transfer using Web3
        logger.warning("Fee transfer not implemented - requires USDC contract integration")
        return None
