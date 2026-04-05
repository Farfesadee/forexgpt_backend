

"""
routes/mentor_routes.py — FastAPI router for the Mentor module.

Endpoints
─────────
POST   /mentor/conversations                          start a generic conversation
POST   /mentor/conversations/{id}/messages            ask a question (generic or follow-up)
POST   /mentor/ask                                    compatibility endpoint (optional conversation_id in body)
GET    /mentor/conversations/{id}/messages            get conversation history
GET    /mentor/conversations/{id}                     legacy — returns empty history for new conversations
GET    /mentor/conversations/{user_id}/{id}           legacy — user-scoped path
GET    /mentor/conversations                          list user's conversations
DELETE /mentor/conversations/{id}                     delete a conversation
DELETE /mentor/conversations/{user_id}/{id}           legacy — user-scoped path
POST   /mentor/backtest-conversations                 seed a backtest conversation
POST   /mentor/ask/stream                             SSE streaming endpoint

Auth: uses get_current_user from api.middleware.auth_middleware
      user_id is extracted from the JWT token — not from the request body
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import uuid

from models.mentor import (
    AskQuestionRequest,
    AskQuestionResponse,
    ConversationHistoryResponse,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    DeleteConversationResponse,
    StartBacktestConversationRequest,
    StartBacktestConversationResponse,
)
from models.user import JWTPayload
from services.mentor_service import MentorService
from core.dependencies import get_mentor_service
from api.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/mentor", tags=["mentor"])


# ---------------------------------------------------------------------------
# Helper — prevents users from accessing other users' conversations
# ---------------------------------------------------------------------------

def _assert_user_access(requested_user_id: str, user: JWTPayload) -> None:
    if requested_user_id != user.user_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access mentor conversations for your own account.",
        )


# ---------------------------------------------------------------------------
# Generic conversation endpoints
# ---------------------------------------------------------------------------

@router.post("/conversations", response_model=AskQuestionResponse)
async def start_conversation(
    request: AskQuestionRequest,
    user:    JWTPayload    = Depends(get_current_user),
    service: MentorService = Depends(get_mentor_service),
):
    """Start a new generic mentor conversation."""
    try:
        result = await service.ask_question(
            user_id         = user.user_id,
            message         = request.message,
            conversation_id = None,
        )
        return AskQuestionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{conversation_id}/messages", response_model=AskQuestionResponse)
async def ask_question(
    conversation_id: str,
    request:         AskQuestionRequest,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """
    Ask a question in an existing conversation.
    Works for both generic and backtest follow-up conversations.
    The mentor loads full conversation history so follow-ups have complete context.
    """
    try:
        result = await service.ask_question(
            user_id         = user.user_id,
            message         = request.message,
            conversation_id = conversation_id,
        )
        return AskQuestionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask", response_model=AskQuestionResponse)
async def ask_question_simple(
    request: AskQuestionRequest,
    user:    JWTPayload    = Depends(get_current_user),
    service: MentorService = Depends(get_mentor_service),
):
    """
    Compatibility endpoint — conversation_id is optional in the request body.
    Continues an existing conversation if provided, otherwise starts a new one.
    """
    try:
        result = await service.ask_question(
            user_id         = user.user_id,
            message         = request.message,
            conversation_id = request.conversation_id,
        )
        return AskQuestionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Conversation history endpoints
# ---------------------------------------------------------------------------

@router.get("/conversations/{conversation_id}/messages", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: str,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """Retrieve full message history for a conversation."""
    try:
        history = service.get_conversation_history(conversation_id, user.user_id)
        if history is None:
            raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
        return ConversationHistoryResponse(
            conversation_id = conversation_id,
            history         = [ConversationMessageResponse(**m) for m in history],
            message_count   = len(history),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}", response_model=ConversationHistoryResponse, include_in_schema=False)
async def get_conversation_history_legacy(
    conversation_id: str,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """
    Legacy endpoint — returns empty history for a brand-new conversation
    instead of failing the page.
    """
    try:
        history = service.get_conversation_history(conversation_id, user.user_id)
        if history is None:
            history = []
        return ConversationHistoryResponse(
            conversation_id = conversation_id,
            history         = [ConversationMessageResponse(**m) for m in history],
            message_count   = len(history),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{user_id}/{conversation_id}", response_model=ConversationHistoryResponse, include_in_schema=False)
async def get_conversation_history_user_scoped_legacy(
    conversation_id: str,
    user_id:         str,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """Legacy endpoint with user_id in the path."""
    try:
        _assert_user_access(user_id, user)
        history = service.get_conversation_history(conversation_id, user.user_id)
        if history is None:
            history = []
        return ConversationHistoryResponse(
            conversation_id = conversation_id,
            history         = [ConversationMessageResponse(**m) for m in history],
            message_count   = len(history),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# List conversations
# ---------------------------------------------------------------------------

@router.get("/conversations", response_model=list[ConversationSummaryResponse])
async def list_conversations(
    limit:   int           = 20,
    user:    JWTPayload    = Depends(get_current_user),
    service: MentorService = Depends(get_mentor_service),
):
    """List all conversations for a user (generic + backtest, newest first)."""
    try:
        conversations = service.list_user_conversations(user.user_id, limit)
        return [ConversationSummaryResponse(**c) for c in conversations]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Delete conversation
# ---------------------------------------------------------------------------

@router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    conversation_id: str,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """Delete a conversation and all its messages."""
    try:
        deleted = service.delete_conversation(conversation_id, user.user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
        return DeleteConversationResponse(
            message         = "Conversation deleted successfully.",
            conversation_id = conversation_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversations/{user_id}/{conversation_id}", response_model=DeleteConversationResponse, include_in_schema=False)
async def delete_conversation_user_scoped_legacy(
    conversation_id: str,
    user_id:         str,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """Legacy endpoint with user_id in the path."""
    try:
        _assert_user_access(user_id, user)
        deleted = service.delete_conversation(conversation_id, user.user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
        return DeleteConversationResponse(
            message         = "Conversation deleted successfully.",
            conversation_id = conversation_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Backtest-seeded conversation
# ---------------------------------------------------------------------------

@router.post("/backtest-conversations", response_model=StartBacktestConversationResponse)
async def start_backtest_conversation(
    request: StartBacktestConversationRequest,
    user:    JWTPayload    = Depends(get_current_user),
    service: MentorService = Depends(get_mentor_service),
):
    """
    Seed a new mentor conversation with full backtest context.
    Returns an initial analysis + conversation_id for follow-up questions via
    POST /mentor/conversations/{conversation_id}/messages
    """
    try:
        result = await service.start_backtest_conversation(
            user_id          = user.user_id,
            backtest_context = request.backtest_context,
        )
        return StartBacktestConversationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Streaming endpoint — SSE (text/event-stream)
# ---------------------------------------------------------------------------

class AskStreamRequest(BaseModel):
    message:         str
    conversation_id: Optional[str] = None


@router.post("/ask/stream")
async def ask_stream(
    request: AskStreamRequest,
    user:    JWTPayload    = Depends(get_current_user),
    service: MentorService = Depends(get_mentor_service),
):
    """
    Stream an AI mentor response as Server-Sent Events (SSE).

    Request body: { "message": "...", "conversation_id": "..." (optional) }

    Each SSE frame:  data: "json-encoded text chunk"\\n\\n
    Final frame:     data: [DONE]\\n\\n

    Chunks are JSON-encoded so embedded newlines in markdown are safe.
    The X-Conversation-Id response header carries the conversation_id
    so the client can store it for follow-up questions.
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())

    async def event_generator():
        try:
            async for chunk in service.ask_question_stream(
                user_id         = user.user_id,
                message         = request.message,
                conversation_id = conversation_id,
            ):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":                 "no-cache",
            "X-Accel-Buffering":             "no",
            "Access-Control-Allow-Origin":   "*",
            "Access-Control-Expose-Headers": "X-Conversation-Id",
            "X-Conversation-Id":             conversation_id,
        },
    )