from pydantic import BaseModel

class SignalRequest(BaseModel):
    pair: str
    timeframe: str
    prompt: str