from pydantic import BaseModel
from datetime import datetime


class BacktestRequest(BaseModel):
    user_id: str | None = None
    currency_pair: str
    entry_price: float
    exit_price: float
    position_size_lots: float
    days_held: int
    direction: str                    # "LONG" or "SHORT"
    market_condition: str = "normal"  # "normal" or "volatile"


class CostBreakdown(BaseModel):
    spread_pips: float
    slippage_pips: float
    commission_pips: float
    financing_pips: float
    total_cost_pips: float


class BacktestResult(BaseModel):
    gross_profit_pips: float
    gross_profit_usd: float
    net_profit_pips: float
    net_profit_usd: float
    cost_breakdown: CostBreakdown
    cost_impact_percent: float
    win: bool


class BacktestResponse(BaseModel):
    naive: BacktestResult
    realistic: BacktestResult
    backtest_id: str | None = None
    created_at: datetime | None = None