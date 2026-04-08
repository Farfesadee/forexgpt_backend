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
    strategy_name:     str   = Field(..., description="rsi | sma | moving_average_crossover | bollinger | bollinger_bands | macd")
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
    
    
# ============================================================================
# CUSTOM STRATEGY — REQUEST / RESPONSE MODELS          (NEW)
# ============================================================================

class RunCustomBacktestRequest(BaseModel):
    """
    Request model for POST /backtest/run/custom.

    Differences from RunBacktestRequest:
    - custom_code replaces strategy_name + strategy_params
    - cost_preset removed (custom path has no cost model)
    - data_source defaults to "csv" (yfinance unreliable for forex)
    """
    user_id:           str
    custom_code:       str   = Field(
        ...,
        description=(
            "Python code that defines generate_signals(data). "
            "data is a pandas DataFrame with columns: date, open, high, low, close, volume. "
            "Must return a list or Series: 1=BUY, -1=SELL, 0=HOLD."
        )
    )
    pair:              str   = Field(..., description="e.g. EURUSD, GBPUSD")
    start_date:        str   = Field(..., description="YYYY-MM-DD")
    end_date:          str   = Field(..., description="YYYY-MM-DD")
    timeframe:         str   = Field(default="1d", description="1d | 1wk")
    initial_capital:   float = Field(default=10000.0, gt=0)
    position_size_pct: float = Field(default=0.1, gt=0, le=1.0)
    data_source:       str   = Field(
        default="csv",
        description="csv recommended for forex; auto | yfinance | csv"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id":      "e0b89393-0d59-4b55-af50-3bf9327d9efb",
                "pair":         "EURUSD",
                "start_date":   "2021-01-01",
                "end_date":     "2023-12-29",
                "timeframe":    "1d",
                "initial_capital":   10000.0,
                "position_size_pct": 0.1,
                "data_source":  "csv",
                "custom_code": (
                    "def generate_signals(data):\n"
                    "    import pandas as pd\n"
                    "    close = data['close']\n"
                    "    delta = close.diff()\n"
                    "    gain = delta.where(delta > 0, 0.0).rolling(14).mean()\n"
                    "    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()\n"
                    "    rsi = 100 - (100 / (1 + gain / loss))\n"
                    "    signals = []\n"
                    "    for r in rsi:\n"
                    "        if r < 30:\n"
                    "            signals.append(1)\n"
                    "        elif r > 70:\n"
                    "            signals.append(-1)\n"
                    "        else:\n"
                    "            signals.append(0)\n"
                    "    return signals\n"
                )
            }
        }


# RunCustomBacktestResponse reuses RunBacktestResponse directly.
# The service saves to the same backtests table with strategy_name='custom',
# so the returned row has the identical shape — no new response model needed.
# Import alias added here for explicitness in the route file:
RunCustomBacktestResponse = RunBacktestResponse
