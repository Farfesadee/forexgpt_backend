"""
Realistic Trading Cost Model
Implements spreads, slippage, commissions, and financing costs.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class AssetClass(Enum):
    """Asset class types with different cost structures."""
    FOREX = "forex"
    STOCKS = "stocks"
    CRYPTO = "crypto"
    FUTURES = "futures"
    OPTIONS = "options"


@dataclass
class TradingCosts:
    """
    Complete trading cost breakdown for a single trade.
    All costs expressed in currency units or basis points.
    """
    spread_cost: float = 0.0          # Bid-ask spread cost
    slippage_cost: float = 0.0        # Market impact / slippage
    commission: float = 0.0            # Broker commission
    financing_cost: float = 0.0        # Overnight financing / swap
    exchange_fees: float = 0.0         # Exchange/platform fees
    
    @property
    def total_cost(self) -> float:
        """Total cost of the trade."""
        return (self.spread_cost + self.slippage_cost + self.commission + 
                self.financing_cost + self.exchange_fees)
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "spread_cost": self.spread_cost,
            "slippage_cost": self.slippage_cost,
            "commission": self.commission,
            "financing_cost": self.financing_cost,
            "exchange_fees": self.exchange_fees,
            "total_cost": self.total_cost
        }


class CostModel:
    """
    Realistic cost model for different asset classes and market conditions.
    
    Costs vary based on:
    - Asset class
    - Market conditions (volatility, liquidity)
    - Trade size
    - Time of day
    - Account type
    """
    
    def __init__(
        self,
        asset_class: AssetClass = AssetClass.FOREX,
        spread_bps: float = 2.0,           # Spread in basis points
        commission_rate: float = 0.0,      # Commission per unit
        slippage_model: str = "fixed",     # "fixed", "volume", "volatility"
        base_slippage_bps: float = 0.5,    # Base slippage in bps
        financing_rate_annual: float = 0.05,  # Annual financing rate (5%)
        exchange_fee_bps: float = 0.0      # Exchange fees in bps
    ):
        """
        Initialize cost model.
        
        Args:
            asset_class: Type of asset being traded
            spread_bps: Average bid-ask spread in basis points
            commission_rate: Commission per trade (flat or per unit)
            slippage_model: How to calculate slippage
            base_slippage_bps: Base slippage in basis points
            financing_rate_annual: Annual financing rate
            exchange_fee_bps: Exchange fees in basis points
        """
        self.asset_class = asset_class
        self.spread_bps = spread_bps
        self.commission_rate = commission_rate
        self.slippage_model = slippage_model
        self.base_slippage_bps = base_slippage_bps
        self.financing_rate_annual = financing_rate_annual
        self.exchange_fee_bps = exchange_fee_bps
    
    def calculate_spread_cost(
        self,
        price: float,
        quantity: float,
        market_conditions: Optional[Dict] = None
    ) -> float:
        """
        Calculate bid-ask spread cost.
        
        Args:
            price: Entry/exit price
            quantity: Trade quantity
            market_conditions: Dict with volatility, liquidity, etc.
        
        Returns:
            Spread cost in currency units
        """
        # Base spread
        spread_cost = (self.spread_bps / 10000) * price * abs(quantity)
        
        # Adjust for market conditions
        if market_conditions:
            volatility = market_conditions.get("volatility", 1.0)
            liquidity = market_conditions.get("liquidity", 1.0)
            
            # Higher volatility = wider spreads
            spread_cost *= volatility
            
            # Lower liquidity = wider spreads
            spread_cost *= (2.0 - liquidity)  # liquidity between 0-1
        
        return spread_cost
    
    def calculate_slippage(
        self,
        price: float,
        quantity: float,
        market_conditions: Optional[Dict] = None
    ) -> float:
        """
        Calculate slippage cost based on model.
        
        Args:
            price: Expected price
            quantity: Trade quantity
            market_conditions: Market state
        
        Returns:
            Slippage cost in currency units
        """
        if self.slippage_model == "fixed":
            # Fixed slippage regardless of conditions
            return (self.base_slippage_bps / 10000) * price * abs(quantity)
        
        elif self.slippage_model == "volume":
            # Slippage increases with trade size
            # Larger trades = more market impact
            volume_factor = market_conditions.get("volume_ratio", 1.0) if market_conditions else 1.0
            
            # If our trade is 1% of average volume, impact is higher
            slippage_multiplier = 1.0 + (1.0 / max(volume_factor, 0.1))
            
            return (self.base_slippage_bps / 10000) * price * abs(quantity) * slippage_multiplier
        
        elif self.slippage_model == "volatility":
            # Slippage increases with volatility
            volatility = market_conditions.get("volatility", 1.0) if market_conditions else 1.0
            
            return (self.base_slippage_bps / 10000) * price * abs(quantity) * volatility
        
        else:
            return 0.0
    
    def calculate_commission(
        self,
        price: float,
        quantity: float,
        is_entry: bool = True
    ) -> float:
        """
        Calculate broker commission.
        
        Args:
            price: Trade price
            quantity: Trade quantity
            is_entry: Whether this is entry or exit
        
        Returns:
            Commission in currency units
        """
        if self.asset_class == AssetClass.FOREX:
            # Forex: usually in spread, but some brokers charge commission
            return self.commission_rate * abs(quantity)
        
        elif self.asset_class == AssetClass.STOCKS:
            # Stocks: per-share or percentage-based
            if self.commission_rate < 0.01:  # Percentage
                return (self.commission_rate / 100) * price * abs(quantity)
            else:  # Per-share
                return self.commission_rate * abs(quantity)
        
        elif self.asset_class == AssetClass.CRYPTO:
            # Crypto: maker/taker fees
            # Taker (market orders) typically 0.1-0.3%
            return (self.commission_rate / 100) * price * abs(quantity)
        
        elif self.asset_class == AssetClass.FUTURES:
            # Futures: per contract
            return self.commission_rate * abs(quantity)
        
        else:
            return 0.0
    
    def calculate_financing_cost(
        self,
        price: float,
        quantity: float,
        holding_days: int,
        is_long: bool = True
    ) -> float:
        """
        Calculate overnight financing / swap cost.
        
        Args:
            price: Position price
            quantity: Position size
            holding_days: Number of days position was held
            is_long: Whether position is long or short
        
        Returns:
            Financing cost in currency units
        """
        if holding_days == 0:
            return 0.0
        
        # Position value
        position_value = price * abs(quantity)
        
        # Daily financing rate
        daily_rate = self.financing_rate_annual / 365
        
        # Long positions pay financing, short positions may earn or pay
        if is_long:
            financing = position_value * daily_rate * holding_days
        else:
            # Short positions: depends on asset class
            if self.asset_class == AssetClass.FOREX:
                # Forex: depends on interest rate differential
                # Simplified: assume symmetric rate
                financing = -position_value * daily_rate * holding_days
            else:
                # Stocks/Crypto: short positions pay higher rate
                financing = position_value * daily_rate * 1.5 * holding_days
        
        return financing
    
    def calculate_exchange_fees(
        self,
        price: float,
        quantity: float
    ) -> float:
        """
        Calculate exchange/platform fees.
        
        Args:
            price: Trade price
            quantity: Trade quantity
        
        Returns:
            Exchange fee in currency units
        """
        return (self.exchange_fee_bps / 10000) * price * abs(quantity)
    
    def calculate_total_costs(
        self,
        entry_price: float,
        exit_price: float,
        quantity: float,
        holding_days: int = 0,
        is_long: bool = True,
        entry_conditions: Optional[Dict] = None,
        exit_conditions: Optional[Dict] = None
    ) -> TradingCosts:
        """
        Calculate all costs for a complete trade (entry + exit).
        
        Args:
            entry_price: Entry price
            exit_price: Exit price
            quantity: Trade quantity
            holding_days: Days held
            is_long: Long or short position
            entry_conditions: Market conditions at entry
            exit_conditions: Market conditions at exit
        
        Returns:
            TradingCosts object with complete breakdown
        """
        # Entry costs
        entry_spread = self.calculate_spread_cost(entry_price, quantity, entry_conditions)
        entry_slippage = self.calculate_slippage(entry_price, quantity, entry_conditions)
        entry_commission = self.calculate_commission(entry_price, quantity, is_entry=True)
        entry_exchange = self.calculate_exchange_fees(entry_price, quantity)
        
        # Exit costs
        exit_spread = self.calculate_spread_cost(exit_price, quantity, exit_conditions)
        exit_slippage = self.calculate_slippage(exit_price, quantity, exit_conditions)
        exit_commission = self.calculate_commission(exit_price, quantity, is_entry=False)
        exit_exchange = self.calculate_exchange_fees(exit_price, quantity)
        
        # Financing costs
        financing = self.calculate_financing_cost(entry_price, quantity, holding_days, is_long)
        
        return TradingCosts(
            spread_cost=entry_spread + exit_spread,
            slippage_cost=entry_slippage + exit_slippage,
            commission=entry_commission + exit_commission,
            financing_cost=financing,
            exchange_fees=entry_exchange + exit_exchange
        )


# Preset cost models for common scenarios
COST_PRESETS = {
    "forex_retail": CostModel(
        asset_class=AssetClass.FOREX,
        spread_bps=2.0,
        commission_rate=0.0,
        base_slippage_bps=0.5,
        financing_rate_annual=0.05
    ),
    
    "forex_institutional": CostModel(
        asset_class=AssetClass.FOREX,
        spread_bps=0.5,
        commission_rate=0.0,
        base_slippage_bps=0.2,
        financing_rate_annual=0.03
    ),
    
    "stocks_commission_free": CostModel(
        asset_class=AssetClass.STOCKS,
        spread_bps=5.0,
        commission_rate=0.0,
        base_slippage_bps=1.0,
        financing_rate_annual=0.08
    ),
    
    "stocks_traditional": CostModel(
        asset_class=AssetClass.STOCKS,
        spread_bps=5.0,
        commission_rate=0.005,  # $0.005 per share
        base_slippage_bps=1.0,
        financing_rate_annual=0.08
    ),
    
    "crypto_exchange": CostModel(
        asset_class=AssetClass.CRYPTO,
        spread_bps=10.0,
        commission_rate=0.1,  # 0.1% taker fee
        base_slippage_bps=5.0,
        financing_rate_annual=0.0,
        slippage_model="volatility"
    ),
    
    "futures_cme": CostModel(
        asset_class=AssetClass.FUTURES,
        spread_bps=1.0,
        commission_rate=2.50,  # $2.50 per contract
        base_slippage_bps=0.5,
        financing_rate_annual=0.0
    )
}


def get_cost_model(preset: str = "forex_retail") -> CostModel:
    """Get a preset cost model."""
    if preset in COST_PRESETS:
        return COST_PRESETS[preset]
    else:
        raise ValueError(f"Unknown preset: {preset}. Available: {list(COST_PRESETS.keys())}")
