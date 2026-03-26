# # from pydantic import BaseModel

# # class MentorRequest(BaseModel):
# #     question: str
# #     context: str | None = None
# #     user_id: str | None = None

# # class MentorResponse(BaseModel):
# #     answer: str
# #     conversation_id: str | None = None

# # class CodeGenRequest(BaseModel):
# #     strategy_description: str
# #     user_id: str | None = None

# # class CodeGenResponse(BaseModel):
# #     code: str
# #     language: str = "python"
    
# """
# models/mentor.py — Pydantic schemas for the Forex theory mentor module.

# Covers:
#   - api/routes/mentor.py        (request/response for all mentor endpoints)
#   - services/mentor_service.py  (internal types for LLM pipeline)

# Tables: public.mentor_conversations, public.mentor_messages
# View:   public.mentor_history
# """

# from __future__ import annotations
# from pydantic import BaseModel, Field, field_validator
# from typing import Optional, List
# from datetime import datetime
# from enum import Enum

# # Enums 

# class DifficultyLevel(str, Enum):
#     BEGINNER     = "beginner"
#     INTERMEDIATE = "intermediate"
#     ADVANCED     = "advanced"

# class MessageRole(str, Enum):
#     USER      = "user"
#     ASSISTANT = "assistant"
#     SYSTEM    = "system"

# # Conversation Schemas 

# class ConversationCreate(BaseModel):
#     """POST /mentor/conversations"""
#     difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE

#     model_config = {"json_schema_extra": {"example": {
#         "difficulty": "intermediate",
#     }}}

# class ConversationResponse(BaseModel):
#     """Single conversation record."""
#     id:              str
#     user_id:         str
#     title:           Optional[str]
#     topic_tags:      List[str]
#     difficulty:      DifficultyLevel
#     message_count:   int
#     is_archived:     bool
#     last_message_at: Optional[datetime]
#     created_at:      datetime
#     updated_at:      datetime

#     model_config = {"from_attributes": True}

# class ConversationListItem(BaseModel):
#     """
#     Compact conversation row for the sidebar list.
#     Sourced from the mentor_history VIEW which includes a response preview snippet.
#     """
#     id:                    str
#     title:                 Optional[str]
#     topic_tags:            List[str]
#     difficulty:            DifficultyLevel
#     message_count:         int
#     is_archived:           bool
#     last_message_at:       Optional[datetime]
#     last_response_preview: Optional[str]   # first 140 chars of last assistant reply
#     last_model_used:       Optional[str]   # e.g. 'mistral-7b-base'
#     created_at:            datetime

#     model_config = {"from_attributes": True}

# class ConversationListResponse(BaseModel):
#     items:           List[ConversationListItem]
#     total:           int

# # Message Schemas

# class MentorAskRequest(BaseModel):
#     """
#     POST /mentor/conversations/{id}/messages
#     The user's question to the Forex theory mentor.
#     """
#     question:     str = Field(..., min_length=3, max_length=2000,
#                               description="The Forex or finance question to ask the mentor.")
#     include_examples: bool = Field(True, description="Request a worked numerical example.")
#     include_formulas: bool = Field(False, description="Request mathematical formulas where applicable.")

#     model_config = {"json_schema_extra": {"example": {
#         "question":          "What is the carry trade and what are its main risks?",
#         "include_examples":  True,
#         "include_formulas":  False,
#     }}}
    

# class MentorMessageResponse(BaseModel):
#     """Single message row — returned after a question is answered."""
#     id:                  str
#     conversation_id:     str
#     role:                MessageRole
#     content:             str

#     # Assistant-message metadata (None on user messages)
#     topic_tags:          List[str]
#     related_concepts:    List[str]
#     follow_up_questions: List[str]
#     system_prompt_key:   Optional[str]
#     model_used:          Optional[str]
#     adapter_used:        Optional[str]
#     tokens_used:         Optional[int]
#     latency_ms:          Optional[int]
#     thumbs_up:           Optional[bool]

#     created_at: datetime

#     model_config = {"from_attributes": True}

# class MentorAskResponse(BaseModel):
#     """
#     Response returned by POST /mentor/conversations/{id}/messages.
#     Includes the saved user message + the assistant's answer.
#     """
#     user_message:      MentorMessageResponse
#     assistant_message: MentorMessageResponse

# class MessageFeedbackRequest(BaseModel):
#     """PATCH /mentor/messages/{id}/feedback"""
#     thumbs_up: bool = Field(..., description="True = helpful, False = not helpful.")

