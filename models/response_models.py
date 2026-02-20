from pydantic import BaseModel

class SignalResponse(BaseModel):
    pair: str
    timeframe: str
    signal: str
    confidence: float
    reasoning: str