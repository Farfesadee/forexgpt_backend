# from pydantic import BaseModel
# from datetime import datetime

# class SignalExtractRequest(BaseModel):
#     transcript: str
#     user_id: str | None = None

# class SignalResult(BaseModel):
#     currency_pair: str
#     direction: str        # "LONG" or "SHORT"
#     confidence: float     # 0.0 – 1.0
#     reasoning: str
#     magnitude: str        # "low", "moderate", "high"
#     time_horizon: str     # e.g. "next_quarter"

# class SignalExtractResponse(BaseModel):
#     signal: SignalResult
#     signal_id: str | None = None
#     created_at: datetime | None = None


"""
models/signal.py — Pydantic schemas for the signal extraction module.

Covers:
  - api/routes/signals.py   (request/response for all signal endpoints)
  - services/signal_service.py  (internal types passed between service and route)
  - core/hf_client.py       (HuggingFace endpoint request/response shapes)

Table: public.signals
"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# Enums 

class SourceType(str, Enum):
    CENTRAL_BANK    = "central_bank"     # Fed, ECB, BoJ, BoE speeches/minutes
    EARNINGS_CALL   = "earnings_call"    # multinational corp with FX exposure
    ECONOMIC_REPORT = "economic_report"  # NFP, CPI, GDP releases
    NEWS            = "news"             # financial news articles


class Signal(str, Enum):
    TRUE = "true"   
    FALSE  = "false"    
    NEUTRAL = "neutral"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class Magnitude(str, Enum):
    HIGH   = "high"
    MODERATE = "moderate"
    LOW     = "low"


class Time_Horizon(str, Enum):
    CURRENT_QUARTER  = "current_quarter"   
    LONG_TERM   = "long_term" 
    NEXT_QUARTER   = "next_quarter"    


# HuggingFace Client Schemas 
# Used internally by core/hf_client.py

class HFExtractionRequest(BaseModel):
    """
    Payload sent to the fine-tuned HuggingFace inference endpoint.
    Formatted by signal_service.py before calling hf_client.py.
    """
    text:          str = Field(..., min_length=50, max_length=8000)
    source_type:   SourceType
    base_currency: Optional[str] = Field(None, min_length=2, max_length=4)
    max_new_tokens: int = Field(512, ge=64, le=1024)
    temperature:    float = Field(0.1, ge=0.0, le=1.0)


class HFExtractionResponse(BaseModel):
    """Raw response from the HF endpoint before signal_service.py normalises it."""
    generated_text: str
    endpoint_id:    Optional[str] = None
    model_version:  Optional[str] = None
    latency_ms:     Optional[int] = None


# Core Signal Data 

class ExtractedSignal(BaseModel):
    """
    A single directional signal extracted from a source document.
    One extraction run may produce multiple signals (e.g. hawkish on USD, bearish on EUR).
    Stored as items in signals.extraction_result JSONB array.
    """
    signal:        Signal
    direction:        Direction
    magnitude:         Magnitude
    confidence:       float = Field(..., ge=0.0, le=1.0)
    current_pair:   List[str] = Field(..., min_length=1)
    key_phrases:      List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None   # plain-English explanation for the student
    time_horizon:     Time_Horizon = Time_Horizon.NEXT_QUARTER

    @field_validator("affected_pairs")
    @classmethod
    def validate_pairs(cls, pairs: List[str]) -> List[str]:
        """Normalise pair format: EUR/USD, USD/JPY, etc."""
        normalised = []
        for p in pairs:
            p = p.upper().strip()
            if len(p) == 6 and "/" not in p:
                p = f"{p[:3]}/{p[3:]}"  # EURUSD → EUR/USD
            normalised.append(p)
        return normalised

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 3)

class ExtractionResult(BaseModel):
    """
    Full result of one signal extraction run.
    Stored as signals.extraction_result JSONB.
    """
    signals:       List[ExtractedSignal] = Field(..., min_length=1)
    summary:       str                   # 1-2 sentence plain-English summary
    macro_context: Optional[str] = None  # broader economic context
    risk_factors:  List[str] = Field(default_factory=list)

    @property
    def primary_signal(self) -> ExtractedSignal:
        """The highest-confidence signal — used for denormalized DB columns."""
        return max(self.signals, key=lambda s: s.confidence)

# API Request Schemas

class SignalExtractionRequest(BaseModel):
    """POST /signals/extract"""
    source_text:   str = Field(..., min_length=50, max_length=8000,
                               description="The transcript, report, or article to analyse.")
    source_type:   SourceType = SourceType.CENTRAL_BANK
    source_label:  Optional[str] = Field(None, max_length=200,
                                          description="Human-readable label, e.g. 'Fed FOMC Minutes June 2024'.")
    base_currency: Optional[str] = Field(None, min_length=2, max_length=4,
                                          description="Primary currency of the source. Hint for the model.")

    model_config = {"json_schema_extra": {"example": {
        "source_text":   "The Committee decided to maintain the federal funds rate...",
        "source_type":   "central_bank",
        "source_label":  "Fed FOMC Statement June 2024",
        "base_currency": "USD",
    }}}

class SignalUpdateRequest(BaseModel):
    """PATCH /signals/{id}"""
    is_saved:   Optional[bool] = None
    is_shared:  Optional[bool] = None
    user_notes: Optional[str]  = Field(None, max_length=2000)


class SignalFilterParams(BaseModel):
    """Query parameters for GET /signals"""
    source_type:  Optional[SourceType]    = None
    signal:    Optional[Signal]     = None
    direction:    Optional[Direction]     = None
    pair:         Optional[str]           = None
    saved_only:   bool                    = False
    limit:        int                     = Field(20, ge=1, le=100)
    offset:       int                     = Field(0, ge=0)

# API Response Schemas 

class SignalResponse(BaseModel):
    """Single signal record returned from the DB."""
    id:               str
    user_id:          str
    source_type:      SourceType
    source_label:     Optional[str]
    base_currency:    Optional[str]
    source_text:      str

    extraction_result: ExtractionResult

    # Denormalized top-signal fields (fast filtering)
    signal:  Optional[Signal]
    direction:  Optional[Direction]
    magnitude:   Optional[Magnitude]
    currency_pair:     List[str]
    confidence:         Optional[float]
    reasoning:        Optional[str]
    time_horizon: Optional[str]

    # HF model tracing
    hf_endpoint_id:      Optional[str]
    hf_model_version:    Optional[str]
    inference_latency_ms: Optional[int]
    is_hf_fallback:      bool = False

    is_saved:   bool = False
    is_shared:  bool = False
    user_notes: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SignalListItem(BaseModel):
    """Compact signal row for list views (GET /signals)."""
    id:               str
    source_type:      SourceType
    source_label:     Optional[str]
    base_currency:    Optional[str]
    magnitude: Optional[Magnitude]
    direction: Optional[Direction]
    reasoning:  Optional[str]
    currency_pair:    List[str]
    confidence:        Optional[float]
    time_horizon: Optional[str]
    hf_endpoint_id:    Optional[str]
    hf_model_version:  Optional[str]
    is_saved:          bool
    created_at:        datetime

    model_config = {"from_attributes": True}


class SignalListResponse(BaseModel):
    """Paginated signal list."""
    items:  List[SignalListItem]
    total:  int
    limit:  int
    offset: int