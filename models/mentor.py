
"""
models/mentor.py — Pydantic schemas for the Mentor module.

Covers:
  - routes/mentor.py           (API request/response contracts)
  - services/mentor_service.py (internal types passed between layers)

The mentor supports two modes:
  1. Generic Q&A       — user asks forex/quant questions in a conversation
  2. Backtest-aware    — backtest service seeds a conversation with full
                         strategy context; user then asks follow-up questions
                         grounded in their actual results and config.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List


# =============================================================================
# SHARED / INTERNAL  —  the core backtest context object
# =============================================================================

class BacktestContext(BaseModel):
    """
    Backtest context passed to the mentor.

    Fields
    ------
    metrics       : performance output from the backtest engine (required)
    strategy_type : what kind of strategy was run — free text, any value
                    e.g. "custom", "mean_reversion", "trend_following"
                    defaults to "custom" if not specified
    parameters    : optional strategy config if available
    backtest_id   : optional ID from the backtest service for traceability
    """
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "strategy_type": "custom",
            "metrics": {
                "strategy_name":         "custom",
                "pair":                  "EURUSD",
                "start_date":            "2021-01-01",
                "end_date":              "2023-12-29",
                "total_return_pct":      -29.99,
                "sharpe_ratio":          -4.83,
                "max_drawdown_pct":      -30.24,
                "win_rate_pct":          67.92,
                "total_trades":          53,
                "profit_factor":         1.94,
                "avg_holding_days":      3.4,
                "winning_trades":        36,
                "losing_trades":         17,
                "avg_win":               0.01,
                "avg_loss":             -0.01,
                "avg_risk_reward":       0.92,
                "volatility_annual_pct": 3.41,
                "sortino_ratio":        -5.08,
                "cagr_pct":            -10.87
            },
            "backtest_id": "bt_abc123"
        }
    })

    metrics:       Dict[str, Any]                   # required — from backtest engine
    strategy_type: str            = "custom"        # optional — defaults to "custom"
    parameters:    Dict[str, Any] = {}              # optional — strategy config
    backtest_id:   Optional[str]  = None            # optional — for traceability


# =============================================================================
# GENERIC Q&A  —  ask a question in an existing or new conversation
# =============================================================================

class AskQuestionRequest(BaseModel):
    """
    POST /mentor/conversations/{id}/messages
    POST /mentor/conversations   (starts a new generic conversation)
    user_id is injected from the JWT token — not required in the body.
    """
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "What is the Sharpe ratio?",
            "user_id": "user_123",
            "conversation_id": None
        }
    })

    message: str = Field(..., min_length=3, max_length=2000)
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None


class AskQuestionResponse(BaseModel):
    """Returned after any mentor message (generic or backtest follow-up)."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "response":        "The Sharpe ratio is a measure of risk-adjusted return...",
            "conversation_id": "uuid-here",
            "message_count":   2,
            "timestamp":       "2024-01-01T00:00:00"
        }
    })

    response:        str
    conversation_id: str
    message_count:   int
    timestamp:       str


# =============================================================================
# BACKTEST-SEEDED CONVERSATION  —  called internally by the backtest service
# =============================================================================

class StartBacktestConversationRequest(BaseModel):
    """
    POST /mentor/backtest-conversations
    user_id comes from JWT token — not required in the body.
    """
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "backtest_context": {
                "strategy_type": "mean_reversion",
                "parameters": {
                    "rsi_period": 14, "rsi_overbought": 70,
                    "stop_loss_pct": 0.02, "currency_pair": "EUR/USD", "timeframe": "1H"
                },
                "metrics": {
                    "sharpe_ratio": 0.3, "max_drawdown": 18.5,
                    "win_rate": 45.2, "total_return": -5.3, "total_trades": 42,
                },
                "backtest_id": "bt_abc123"
            }
        }
    })

    backtest_context: BacktestContext


class StartBacktestConversationResponse(BaseModel):
    """
    Returned after the backtest conversation is seeded.
    The frontend stores conversation_id and uses it for follow-up questions
    via the standard POST /mentor/conversations/{id}/messages endpoint.
    """
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "analysis":        "Your EUR/USD mean-reversion strategy (RSI-14, 1H)...",
            "conversation_id": "uuid-here",
            "backtest_id":     "bt_abc123",
            "timestamp":       "2024-01-01T00:00:00"
        }
    })

    analysis:        str            # initial deep-dive analysis
    conversation_id: str            # used for all follow-up questions
    backtest_id:     Optional[str] = None
    timestamp:       str


# =============================================================================
# CONVERSATION MANAGEMENT
# =============================================================================

class ConversationMessageResponse(BaseModel):
    """Single message in a conversation."""
    role:      str
    content:   str
    timestamp: Optional[str] = None


class ConversationHistoryResponse(BaseModel):
    """Full message history for a conversation."""
    conversation_id: str
    history:         List[ConversationMessageResponse]
    message_count:   int


class ConversationSummaryResponse(BaseModel):
    """Lightweight row for the conversation list / sidebar."""
    conversation_id: str
    started_at:      str
    preview:         str
    message_count:   int
    is_backtest:     bool = False   # lets the UI badge backtest conversations


class DeleteConversationResponse(BaseModel):
    """Returned after a conversation is deleted."""
    message:         str
    conversation_id: str
