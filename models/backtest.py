"""
models/backtest.py
Pydantic request/response models for the backtest endpoints.
Field names match the backtests table schema in database.py.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# ============================================================================
# REQUEST MODELS
# ============================================================================

class RunBacktestRequest(BaseModel):
    user_id:           str
    pair:              str   = Field(..., description="e.g. EURUSD, GBPUSD")
    strategy_name:     str   = Field(..., description="rsi | moving_average_crossover | bollinger_bands | macd")
    start_date:        str   = Field(..., description="YYYY-MM-DD")
    end_date:          str   = Field(..., description="YYYY-MM-DD")
    strategy_id:       Optional[str]   = Field(default=None, description="FK to strategies table")
    timeframe:         str   = Field(default="1d", description="1d | 1wk")
    initial_capital:   float = Field(default=10000.0, gt=0)
    strategy_params:   Optional[Dict[str, Any]] = Field(
        default=None,
        description="e.g. {period: 14, oversold: 30, overbought: 70} for RSI"
    )
    cost_preset:       str   = Field(
        default="forex_retail",
        description="forex_retail | forex_institutional | stocks_commission_free | crypto_exchange"
    )
    position_size_pct: float = Field(default=0.1, gt=0, le=1.0)
    data_source:       str   = Field(default="auto", description="auto | yfinance | alphavantage | csv")


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class BacktestMetricsResponse(BaseModel):
    """Mirrors PerformanceMetrics.calculate_all_metrics() output exactly."""
    total_return_pct:       float
    cagr_pct:               float
    initial_capital:        float
    final_capital:          float
    total_trades:           int
    winning_trades:         int
    losing_trades:          int
    win_rate:               float
    win_rate_pct:           float
    gross_profit:           float
    gross_loss:             float
    profit_factor:          float
    avg_win:                float
    avg_loss:               float
    avg_risk_reward:        float
    avg_holding_days:       float
    total_pnl:              float
    max_drawdown_pct:       float
    avg_drawdown_pct:       float
    volatility_annual_pct:  float
    sharpe_ratio:           float
    sortino_ratio:          float
    calmar_ratio:           float
    total_costs:            float
    spread_costs:           float
    slippage_costs:         float
    commission_costs:       float
    financing_costs:        float
    exchange_fee_costs:     float
    costs_pct_of_gross_pnl: float


class RunBacktestResponse(BaseModel):
    """
    Returned after POST /backtest/run.
    Matches the completed backtests row from BacktestsRepo.get()
    """
    id:               str
    user_id:          str
    strategy_id:      Optional[str]
    pair:             str
    start_date:       str
    end_date:         str
    timeframe:        str
    initial_capital:  float
    strategy_name:    str
    status:           str                    # "completed"
    metrics:          Optional[Dict[str, Any]]
    # Denormalized by DB trigger sync_backtest_on_complete:
    total_return_pct: Optional[float]
    sharpe_ratio:     Optional[float]
    max_drawdown_pct: Optional[float]
    win_rate_pct:     Optional[float]
    total_trades:     Optional[int]
    created_at:       datetime


class SavedBacktestResponse(BaseModel):
    """Returned in list view — GET /backtest/user/{user_id}"""
    id:               str
    strategy_id:      Optional[str]
    pair:             str
    start_date:       str
    end_date:         str
    timeframe:        str
    initial_capital:  float
    status:           str
    total_return_pct: Optional[float]
    sharpe_ratio:     Optional[float]
    max_drawdown_pct: Optional[float]
    win_rate_pct:     Optional[float]
    total_trades:     Optional[int]
    is_saved:         Optional[bool]
    created_at:       datetime


class BacktestDetailResponse(BaseModel):
    """Full detail — GET /backtest/user/{user_id}/{backtest_id}"""
    id:                     str
    user_id:                str
    strategy_id:            Optional[str]
    pair:                   str
    start_date:             str
    end_date:               str
    timeframe:              str
    initial_capital:        float
    strategy_name:          str
    status:                 str
    metrics:                Optional[Dict[str, Any]]
    equity_curve:           Optional[List[Dict]]
    total_return_pct:       Optional[float]
    sharpe_ratio:           Optional[float]
    max_drawdown_pct:       Optional[float]
    win_rate_pct:           Optional[float]
    total_trades:           Optional[int]
    is_saved:               Optional[bool]
    created_at:             datetime


class DeleteBacktestResponse(BaseModel):
    message:     str
    backtest_id: str
