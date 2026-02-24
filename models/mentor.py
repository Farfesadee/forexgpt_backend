# from pydantic import BaseModel

# class MentorRequest(BaseModel):
#     question: str
#     context: str | None = None
#     user_id: str | None = None

# class MentorResponse(BaseModel):
#     answer: str
#     conversation_id: str | None = None

# class CodeGenRequest(BaseModel):
#     strategy_description: str
#     user_id: str | None = None

# class CodeGenResponse(BaseModel):
#     code: str
#     language: str = "python"
    
"""
models/mentor.py — Pydantic schemas for the Forex theory mentor module.

Covers:
  - api/routes/mentor.py        (request/response for all mentor endpoints)
  - services/mentor_service.py  (internal types for LLM pipeline)

Tables: public.mentor_conversations, public.mentor_messages
View:   public.mentor_history
"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Enums 

class DifficultyLevel(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"

class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"

# Conversation Schemas 

class ConversationCreate(BaseModel):
    """POST /mentor/conversations"""
    difficulty: DifficultyLevel = DifficultyLevel.INTERMEDIATE

    model_config = {"json_schema_extra": {"example": {
        "difficulty": "intermediate",
    }}}

class ConversationResponse(BaseModel):
    """Single conversation record."""
    id:              str
    user_id:         str
    title:           Optional[str]
    topic_tags:      List[str]
    difficulty:      DifficultyLevel
    message_count:   int
    is_archived:     bool
    last_message_at: Optional[datetime]
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}

class ConversationListItem(BaseModel):
    """
    Compact conversation row for the sidebar list.
    Sourced from the mentor_history VIEW which includes a response preview snippet.
    """
    id:                    str
    title:                 Optional[str]
    topic_tags:            List[str]
    difficulty:            DifficultyLevel
    message_count:         int
    is_archived:           bool
    last_message_at:       Optional[datetime]
    last_response_preview: Optional[str]   # first 140 chars of last assistant reply
    last_model_used:       Optional[str]   # e.g. 'mistral-7b-base'
    created_at:            datetime

    model_config = {"from_attributes": True}

class ConversationListResponse(BaseModel):
    items:           List[ConversationListItem]
    total:           int

# Message Schemas

class MentorAskRequest(BaseModel):
    """
    POST /mentor/conversations/{id}/messages
    The user's question to the Forex theory mentor.
    """
    question:     str = Field(..., min_length=3, max_length=2000,
                              description="The Forex or finance question to ask the mentor.")
    include_examples: bool = Field(True, description="Request a worked numerical example.")
    include_formulas: bool = Field(False, description="Request mathematical formulas where applicable.")

    model_config = {"json_schema_extra": {"example": {
        "question":          "What is the carry trade and what are its main risks?",
        "include_examples":  True,
        "include_formulas":  False,
    }}}

class MentorMessageResponse(BaseModel):
    """Single message row — returned after a question is answered."""
    id:                  str
    conversation_id:     str
    role:                MessageRole
    content:             str

    # Assistant-message metadata (None on user messages)
    topic_tags:          List[str]
    related_concepts:    List[str]
    follow_up_questions: List[str]
    system_prompt_key:   Optional[str]
    model_used:          Optional[str]
    adapter_used:        Optional[str]
    tokens_used:         Optional[int]
    latency_ms:          Optional[int]
    thumbs_up:           Optional[bool]

    created_at: datetime

    model_config = {"from_attributes": True}

class MentorAskResponse(BaseModel):
    """
    Response returned by POST /mentor/conversations/{id}/messages.
    Includes the saved user message + the assistant's answer.
    """
    user_message:      MentorMessageResponse
    assistant_message: MentorMessageResponse

class MessageFeedbackRequest(BaseModel):
    """PATCH /mentor/messages/{id}/feedback"""
    thumbs_up: bool = Field(..., description="True = helpful, False = not helpful.")

class MessageHistoryResponse(BaseModel):
    """GET /mentor/conversations/{id}/messages"""
    conversation_id: str
    messages:        List[MentorMessageResponse]

# Internal Service Schemas 
# Used by mentor_service.py — not exposed directly via API responses.

class LLMMessage(BaseModel):
    """
    OpenAI-style message dict passed to the Mistral/HF API.
    mentor_service.py builds a list of these from mentor_messages history.
    """
    role:    MessageRole
    content: str

class MentorLLMContext(BaseModel):
    """
    Complete context assembled by mentor_service.py before calling the LLM.
    Passed to core/llm_router.py for model selection and prompt building.
    """
    conversation_id:   str
    user_id:           str
    difficulty:        DifficultyLevel
    history:           List[LLMMessage]   # last N turns for context window
    new_question:      str
    include_examples:  bool
    include_formulas:  bool
    system_prompt_key: str                # resolved by llm_router.py from difficulty