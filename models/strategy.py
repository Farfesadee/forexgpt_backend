
"""
models/strategy.py — Pydantic schemas for the strategy code generation module.

Covers:
  - api/routes/codegen.py         (all codegen endpoints)
  - services/codegen_service.py   (LLM pipeline, E2B sandbox types)

Table: public.strategies
View:  public.strategy_leaderboard
"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# Enums

class StrategyType(str, Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION  = "mean_reversion"
    BREAKOUT        = "breakout"
    CARRY_TRADE     = "carry_trade"
    MOMENTUM        = "momentum"
    CUSTOM          = "custom"

class ComplexityLevel(str, Enum):
    SIMPLE       = "simple"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"

class Timeframe(str, Enum):
    M1  = "M1"
    M5  = "M5"
    M15 = "M15"
    H1  = "H1"
    H4  = "H4"
    D1  = "D1"

# Parameter Definition

class StrategyParameter(BaseModel):
    """
    One tunable parameter extracted from generated code.
    Stored as a dict of these in strategies.parameters JSONB.
    """
    default:     Any
    description: str
    range:       Optional[str] = None   # e.g. "5-50", "0.1-2.0"
    type:        str = "number"         # "number" | "boolean" | "string"

# API Request Schemas 

class StrategyGenerateRequest(BaseModel):
    """POST /codegen/generate"""
    strategy_description: str = Field(
        ..., min_length=20, max_length=2000,
        description="Plain-English description of the strategy logic.",
    )
    strategy_type:   StrategyType  = StrategyType.CUSTOM
    target_pairs:    List[str]     = Field(default=["EUR/USD"], min_length=1, max_length=10)
    timeframe:       Timeframe     = Timeframe.H1
    risk_per_trade:  float         = Field(1.0, ge=0.1, le=5.0,
                                           description="% of account to risk per trade.")
    include_comments:      bool = True
    include_backtest_hook: bool = True
    save_to_library:       bool = False   # if True, saved to strategies table after generation

    @field_validator("target_pairs")
    @classmethod
    def normalise_pairs(cls, pairs: List[str]) -> List[str]:
        out = []
        for p in pairs:
            p = p.upper().strip()
            if len(p) == 6 and "/" not in p:
                p = f"{p[:3]}/{p[3:]}"
            out.append(p)
        return out

    model_config = {"json_schema_extra": {"example": {
        "strategy_description": "Buy EUR/USD when the 20-period EMA crosses above the 50-period EMA. Exit when it crosses back below. Risk 1% per trade.",
        "strategy_type":   "trend_following",
        "target_pairs":    ["EUR/USD"],
        "timeframe":       "H1",
        "risk_per_trade":  1.0,
        "include_comments": True,
        "include_backtest_hook": True,
    }}}

class StrategyValidateRequest(BaseModel):
    """POST /codegen/validate — run existing code through E2B without regenerating."""
    code: str = Field(..., min_length=50, description="Python strategy code to validate.")

class StrategyUpdateRequest(BaseModel):
    """PATCH /codegen/strategies/{id}"""
    name:       Optional[str]  = Field(None, min_length=2, max_length=120)
    is_saved:   Optional[bool] = None
    is_public:  Optional[bool] = None
    parameters: Optional[Dict[str, Any]] = None   # updated parameter values

# Sandbox Result 

class SandboxResult(BaseModel):
    """
    Result of E2B code execution.
    Stored in strategies.sandbox_passed + strategies.sandbox_output.
    """
    executed:  bool              # False if E2B not configured
    passed:    Optional[bool]    # None if not executed
    stage:     str               # 'syntax' | 'structure' | 'runtime' | 'skipped'
    stdout:    str = ""
    stderr:    str = ""
    error:     Optional[str]

# API Response Schemas 

class StrategyResponse(BaseModel):
    """Full strategy record."""
    id:             str
    user_id:        str
    name:           str
    description:    str
    strategy_type:  StrategyType
    target_pairs:   List[str]
    timeframe:      str
    risk_per_trade: float

    code:              str
    parameters:        Dict[str, StrategyParameter]
    educational_notes: List[str]
    complexity:        Optional[ComplexityLevel]

    sandbox_passed:    Optional[bool]
    sandbox_output:    Optional[str]

    system_prompt_key: Optional[str]
    model_used:        Optional[str]

    is_saved:   bool
    is_public:  bool
    version:    int

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class StrategyGenerateResponse(BaseModel):
    """
    Response from POST /codegen/generate.
    Always includes the generated code + sandbox result.
    Optionally includes the saved strategy record if save_to_library=True.
    """
    strategy_name:     str
    explanation:       str
    code:              str
    parameters:        Dict[str, StrategyParameter]
    educational_notes: List[str]
    complexity:        ComplexityLevel
    sandbox:           SandboxResult
    saved_strategy:    Optional[StrategyResponse] = None   # present if save_to_library=True

class StrategyValidateResponse(BaseModel):
    """Response from POST /codegen/validate."""
    passed:  bool
    stage:   str
    stdout:  str
    error:   Optional[str]

class StrategyListItem(BaseModel):
    """Compact row for the strategy library list."""
    id:             str
    name:           str
    description:    str
    strategy_type:  StrategyType
    target_pairs:   List[str]
    timeframe:      str
    complexity:     Optional[ComplexityLevel]
    sandbox_passed: Optional[bool]
    is_saved:       bool
    is_public:      bool
    created_at:     datetime

    model_config = {"from_attributes": True}

class StrategyListResponse(BaseModel):
    items:  List[StrategyListItem]
    total:  int

class LeaderboardEntry(BaseModel):
    """
    One row from the strategy_leaderboard VIEW.
    Joins strategies + backtests — shows best-performing validated strategies.
    """
    backtest_id:      str
    user_id:          str
    author:           Optional[str]
    strategy_name:    str
    strategy_type:    StrategyType
    target_pairs:     List[str]
    complexity:       Optional[ComplexityLevel]
    pair:             str
    timeframe:        str
    total_return_pct: Optional[float]
    sharpe_ratio:     Optional[float]
    sortino_ratio:    Optional[float]
    max_drawdown_pct: Optional[float]
    win_rate_pct:     Optional[float]
    profit_factor:    Optional[float]
    total_trades:     Optional[int]
    sandbox_passed:   Optional[bool]
    is_public:        bool
    completed_at:     Optional[datetime]

    model_config = {"from_attributes": True}

class LeaderboardResponse(BaseModel):
    items: List[LeaderboardEntry]
    total: int

# Template Schema

class StrategyTemplate(BaseModel):
    """Pre-built strategy template shown in the codegen UI."""
    id:                 str
    name:               str
    strategy_type:      StrategyType
    difficulty:         str
    description:        str
    sample_description: str   # ready-to-use input for the generate endpoint