# from pydantic import BaseModel
# from typing import Literal

# class QuantAskRequest(BaseModel):
#     question: str
#     topic_id: str | None = None
#     conversation_history: list[dict] | None = None
#     user_id: str | None = None

# class QuantAskResponse(BaseModel):
#     answer: str
#     topic_id: str | None = None
#     related_topics: list[str] = []
#     conversation_id: str | None = None

# class QuantTopic(BaseModel):
#     id: str
#     title: str
#     difficulty: Literal["beginner", "intermediate", "advanced"]
#     category: str
#     description: str

# class QuantSearchResponse(BaseModel):
#     results: list[QuantTopic]
#     total: int

# class QuantInteractiveRequest(BaseModel):
#     topic_id: str
#     message: str
#     history: list[dict] | None = None
#     user_id: str | None = None

"""
models/quant_finance.py — Pydantic schemas for the quantitative finance module.

Covers:
  - api/routes/quant_finance.py         (all quant endpoints)
  - services/quant_finance_service.py   (internal LLM pipeline types)

Tables: public.quant_sessions, public.quant_messages
View:   public.quant_history

Quant finance is deliberately separate from the Forex theory mentor because:
  - Different system prompt in core/system_prompts.py
  - llm_router.py may route to a different adapter based on quant_domain
  - Responses include LaTeX formulas and code snippets → different rendering
  - Independent usage counter: quant_questions_asked (vs mentor_questions_asked)
"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

#  Enums

class QuantDomain(str, Enum):
    """
    Sub-domain of quantitative finance.
    Stored in quant_sessions.quant_domain — read by llm_router.py to
    select the most appropriate system prompt key and adapter.
    """
    GENERAL              = "general"            # catch-all
    STATISTICS           = "statistics"         # Sharpe, Sortino, distributions, correlation
    DERIVATIVES          = "derivatives"        # options pricing, Greeks, vol surface
    RISK_MODELS          = "risk_models"        # VaR, CVaR, drawdown, stress testing
    TIME_SERIES          = "time_series"        # ARIMA, GARCH, cointegration, regime detection
    PORTFOLIO            = "portfolio"          # MPT, Kelly criterion, position sizing
    MARKET_MICROSTRUCTURE = "market_microstructure"  # order flow, liquidity, slippage, market impact

class DifficultyLevel(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"

class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"

# Session Schemas 

class QuantSessionCreate(BaseModel):
    """POST /quant/sessions"""
    quant_domain: QuantDomain     = QuantDomain.GENERAL
    difficulty:   DifficultyLevel = DifficultyLevel.INTERMEDIATE

    model_config = {"json_schema_extra": {"example": {
        "quant_domain": "statistics",
        "difficulty":   "intermediate",
    }}}

class QuantSessionResponse(BaseModel):
    """Single quant session record."""
    id:              str
    user_id:         str
    title:           Optional[str]
    topic_tags:      List[str]
    quant_domain:    QuantDomain
    difficulty:      DifficultyLevel
    message_count:   int
    is_archived:     bool
    last_message_at: Optional[datetime]
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}

class QuantSessionListItem(BaseModel):
    """
    Compact session row for the sidebar list.
    Sourced from the quant_history VIEW.
    """
    id:                    str
    title:                 Optional[str]
    topic_tags:            List[str]
    quant_domain:          QuantDomain
    difficulty:            DifficultyLevel
    message_count:         int
    is_archived:           bool
    last_message_at:       Optional[datetime]
    last_response_preview: Optional[str]   # 140-char snippet of last assistant reply
    last_prompt_key:       Optional[str]   # e.g. 'quant_statistics_advanced'
    created_at:            datetime

    model_config = {"from_attributes": True}

class QuantSessionListResponse(BaseModel):
    items: List[QuantSessionListItem]
    total: int

class QuantDomainStat(BaseModel):
    """One row from get_quant_domain_stats() RPC — per-domain usage breakdown."""
    quant_domain:  QuantDomain
    session_count: int
    message_count: int
    last_active:   Optional[datetime]

# Message Schemas

class QuantAskRequest(BaseModel):
    """
    POST /quant/sessions/{id}/messages
    The user's quantitative finance question.

    quant_domain is optional — if provided it overrides the session domain
    for this message and can trigger a different adapter in llm_router.py.
    """
    question:          str = Field(..., min_length=3, max_length=3000)
    quant_domain:      Optional[QuantDomain] = None   # override for this message only
    show_derivation:   bool = Field(False, description="Ask the model to show step-by-step mathematical derivation.")
    include_python:    bool = Field(False, description="Ask the model to include a runnable Python example.")
    notation_style:    str  = Field("standard", pattern="^(standard|latex|plain)$",
                                    description="Math notation style: 'standard' (markdown), 'latex' (KaTeX), 'plain' (no symbols).")

    model_config = {"json_schema_extra": {"example": {
        "question":        "Derive the Sharpe ratio and explain when it's misleading for Forex strategies.",
        "show_derivation": True,
        "include_python":  True,
        "notation_style":  "latex",
    }}}

class QuantMessageResponse(BaseModel):
    """Single quant message record."""
    id:         str
    session_id: str
    role:       MessageRole
    content:    str

    # Math and code content flags (used by frontend for rendering)
    contains_formula:  bool
    formula_latex:     List[str]   # extracted LaTeX strings for KaTeX rendering
    contains_code:     bool
    code_snippets:     List[str]   # extracted Python code blocks

    # LLM routing metadata
    system_prompt_key: Optional[str]   # e.g. 'quant_statistics_advanced'
    model_used:        Optional[str]
    adapter_used:      Optional[str]
    tokens_used:       Optional[int]
    latency_ms:        Optional[int]
    thumbs_up:         Optional[bool]

    created_at: datetime

    model_config = {"from_attributes": True}

class QuantAskResponse(BaseModel):
    """Response from POST /quant/sessions/{id}/messages."""
    user_message:      QuantMessageResponse
    assistant_message: QuantMessageResponse

class QuantMessageFeedbackRequest(BaseModel):
    """PATCH /quant/messages/{id}/feedback"""
    thumbs_up: bool

class QuantMessageHistoryResponse(BaseModel):
    """GET /quant/sessions/{id}/messages"""
    session_id: str
    messages:   List[QuantMessageResponse]

# Internal Service Schemas 
# Used by quant_finance_service.py — not exposed via API.

class LLMMessage(BaseModel):
    """OpenAI-style message dict sent to the LLM."""
    role:    MessageRole
    content: str

class QuantLLMContext(BaseModel):
    """
    Complete context assembled by quant_finance_service.py before calling llm_router.py.
    The router reads quant_domain + difficulty to select the right system prompt key
    and adapter from core/system_prompts.py.
    """
    session_id:       str
    user_id:          str
    quant_domain:     QuantDomain
    difficulty:       DifficultyLevel
    history:          List[LLMMessage]
    new_question:     str
    show_derivation:  bool
    include_python:   bool
    notation_style:   str
    system_prompt_key: str    # e.g. 'quant_statistics_intermediate'

class ParsedQuantResponse(BaseModel):
    """
    Parsed LLM output from quant_finance_service.py.
    The service extracts LaTeX and code blocks before saving to DB.
    """
    content:          str
    formula_latex:    List[str] = Field(default_factory=list)
    code_snippets:    List[str] = Field(default_factory=list)
    contains_formula: bool = False
    contains_code:    bool = False

    @field_validator("contains_formula", mode="before")
    @classmethod
    def set_contains_formula(cls, v, info) -> bool:
        if "formula_latex" in info.data:
            return len(info.data["formula_latex"]) > 0
        return v

    @field_validator("contains_code", mode="before")
    @classmethod
    def set_contains_code(cls, v, info) -> bool:
        if "code_snippets" in info.data:
            return len(info.data["code_snippets"]) > 0
        return v