"""
models/backtest.py
Pydantic request/response models for the backtest endpoint.
Matches the style of models/signal.py and models/mentor.py
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# ============================================================================
# REQUEST MODELS
# ============================================================================

class RunBacktestRequest(BaseModel):
    user_id: str
    symbol: str = Field(..., description="Currency pair e.g. EURUSD, GBPUSD")
    strategy: str = Field(..., description="moving_average_crossover | rsi | bollinger_bands | macd")
    start: str = Field(..., description="Start date YYYY-MM-DD")
    end: str = Field(..., description="End date YYYY-MM-DD")
    initial_capital: float = Field(default=10000.0, gt=0)
    strategy_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional strategy parameters e.g. {period: 14, oversold: 30}"
    )
    data_source: Optional[str] = Field(
        default="auto",
        description="auto | yfinance | alphavantage | csv"
    )
    save_to_db: bool = Field(
        default=True,
        description="Whether to save the result to Supabase"
    )


class DeleteBacktestRequest(BaseModel):
    user_id: str


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class BacktestMetricsResponse(BaseModel):
    """Mirrors the dict returned by MetricsCalculator.calculate()"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    win_rate_pct: float
    total_pnl: float
    gross_profit: float
    gross_loss: float
    avg_win: float
    avg_loss: float
    avg_risk_reward: float
    profit_factor: float
    initial_capital: float
    final_capital: float
    total_return_pct: float
    annual_return_pct: float
    volatility_annual_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float


class RunBacktestResponse(BaseModel):
    """Returned after running a backtest."""
    backtest_id: Optional[str] = None         # set if saved to DB
    strategy_name: str
    symbol: str
    start: str
    end: str
    data_source: str
    initial_capital: float
    metrics: BacktestMetricsResponse
    ai_explanation: Optional[str] = None      # LLM explanation if requested
    created_at: Optional[datetime] = None


class SavedBacktestResponse(BaseModel):
    """Returned when listing saved backtests."""
    id: str
    strategy_name: str
    symbol: str
    start: str
    end: str
    initial_capital: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_trades: int
    created_at: datetime


class BacktestDetailResponse(BaseModel):
    """Full detail of a saved backtest."""
    id: str
    user_id: str
    strategy_name: str
    strategy_config: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    created_at: datetime


class DeleteBacktestResponse(BaseModel):
    message: str
    backtest_id: str

class BacktestUpdateRequest(BaseModel):
    is_saved: Optional[bool] = None
    user_notes: Optional[str] = None

class BacktestFilterParams(BaseModel):
    pair: Optional[str] = None
    limit: int = 20
    offset: int = 0


# Aliases to match route imports
BacktestRunRequest = RunBacktestRequest
BacktestResponse = RunBacktestResponse
BacktestListResponse = SavedBacktestResponse  # or create a proper list wrapper
BacktestTradeListResponse = SavedBacktestResponse  # adjust as needed


# class BacktestStatisticsResponse(BaseModel):
#     """Summary statistics across all of a user's backtests."""
#     total_backtests: int
#     best_strategy: Optional[str] = None
#     best_return_pct: Optional[float] = None
#     avg_sharpe_ratio: Optional[float] = None
#     most_tested_symbol: Optional[str] = None