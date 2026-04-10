"""
Backtesting Engine
Core engine for strategy backtesting with realistic cost modeling.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from enum import Enum

from backtesting.costs.cost_model import CostModel, TradingCosts

class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Trade:
    """Represents a complete trade (entry + exit)."""
    entry_date: datetime
    entry_price: float
    exit_date: datetime
    exit_price: float
    quantity: float
    side: str  # "long" or "short"
    
    # Costs
    costs: TradingCosts
    
    # P&L
    gross_pnl: float
    net_pnl: float
    
    # Metrics
    holding_days: int
    return_pct: float
    
    # ── NEW: why the entry signal fired (parameterised strategies only) ──
    # e.g. "RSI = 28.4 < 30 (oversold)" or "MA50 crossed above MA200"
    # None for custom code strategies — user knows their own logic
    signal_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_date":    self.entry_date,
            "entry_price":   self.entry_price,
            "exit_date":     self.exit_date,
            "exit_price":    self.exit_price,
            "quantity":      self.quantity,
            "side":          self.side,
            "holding_days":  self.holding_days,
            "gross_pnl":     self.gross_pnl,
            "net_pnl":       self.net_pnl,
            "return_pct":    self.return_pct,
            "signal_reason": self.signal_reason,
            **self.costs.to_dict()
        }


@dataclass
class Position:
    """Represents an open position."""
    entry_date: datetime
    entry_price: float
    quantity: float
    side: str
    
    # ── NEW: reason the entry signal fired, carried through to Trade ────
    signal_reason: Optional[str] = None
    
    def mark_to_market(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.side == "long":
            return (current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - current_price) * self.quantity


class BacktestEngine:
    """
    Backtesting engine with realistic cost modeling.
    
    Features:
    - Realistic spread, slippage, commission costs
    - Position tracking
    - Trade logging
    - Performance metrics
    - Signal reason tracking
    """
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        cost_model: Optional[CostModel] = None,
        position_size_pct: float = 0.1,  # Use 10% of capital per trade
        max_positions: int = 1,  # Number of concurrent positions
        allow_shorting: bool = True
    ):
        """
        Initialize backtest engine.
        
        Args:
            initial_capital:   Starting capital
            cost_model: Cost   model to use
            position_size_pct: Percentage of capital to risk per trade
            max_positions:     Maximum concurrent positions
            allow_shorting:    Whether short positions are allowed
        """
        self.initial_capital =   initial_capital
        self.capital =           initial_capital
        self.cost_model =        cost_model or CostModel()
        self.position_size_pct = position_size_pct
        self.max_positions =     max_positions
        self.allow_shorting =    allow_shorting
        
        # State
        self.positions:     List[Position] = []
        self.closed_trades: List[Trade] = []
        self.equity_curve:  List[Dict] = []
        
        # Current state
        self.current_date:  Optional[datetime] = None
        self.current_price: float = 0.0
    
    def can_open_position(self) -> bool:
        """Check if we can open a new position."""
        return len(self.positions) < self.max_positions
    
    def get_position_size(self, price: float) -> float:
        """Calculate position size based on capital."""
        # Use percentage of available capital
        position_value = self.capital * self.position_size_pct
        quantity       = position_value / price
        return quantity
    
    def open_position(
        self,
        date: datetime,
        price: float,
        side: str,
        quantity: Optional[float] = None,
        market_conditions: Optional[Dict] = None,
        signal_reason: Optional[str] = None,
    ) -> bool:
        """
        Open a new position.
        
        Args:
            date: Entry date
            price: Entry price
            side: "long" or "short"
            quantity: Position size (if None, auto-calculated)
            market_conditions: Market state for cost calculation
            signal_reason:     Human-readable reason the signal fired
                               e.g. "RSI = 28.4 < 30 (oversold)"
        
        Returns:
            True if position opened successfully
        """
        if not self.can_open_position():
            return False
        
        if side == "short" and not self.allow_shorting:
            return False
        
        # Calculate position size
        if quantity is None:
            quantity = self.get_position_size(price)
        
        # Create position
        position = Position(
            entry_date=date,
            entry_price=price,
            quantity=quantity,
            side=side,
            signal_reason=signal_reason,
        )
        
        self.positions.append(position)
        self.current_date = date
        self.current_price = price
        
        return True
    
    def close_position(
        self,
        position: Position,
        date: datetime,
        price: float,
        market_conditions: Optional[Dict] = None
    ) -> Trade:
        """
        Close an existing position.
        
        Args:
            position:          Position to close
            date:              Exit date
            price:             Exit price
            market_conditions: Market state for cost calculation
        
        Returns:
            Trade object with complete info
        """
        # Calculate holding period
        holding_days = (date - position.entry_date).days
        
        # Calculate gross P&L
        if position.side == "long":
            gross_pnl = (price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - price) * position.quantity
        
        # Calculate costs
        costs = self.cost_model.calculate_total_costs(
            entry_price=position.entry_price,
            exit_price=price,
            quantity=position.quantity,
            holding_days=holding_days,
            is_long=(position.side == "long"),
            entry_conditions=market_conditions,
            exit_conditions=market_conditions
        )
        
        # Net P&L after costs
        net_pnl = gross_pnl - costs.total_cost
        
        # Return percentage
        position_value = position.entry_price * position.quantity
        return_pct = (net_pnl / position_value) * 100
        
        # Create trade record
        trade = Trade(
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            exit_date=date,
            exit_price=price,
            quantity=position.quantity,
            side=position.side,
            costs=costs,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            holding_days=holding_days,
            return_pct=return_pct,
            signal_reason=position.signal_reason,
        )
        
        # Update capital
        self.capital += net_pnl
        
        # Record trade
        self.closed_trades.append(trade)
        
        # Remove position
        self.positions.remove(position)
        
        self.current_date = date
        self.current_price = price
        
        return trade
    
    def close_all_positions(
        self,
        date: datetime,
        price: float,
        market_conditions: Optional[Dict] = None
    ):
        """Close all open positions."""
        for position in self.positions.copy():
            self.close_position(position, date, price, market_conditions)
    
    def update_equity(self, date: datetime, price: float, ohlc: Optional[Dict] = None):
        """Update equity curve with current mark-to-market and OHLC data."""
        # Calculate unrealized P&L
        unrealized_pnl = sum(
            pos.mark_to_market(price) for pos in self.positions
        )
        
        # Total equity
        total_equity = self.capital + unrealized_pnl
        
        # Record
        record = {
            "date":           date,
            "price":          price,
            "capital":        self.capital,
            "unrealized_pnl": unrealized_pnl,
            "total_equity":   total_equity,
            "num_positions":  len(self.positions)
        }
        
        if ohlc:
            record.update({
                "open": ohlc.get("open"),
                "high": ohlc.get("high"),
                "low": ohlc.get("low"),
                "close": ohlc.get("close"),
            })
            
        self.equity_curve.append(record)
    
    def run_backtest(
        self,
        data: pd.DataFrame,
        strategy: Callable,
        price_col: str = "close",
        date_col: str = "date"
    ) -> Dict[str, Any]:
        """
        Run backtest on historical data.
        
        Args:
            data:      DataFrame with price data
            strategy:  Strategy function — may return:
                         - a plain string: "buy" | "sell" | "short" | "cover" | None
                         - a tuple:        ("buy", "RSI = 28.4 < 30 (oversold)")
                       Both forms are handled transparently.
            price_col: Column name for price
            date_col:  Column name for date
        
        Returns:
            Backtest results dictionary
        """
        for idx, row in data.iterrows():
            date =  row[date_col]
            price = row[price_col]
            
            # Get market conditions
            market_conditions = {
                "volatility":   row.get("volatility", 1.0),
                "volume_ratio": row.get("volume_ratio", 1.0),
                "liquidity":    row.get("liquidity", 1.0)
            }
            
            # Get strategy signal
            raw_result = strategy(data.iloc[:idx + 1])
            if isinstance(raw_result, tuple):
                signal, signal_reason = raw_result
            else:
                signal        = raw_result
                signal_reason = None
            
            
            # Process signal
            if signal == "buy" and self.can_open_position():
                self.open_position(date, price, "long", market_conditions=market_conditions, signal_reason=signal_reason,)
            
            elif signal == "sell" and len(self.positions) > 0:
                # Close long positions
                for pos in self.positions.copy():
                    if pos.side == "long":
                        self.close_position(pos, date, price, market_conditions)
            
            elif signal == "short" and self.can_open_position() and self.allow_shorting:
                self.open_position(date, price, "short", market_conditions=market_conditions, signal_reason=signal_reason,)
            
            elif signal == "cover" and len(self.positions) > 0:
                # Close short positions
                for pos in self.positions.copy():
                    if pos.side == "short":
                        self.close_position(pos, date, price, market_conditions)
            
            # Update equity curve
            self.update_equity(date, price, ohlc=row.to_dict())
        
        # Close any remaining positions
        if len(self.positions) > 0:
            last_date =  data[date_col].iloc[-1]
            last_price = data[price_col].iloc[-1]
            self.close_all_positions(last_date, last_price)
        
        return self.get_results()
    
    def get_results(self) -> Dict[str, Any]:
        """Get backtest results."""
        return {
            "initial_capital": self.initial_capital,
            "final_capital":   self.capital,
            "total_return":    ((self.capital - self.initial_capital) / self.initial_capital) * 100,
            "num_trades":      len(self.closed_trades),
            "trades":          [t.to_dict() for t in self.closed_trades],
            "equity_curve":    self.equity_curve
        }
    
    def reset(self):
        """Reset engine to initial state."""
        self.capital       = self.initial_capital
        self.positions     = []
        self.closed_trades = []
        self.equity_curve  = []
        self.current_date  = None
        self.current_price = 0.0
