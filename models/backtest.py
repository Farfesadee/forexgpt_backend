# from pydantic import BaseModel
# from datetime import datetime

# class BacktestRequest(BaseModel):
#     user_id: str | None = None
#     currency_pair: str
#     entry_price: float
#     exit_price: float
#     position_size_lots: float
#     days_held: int
#     direction: str                    # "LONG" or "SHORT"
#     market_condition: str = "normal"  # "normal" or "volatile"

# class CostBreakdown(BaseModel):
#     spread_pips: float
#     slippage_pips: float
#     commission_pips: float
#     financing_pips: float
#     total_cost_pips: float

# class BacktestResult(BaseModel):
#     gross_profit_pips: float
#     gross_profit_usd: float
#     net_profit_pips: float
#     net_profit_usd: float
#     cost_breakdown: CostBreakdown
#     cost_impact_percent: float
#     win: bool

# class BacktestResponse(BaseModel):
#     naive: BacktestResult
#     realistic: BacktestResult
#     backtest_id: str | None = None
#     created_at: datetime | None = None

"""
models/backtest.py — Pydantic schemas for the backtesting module.

Covers:
  - api/routes/backtest.py        (all backtest endpoints)
  - services/backtest_service.py  (engine I/O, cost model, metrics, interpreter)

Tables: public.backtests, public.backtest_trades
"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict
from datetime import datetime, date
from enum import Enum

# Enums 

class BacktestStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"

class TradeDirection(str, Enum):
    LONG  = "long"
    SHORT = "short"

class BacktestTimeframe(str, Enum):
    """yfinance-compatible interval strings."""
    M1  = "1m"
    M5  = "5m"
    M15 = "15m"
    H1  = "1h"
    H4  = "4h"
    D1  = "1d"

# Trading Cost Model

class TradingCosts(BaseModel):
    """
    Realistic trading cost assumptions for backtest_service.py.
    Defaults reflect typical retail broker conditions for EUR/USD.
    """
    spread_pips:             float = Field(1.0,  ge=0.0, le=20.0,
                                            description="Bid-ask spread in pips.")
    commission_per_lot:      float = Field(3.5,  ge=0.0, le=50.0,
                                            description="Round-trip commission in USD per standard lot.")
    slippage_pips:           float = Field(0.5,  ge=0.0, le=5.0,
                                            description="Estimated slippage per execution in pips.")
    swap_long_pips_per_day:  float = Field(0.0,  ge=-20.0, le=20.0,
                                            description="Overnight swap cost for long positions (pips/day). Negative = charge.")
    swap_short_pips_per_day: float = Field(0.0,  ge=-20.0, le=20.0,
                                            description="Overnight swap cost for short positions (pips/day). Negative = charge.")

    @property
    def total_entry_exit_pips(self) -> float:
        """Total round-trip cost in pips (spread + slippage both ways)."""
        return self.spread_pips + (self.slippage_pips * 2)

# Performance Metrics 

class BacktestMetrics(BaseModel):
    """
    Full set of performance metrics computed by backtest_service.py.
    Stored as backtests.metrics JSONB.
    Key fields are also denormalized onto the backtests row for fast queries.
    """
    # Returns
    total_return_pct:       float
    annualized_return_pct:  float

    # Risk-adjusted returns
    sharpe_ratio:           float
    sortino_ratio:          float
    calmar_ratio:           float

    # Drawdown
    max_drawdown_pct:             float
    max_drawdown_duration_days:   int

    # Trade statistics
    total_trades:          int
    win_rate_pct:          float
    profit_factor:         float
    avg_trade_duration_hours: float

    # Best / worst
    best_trade_pips:  float
    worst_trade_pips: float
    avg_win_pips:     float
    avg_loss_pips:    float

    # Cost impact
    total_cost_pips:  Optional[float] = None   # spread + commission + slippage across all trades

    @field_validator("win_rate_pct", "sharpe_ratio", "sortino_ratio", "calmar_ratio")
    @classmethod
    def round_ratios(cls, v: float) -> float:
        return round(v, 4)

    @field_validator("total_return_pct", "annualized_return_pct",
                     "max_drawdown_pct", "profit_factor")
    @classmethod
    def round_pcts(cls, v: float) -> float:
        return round(v, 2)

class EquityCurvePoint(BaseModel):
    """One data point in the equity curve time series."""
    date:     datetime
    equity:   float
    drawdown: float   # current drawdown as a decimal, e.g. -0.05 = -5%

# API Request Schemas

class BacktestRunRequest(BaseModel):
    """POST /backtest/run"""
    # Strategy source — provide one of: strategy_id or inline code
    strategy_id: Optional[str] = Field(None, description="ID of a saved strategy from the library.")
    code:        Optional[str] = Field(None, min_length=50,
                                        description="Inline Python strategy code (if not using saved strategy).")

    # Market data config
    pair:       str  = Field(..., description="yfinance ticker, e.g. 'EURUSD=X' or 'GBP/USD'.")
    start_date: date = Field(..., description="Backtest start date.")
    end_date:   date = Field(..., description="Backtest end date.")
    timeframe:  BacktestTimeframe = BacktestTimeframe.H1

    # Capital
    initial_capital: float = Field(10_000.0, ge=100.0, le=10_000_000.0)
    leverage:        int   = Field(30,        ge=1,      le=500)

    # Cost model (overrides defaults from config.py)
    costs: TradingCosts = Field(default_factory=TradingCosts)

    # Options
    save_results: bool = Field(False, description="Persist completed backtest to the DB.")

    @model_validator(mode="after")
    def must_have_strategy_source(self) -> "BacktestRunRequest":
        if not self.strategy_id and not self.code:
            raise ValueError("Provide either strategy_id or inline code.")
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date.")
        return self

    @field_validator("pair")
    @classmethod
    def normalise_pair(cls, v: str) -> str:
        """Accept EUR/USD or EURUSD → always store as EURUSD=X for yfinance."""
        v = v.upper().strip()
        if "/" in v:
            v = v.replace("/", "") + "=X"
        elif len(v) == 6 and not v.endswith("=X"):
            v = v + "=X"
        return v

    model_config = {"json_schema_extra": {"example": {
        "strategy_id":    "30000000-0000-0000-0000-000000000001",
        "pair":           "EUR/USD",
        "start_date":     "2023-01-01",
        "end_date":       "2024-01-01",
        "timeframe":      "1h",
        "initial_capital": 10000,
        "leverage":        30,
        "costs": {
            "spread_pips":        1.0,
            "commission_per_lot": 3.5,
            "slippage_pips":      0.5,
        },
        "save_results": False,
    }}}

class BacktestFilterParams(BaseModel):
    """Query params for GET /backtest"""
    pair:   Optional[str] = None
    limit:  int = Field(20, ge=1, le=100)
    offset: int = Field(0,  ge=0)

# API Response Schemas 

class BacktestTrade(BaseModel):
    """Individual trade record — from backtest_trades table."""
    id:             str
    backtest_id:    str
    trade_number:   int
    direction:      TradeDirection
    entry_time:     datetime
    exit_time:      datetime
    entry_price:    float
    exit_price:     float
    lot_size:       float
    pnl_pips:       float
    pnl_usd:        float
    duration_hours: Optional[float]

    model_config = {"from_attributes": True}

class BacktestResponse(BaseModel):
    """Full backtest record — returned on completion or GET /backtest/{id}."""
    id:          str
    user_id:     str
    strategy_id: Optional[str]

    pair:            str
    start_date:      date
    end_date:        date
    timeframe:       str
    initial_capital: float
    leverage:        int

    costs:  TradingCosts

    status:        BacktestStatus
    error_message: Optional[str]

    # Full result data
    metrics:      Optional[BacktestMetrics]
    equity_curve: Optional[List[EquityCurvePoint]]

    # Denormalized key metrics (for quick display without parsing metrics JSONB)
    total_return_pct: Optional[float]
    sharpe_ratio:     Optional[float]
    max_drawdown_pct: Optional[float]
    win_rate_pct:     Optional[float]
    total_trades:     Optional[int]

    # Educational output from backtest_service.py interpreter
    educational_analysis:    Optional[str]
    improvement_suggestions: List[str]

    is_saved:   bool
    user_notes: Optional[str]

    created_at:   datetime
    updated_at:   datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}

class BacktestListItem(BaseModel):
    """Compact backtest row for list views."""
    id:               str
    strategy_id:      Optional[str]
    pair:             str
    start_date:       date
    end_date:         date
    timeframe:        str
    initial_capital:  float
    status:           BacktestStatus
    total_return_pct: Optional[float]
    sharpe_ratio:     Optional[float]
    max_drawdown_pct: Optional[float]
    win_rate_pct:     Optional[float]
    total_trades:     Optional[int]
    is_saved:         bool
    created_at:       datetime

    model_config = {"from_attributes": True}

class BacktestListResponse(BaseModel):
    items:  List[BacktestListItem]
    total:  int

class BacktestTradeListResponse(BaseModel):
    """Paginated trade ledger for a single backtest."""
    backtest_id: str
    trades:      List[BacktestTrade]
    total:       int
    limit:       int
    offset:      int

class BacktestUpdateRequest(BaseModel):
    """PATCH /backtest/{id}"""
    is_saved:   Optional[bool] = None
    user_notes: Optional[str]  = Field(None, max_length=2000)

# Educational Interpretation 
# Internal schema used by backtest_service.py interpret_results()

class MetricInterpretation(BaseModel):
    """Plain-English interpretation of a single metric."""
    metric:      str
    value:       float
    rating:      str   # 'excellent' | 'good' | 'acceptable' | 'poor'
    explanation: str

class BacktestInterpretation(BaseModel):
    """
    Full educational analysis produced by backtest_service.py.
    Written to backtests.educational_analysis + improvement_suggestions.
    """
    summary:               str
    interpretations:       List[MetricInterpretation]
    improvement_suggestions: List[str]
    cost_impact_summary:   str   # e.g. "Trading costs consumed 2.3% of gross returns"