# class MessageHistoryResponse(BaseModel):
#     """GET /mentor/conversations/{id}/messages"""
#     conversation_id: str
#     messages:        List[MentorMessageResponse]

# # Internal Service Schemas 
# # Used by mentor_service.py — not exposed directly via API responses.

# class LLMMessage(BaseModel):
#     """
#     OpenAI-style message dict passed to the Mistral/HF API.
#     mentor_service.py builds a list of these from mentor_messages history.
#     """
#     role:    MessageRole
#     content: str

# class MentorLLMContext(BaseModel):
#     """
#     Complete context assembled by mentor_service.py before calling the LLM.
#     Passed to core/llm_router.py for model selection and prompt building.
#     """
#     conversation_id:   str
#     user_id:           str
#     difficulty:        DifficultyLevel
#     history:           List[LLMMessage]   # last N turns for context window
#     new_question:      str
#     include_examples:  bool
#     include_formulas:  bool
#     system_prompt_key: str                # resolved by llm_router.py from difficulty




























# """
# Pydantic schemas for Mentor Service
# Request and Response models for mentor endpoints
# """

# from pydantic import BaseModel
# from typing import Optional


# # ============================================================================
# # REQUEST MODELS
# # ============================================================================

# class AskQuestionRequest(BaseModel):
#     """Request model for asking the mentor a question"""
#     user_id: Optional[str] = None
#     message: str
#     conversation_id: Optional[str] = None

#     class Config:
#         json_schema_extra = {
#             "example": {
#                 "user_id": "user_123",
#                 "message": "What is the Sharpe ratio?",
#                 "conversation_id": None
#             }
#         }


# # ============================================================================
# # RESPONSE MODELS
# # ============================================================================

# class AskQuestionResponse(BaseModel):
#     """Response model for mentor answer"""
#     response: str
#     conversation_id: str
#     message_count: int
#     timestamp: str

#     class Config:
#         json_schema_extra = {
#             "example": {
#                 "response": "The Sharpe ratio is a measure of risk-adjusted return...",
#                 "conversation_id": "uuid-here",
#                 "message_count": 2,
#                 "timestamp": "2024-01-01T00:00:00"
#             }
#         }


# class ConversationMessageResponse(BaseModel):
#     """Single message in a conversation"""
#     role: str
#     content: str
#     timestamp: Optional[str] = None


# class ConversationHistoryResponse(BaseModel):
#     """Response model for full conversation history"""
#     conversation_id: str
#     history: list[ConversationMessageResponse]
#     message_count: int


# class ConversationSummaryResponse(BaseModel):
#     """Response model for conversation summary in list"""
#     conversation_id: str
#     started_at: str
#     preview: str
#     message_count: int


# class DeleteConversationResponse(BaseModel):
#     """Response model for conversation deletion"""
#     message: str
#     conversation_id: str






























# old mentor.py without dev mode
# """
# models/mentor.py — Pydantic schemas for the Mentor module.

# Covers:
#   - routes/mentor.py           (API request/response contracts)
#   - services/mentor_service.py (internal types passed between layers)

# The mentor supports two modes:
#   1. Generic Q&A       — user asks forex/quant questions in a conversation
#   2. Backtest-aware    — backtest service seeds a conversation with full
#                          strategy context; user then asks follow-up questions
#                          grounded in their actual results and config.
# """

# from __future__ import annotations
# from pydantic import BaseModel, Field, ConfigDict
# from typing import Optional, Dict, Any, List


# # =============================================================================
# # SHARED / INTERNAL  —  the core backtest context object
# # =============================================================================

# class BacktestContext(BaseModel):
#     """
#     Full backtest context injected by the backtest service.

#     Stored once at conversation creation and prepended to every LLM call
#     so the mentor always reasons against THIS specific run — not generically.

#     Fields
#     ------
#     strategy_type : human-readable label, e.g. "mean_reversion"
#     parameters    : the exact config the user ran, e.g. rsi_period, stop_loss
#     metrics       : performance output from the backtest engine
#     backtest_id   : opaque ID from the backtest service (for traceability)
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "strategy_type": "mean_reversion",
#             "parameters": {
#                 "rsi_period":      14,
#                 "rsi_overbought":  70,
#                 "rsi_oversold":    30,
#                 "stop_loss_pct":   0.02,
#                 "take_profit_pct": 0.04,
#                 "currency_pair":   "EUR/USD",
#                 "timeframe":       "1H"
#             },
#             "metrics": {
#                 "sharpe_ratio":  0.3,
#                 "max_drawdown":  18.5,
#                 "win_rate":      45.2,
#                 "total_return": -5.3,
#                 "total_trades":  42,
#                 "profit_factor": 0.87,
#                 "avg_trade_pnl": -12.6
#             },
#             "backtest_id": "bt_abc123"
#         }
#     })

