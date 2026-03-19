
"""
Pydantic schemas for CodeGen Service
Request and Response models for code generation endpoints
"""

from pydantic import BaseModel
from typing import Optional


# ============================================================================
# REQUEST MODELS
# ============================================================================

class GenerateCodeRequest(BaseModel):
    """Request model for code generation"""
    user_id: Optional[str] = None
    strategy_description: str
    conversation_id: Optional[str] = None
    previous_code: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "strategy_description": "Create a mean reversion strategy using RSI. Buy when RSI < 30, sell when RSI > 70.",
                "conversation_id": None,
                "previous_code": None,
                "error_message": None
            }
        }

class ImproveStrategyRequest(BaseModel):
    """Request model for strategy improvement"""
    user_id: Optional[str] = None
    original_code: str
    backtest_results: dict
    mentor_analysis: str
    additional_requirements: Optional[str] = None
    conversation_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "original_code": "def generate_signals(data): ...",
                "backtest_results": {
                    "strategy_name": "custom",
                    "pair": "EURUSD",
                    "start_date": "2021-01-01",
                    "end_date": "2023-12-29",
                    "total_return_pct": -29.99,
                    "sharpe_ratio": -4.83,
                    "max_drawdown_pct": -30.24,
                    "win_rate_pct": 67.92,
                    "total_trades": 53,
                    "profit_factor": 1.94,
                    "sortino_ratio": -5.08,
                    "cagr_pct": -10.87
                },
                "mentor_analysis": "Strategy failed because it trades into trends...",
                "additional_requirements": "Also add time-based filters",
                "conversation_id": None
            }
        }

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class GenerateCodeResponse(BaseModel):
    """Response model for generated code"""
    code: str
    explanation: str
    conversation_id: str
    language: str
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "code": "import pandas as pd\nimport numpy as np\n...",
                "explanation": "This strategy uses RSI to identify mean reversion opportunities...",
                "conversation_id": "uuid-here",
                "language": "python",
                "timestamp": "2024-01-01T00:00:00"
            }
        }


class GeneratedCodeSummaryResponse(BaseModel):
    """Response model for a code summary in list"""
    id: str
    conversation_id: str
    description: str
    created_at: str


class GeneratedCodeDetailResponse(BaseModel):
    """Response model for full generated code details"""
    id: str
    conversation_id: str
    code: str
    description: str
    created_at: str


class CodeConversationMessageResponse(BaseModel):
    """Single message in a code generation conversation"""
    role: str
    content: str
    timestamp: Optional[str] = None
    code: Optional[str] = None


class CodeConversationHistoryResponse(BaseModel):
    """Response model for code generation conversation history"""
    conversation_id: str
    history: list[CodeConversationMessageResponse]

class ImproveStrategyResponse(BaseModel):
    """Response model for improved strategy code"""
    code: str
    explanation: str
    conversation_id: str
    code_id: Optional[str] = None
    language: str
    timestamp: str