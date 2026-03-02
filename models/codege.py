
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
    user_id: str
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


class CodeConversationHistoryResponse(BaseModel):
    """Response model for code generation conversation history"""
    conversation_id: str
    history: list[CodeConversationMessageResponse]