#     strategy_type: str
#     parameters:    Dict[str, Any]
#     metrics:       Dict[str, Any]
#     backtest_id:   Optional[str] = None


# # =============================================================================
# # GENERIC Q&A  —  ask a question in an existing or new conversation
# # =============================================================================

# class AskQuestionRequest(BaseModel):
#     """
#     POST /mentor/conversations/{id}/messages
#     POST /mentor/conversations   (starts a new generic conversation)
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             # "user_id":         "user_123",
#             "message":         "What is the Sharpe ratio?",
#             "conversation_id": None
#         }
#     })

#     # user_id:         str
#     message:         str = Field(..., min_length=3, max_length=2000)
#     conversation_id: Optional[str] = None


# class AskQuestionResponse(BaseModel):
#     """Returned after any mentor message (generic or backtest follow-up)."""
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "response":        "The Sharpe ratio is a measure of risk-adjusted return...",
#             "conversation_id": "uuid-here",
#             "message_count":   2,
#             "timestamp":       "2024-01-01T00:00:00"
#         }
#     })

#     response:        str
#     conversation_id: str
#     message_count:   int
#     timestamp:       str


# # =============================================================================
# # BACKTEST-SEEDED CONVERSATION  —  called internally by the backtest service
# # =============================================================================

# class StartBacktestConversationRequest(BaseModel):
#     """
#     POST /mentor/backtest-conversations

#     Called service-to-service by the backtest service right after a run
#     completes.  Creates a new mentor conversation pre-loaded with the full
#     BacktestContext and returns an initial analysis + a conversation_id that
#     the frontend passes back for all follow-up questions.
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "user_id": "user_123",
#             "backtest_context": {
#                 "strategy_type": "mean_reversion",
#                 "parameters": {
#                     "rsi_period":      14,
#                     "rsi_overbought":  70,
#                     "rsi_oversold":    30,
#                     "stop_loss_pct":   0.02,
#                     "take_profit_pct": 0.04,
#                     "currency_pair":   "EUR/USD",
#                     "timeframe":       "1H"
#                 },
#                 "metrics": {
#                     "sharpe_ratio":  0.3,
#                     "max_drawdown":  18.5,
#                     "win_rate":      45.2,
#                     "total_return": -5.3,
#                     "total_trades":  42,
#                     "profit_factor": 0.87,
#                     "avg_trade_pnl": -12.6
#                 },
#                 "backtest_id": "bt_abc123"
#             }
#         }
#     })

#     user_id:          str
#     backtest_context: BacktestContext


# class StartBacktestConversationResponse(BaseModel):
#     """
#     Returned after the backtest conversation is seeded.
#     The frontend stores conversation_id and uses it for follow-up questions
#     via the standard POST /mentor/conversations/{id}/messages endpoint.
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "analysis":        "Your EUR/USD mean-reversion strategy (RSI-14, 1H)...",
#             "conversation_id": "uuid-here",
#             "backtest_id":     "bt_abc123",
#             "timestamp":       "2024-01-01T00:00:00"
#         }
#     })

#     analysis:        str            # initial deep-dive analysis
#     conversation_id: str            # used for all follow-up questions
#     backtest_id:     Optional[str] = None
#     timestamp:       str


# # =============================================================================
# # CONVERSATION MANAGEMENT
# # =============================================================================

# class ConversationMessageResponse(BaseModel):
#     """Single message in a conversation."""
#     role:      str
#     content:   str
#     timestamp: Optional[str] = None


# class ConversationHistoryResponse(BaseModel):
#     """Full message history for a conversation."""
#     conversation_id: str
#     history:         List[ConversationMessageResponse]
#     message_count:   int


# class ConversationSummaryResponse(BaseModel):
#     """Lightweight row for the conversation list / sidebar."""
#     conversation_id: str
#     started_at:      str
#     preview:         str
#     message_count:   int
#     is_backtest:     bool = False   # lets the UI badge backtest conversations


