from pydantic import BaseModel
from datetime import datetime


class SignalExtractRequest(BaseModel):
    transcript: str
    user_id: str | None = None


class SignalResult(BaseModel):
    currency_pair: str
    direction: str        # "LONG" or "SHORT"
    confidence: float     # 0.0 – 1.0
    reasoning: str
    magnitude: str        # "low", "moderate", "high"
    time_horizon: str     # e.g. "next_quarter"


class SignalExtractResponse(BaseModel):
    signal: SignalResult
    signal_id: str | None = None
    created_at: datetime | None = None