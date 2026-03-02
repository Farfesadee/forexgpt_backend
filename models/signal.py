"""
Pydantic schemas for Signal Service
Request and Response models for signal extraction endpoints
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ============================================================================
# REQUEST MODELS
# ============================================================================

class ExtractSignalRequest(BaseModel):
    """Request model for single signal extraction"""
    user_id: str
    transcript: str
    company_name: Optional[str] = None
    save_to_db: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "transcript": "In Q1, we experienced a 4% revenue headwind from currency movements, primarily due to USD strength versus EUR...",
                "company_name": "Microsoft",
                "save_to_db": True
            }
        }


class BatchExtractRequest(BaseModel):
    """Request model for batch signal extraction"""
    user_id: str
    transcripts: list[dict]  # List of {"text": "...", "company_name": "..."}
    save_to_db: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "transcripts": [
                    {"text": "transcript text here...", "company_name": "Microsoft"},
                    {"text": "another transcript...", "company_name": "Apple"}
                ],
                "save_to_db": True
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class SignalResponse(BaseModel):
    """Response model for an extracted signal"""
    signal: bool
    currency_pair: Optional[str] = None
    direction: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reasoning: str
    magnitude: Optional[str] = None
    time_horizon: Optional[str] = None
    company_name: Optional[str] = None
    raw_response: Optional[str] = None
    signal_id: Optional[str] = None
    timestamp: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "signal": True,
                "currency_pair": "EUR/USD",
                "direction": "SHORT",
                "confidence": 0.7,
                "reasoning": "Company reported 4% revenue headwind from USD strength vs EUR.",
                "magnitude": "moderate",
                "time_horizon": "current_quarter",
                "company_name": "Microsoft",
                "signal_id": "uuid-here",
                "timestamp": "2024-01-01T00:00:00"
            }
        }


class BatchSignalResponse(BaseModel):
    """Response model for batch signal extraction"""
    signals: list[SignalResponse]
    total: int
    signals_found: int


class SavedSignalResponse(BaseModel):
    """Response model for a saved signal retrieved from DB"""
    signal_id: str
    currency_pair: Optional[str] = None
    direction: Optional[str] = None
    confidence: Optional[float] = None
    reasoning: str
    magnitude: Optional[str] = None
    time_horizon: Optional[str] = None
    company_name: Optional[str] = None
    created_at: str


class SignalStatisticsResponse(BaseModel):
    """Response model for signal statistics"""
    total_signals: int
    by_currency_pair: dict
    by_direction: dict
    by_magnitude: dict
    average_confidence: float


class DeleteSignalResponse(BaseModel):
    """Response model for signal deletion"""
    message: str
    signal_id: str