# class DeleteConversationResponse(BaseModel):
#     """Returned after a conversation is deleted."""
#     message:         str
#     conversation_id: str


# # =============================================================================
# # BACKTEST PASS / FAIL ANALYSIS  —  called by the backtest service
# # =============================================================================

# class AnalyzeBacktestRequest(BaseModel):
#     """
#     Request model for backtest pass/fail analysis.
#     Sent by the backtest service after a run completes.
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "user_id":       "user_123",
#             "strategy_type": "mean_reversion",
#             "metrics": {
#                 "sharpe_ratio":  0.3,
#                 "max_drawdown":  18.5,
#                 "win_rate":      45.2,
#                 "total_return": -5.3,
#                 "total_trades":  42,
#             }
#         }
#     })

#     user_id:       str
#     strategy_type: str
#     metrics:       Dict[str, Any]   # sharpe_ratio, max_drawdown, total_return,
#                                     # win_rate, total_trades


# class AnalyzeBacktestResponse(BaseModel):
#     """
#     Response model for backtest pass/fail analysis.
#     verdict is always "PASS" or "FAIL".
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "verdict":     "FAIL",
#             "explanation": "Your mean reversion strategy failed. The Sharpe of 0.3...",
#             "timestamp":   "2024-01-01T00:00:00"
#         }
#     })

#     verdict:     str    # "PASS" or "FAIL"
#     explanation: str    # educational explanation of why
#     timestamp:   str
































































# """
# models/mentor.py — Pydantic schemas for the Mentor module.

# Covers:
#   - routes/mentor.py           (API request/response contracts)
#   - services/mentor_service.py (internal types passed between layers)

# The mentor supports two modes:
#   1. Generic Q&A       — user asks forex/quant questions in a conversation
#   2. Backtest-aware    — backtest service seeds a conversation with full
#                          strategy context; user then asks follow-up questions
#                          grounded in their actual results and config.
# """

# from __future__ import annotations
# from pydantic import BaseModel, Field, ConfigDict
# from typing import Optional, Dict, Any, List

# from models import user


# # =============================================================================
# # SHARED / INTERNAL  —  the core backtest context object
# # =============================================================================

# class BacktestContext(BaseModel):
#     """
#     Full backtest context injected by the backtest service.

#     Stored once at conversation creation and prepended to every LLM call
#     so the mentor always reasons against THIS specific run — not generically.

#     Fields
#     ------
#     strategy_type : human-readable label, e.g. "mean_reversion"
#     parameters    : the exact config the user ran, e.g. rsi_period, stop_loss
#     metrics       : performance output from the backtest engine
#     backtest_id   : opaque ID from the backtest service (for traceability)
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "strategy_type": "mean_reversion",
#             "parameters": {
#                 "rsi_period":      14,
#                 "rsi_overbought":  70,
#                 "rsi_oversold":    30,
#                 "stop_loss_pct":   0.02,
#                 "take_profit_pct": 0.04,
#                 "currency_pair":   "EUR/USD",
#                 "timeframe":       "1H"
#             },
#             "metrics": {
#                 "sharpe_ratio":  0.3,
#                 "max_drawdown":  18.5,
#                 "win_rate":      45.2,
#                 "total_return": -5.3,
#                 "total_trades":  42,
#                 "profit_factor": 0.87,
#                 "avg_trade_pnl": -12.6
#             },
#             "backtest_id": "bt_abc123"
#         }
#     })

#     strategy_type: str
#     parameters:    Dict[str, Any]
#     metrics:       Dict[str, Any]
#     backtest_id:   Optional[str] = None


# # =============================================================================
# # GENERIC Q&A  —  ask a question in an existing or new conversation
# # =============================================================================

# class AskQuestionRequest(BaseModel):
#     """
#     POST /mentor/conversations/{id}/messages
#     POST /mentor/conversations   (starts a new generic conversation)
#     user_id is injected from the JWT token — not required in the body.
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "message": "What is the Sharpe ratio?",
#             "user_id": "user_123",
#             "conversation_id": None
#         }
#     })

#     message: str = Field(..., min_length=3, max_length=2000),
#     user_id: Optional[str] = None,
#     conversation_id: Optional[str] = None


# class AskQuestionResponse(BaseModel):
#     """Returned after any mentor message (generic or backtest follow-up)."""
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "response":        "The Sharpe ratio is a measure of risk-adjusted return...",
#             "conversation_id": "uuid-here",
#             "message_count":   2,
#             "timestamp":       "2024-01-01T00:00:00"
#         }
#     })

#     response:        str
#     conversation_id: str
#     message_count:   int
#     timestamp:       str


# # =============================================================================
# # BACKTEST-SEEDED CONVERSATION  —  called internally by the backtest service
# # =============================================================================

# class StartBacktestConversationRequest(BaseModel):
#     """
#     POST /mentor/backtest-conversations
#     user_id comes from JWT token — not required in the body.
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "backtest_context": {
#                 "strategy_type": "mean_reversion",
#                 "parameters": {
#                     "rsi_period": 14, "rsi_overbought": 70,
#                     "stop_loss_pct": 0.02, "currency_pair": "EUR/USD", "timeframe": "1H"
#                 },
#                 "metrics": {
#                     "sharpe_ratio": 0.3, "max_drawdown": 18.5,
#                     "win_rate": 45.2, "total_return": -5.3, "total_trades": 42,
#                 },
#                 "backtest_id": "bt_abc123"
#             }
#         }
#     })

#     backtest_context: BacktestContext


# class StartBacktestConversationResponse(BaseModel):
#     """
#     Returned after the backtest conversation is seeded.
#     The frontend stores conversation_id and uses it for follow-up questions
#     via the standard POST /mentor/conversations/{id}/messages endpoint.
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "analysis":        "Your EUR/USD mean-reversion strategy (RSI-14, 1H)...",
#             "conversation_id": "uuid-here",
#             "backtest_id":     "bt_abc123",
#             "timestamp":       "2024-01-01T00:00:00"
#         }
#     })

#     analysis:        str            # initial deep-dive analysis
#     conversation_id: str            # used for all follow-up questions
#     backtest_id:     Optional[str] = None
#     timestamp:       str


# # =============================================================================
# # CONVERSATION MANAGEMENT
# # =============================================================================

# class ConversationMessageResponse(BaseModel):
#     """Single message in a conversation."""
#     role:      str
#     content:   str
#     timestamp: Optional[str] = None


# class ConversationHistoryResponse(BaseModel):
#     """Full message history for a conversation."""
#     conversation_id: str
#     history:         List[ConversationMessageResponse]
#     message_count:   int


# class ConversationSummaryResponse(BaseModel):
#     """Lightweight row for the conversation list / sidebar."""
#     conversation_id: str
#     started_at:      str
#     preview:         str
#     message_count:   int
#     is_backtest:     bool = False   # lets the UI badge backtest conversations


# class DeleteConversationResponse(BaseModel):
#     """Returned after a conversation is deleted."""
#     message:         str
#     conversation_id: str


# # =============================================================================
# # BACKTEST PASS / FAIL ANALYSIS  —  called by the backtest service
# # =============================================================================

# class AnalyzeBacktestRequest(BaseModel):
#     """
#     Request model for backtest pass/fail analysis.
#     user_id comes from JWT token — not required in the body.
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "strategy_type": "custom",
#             "metrics": {
#                 "strategy_name":        "custom",
#                 "pair":                 "EURUSD",
#                 "start_date":           "2021-01-01",
#                 "end_date":             "2023-12-29",
#                 "total_return_pct":     -29.99,
#                 "sharpe_ratio":         -4.83,
#                 "max_drawdown_pct":     -30.24,
#                 "win_rate_pct":         67.92,
#                 "total_trades":         53,
#                 "profit_factor":        1.94,
#                 "avg_holding_days":     3.4,
#                 "winning_trades":       36,
#                 "losing_trades":        17,
#                 "avg_win":              0.01,
#                 "avg_loss":            -0.01,
#                 "avg_risk_reward":      0.92,
#                 "volatility_annual_pct": 3.41,
#                 "sortino_ratio":        -5.08,
#                 "cagr_pct":            -10.87
#             }
#         }
#     })
 

#     strategy_type: str
#     metrics:       Dict[str, Any]


# class AnalyzeBacktestResponse(BaseModel):
#     """
#     Response model for backtest pass/fail analysis.
#     verdict is always "PASS" or "FAIL".
#     """
#     model_config = ConfigDict(json_schema_extra={
#         "example": {
#             "verdict":     "FAIL",
#             "explanation": "Your mean reversion strategy failed. The Sharpe of 0.3...",
#             "timestamp":   "2024-01-01T00:00:00"
#         }
#     })

#     verdict:     str    # "PASS" or "FAIL"
#     explanation: str    # educational explanation of why
#     timestamp:   str


























































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
