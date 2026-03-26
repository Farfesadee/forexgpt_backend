# """
# API Routes for Mentor Service
# Handles all mentor endpoints including signal-contextual Q&A
# and backtest analysis.
# """
# from services.mentor_service import MentorService
# service = MentorService()
# from fastapi import APIRouter, HTTPException
# from models.mentor import (
#     AskQuestionRequest,
#     AskQuestionResponse,
#     AnalyzeBacktestRequest,
#     AnalyzeBacktestResponse,
#     ConversationHistoryResponse,
#     ConversationMessageResponse,
#     ConversationSummaryResponse,
#     DeleteConversationResponse,
# )

# router = APIRouter(prefix="/mentor", tags=["Mentor"])

# # service is injected via dependency injection in your app setup
# # from core.dependencies import get_mentor_service
# # service = get_mentor_service()


# # ============================================================================
# # ASK QUESTION
# # ============================================================================

# @router.post("/conversations/ask", response_model=AskQuestionResponse)
# async def ask_question(request: AskQuestionRequest):
#     """
#     Ask the mentor a question.

#     - If conversation_id is None and signal_context is provided,
#       a new signal-linked conversation is created and the system
#       prompt is augmented with the signal details.

#     - If conversation_id is provided, the question is added to
#       the existing conversation (signal context already injected
#       at creation time).
#     """
#     try:
#         result = await service.ask_question(
#             user_id=request.user_id,
#             message=request.message,
#             conversation_id=request.conversation_id,
#             signal_context=request.signal_context.model_dump()
#             if request.signal_context
#             else None,
#         )
#         return AskQuestionResponse(**result)

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================================
# # ANALYZE BACKTEST
# # ============================================================================

# @router.post("/analyze-backtest", response_model=AnalyzeBacktestResponse)
# async def analyze_backtest(request: AnalyzeBacktestRequest):
#     """
#     Analyze backtest results in the context of the signal that was tested.

#     The analysis is saved to the signal's mentor conversation so the
#     user can refer back to it. Triggers for any result — good or bad.
#     """
#     try:
#         result = await service.analyze_backtest_results(
#             user_id=request.user_id,
#             conversation_id=request.conversation_id,
#             signal_context=request.signal_context.model_dump(),
#             strategy_type=request.strategy_type,
#             results=request.results,
#             strategy_code=request.strategy_code,
#         )
#         return AnalyzeBacktestResponse(**result)

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================================
# # CONVERSATION HISTORY
# # ============================================================================

# @router.get(
#     "/conversations/{conversation_id}/messages",
#     response_model=ConversationHistoryResponse,
# )
# async def get_conversation_history(conversation_id: str, user_id: str):
#     """
#     Retrieve the full message history for a conversation.
#     """
#     try:
#         history = service.get_conversation_history(
#             conversation_id=conversation_id,
#             user_id=user_id,
#         )
#         if history is None:
#             raise HTTPException(status_code=403, detail="Unauthorized")

#         return ConversationHistoryResponse(
#             conversation_id=conversation_id,
#             history=[ConversationMessageResponse(**m) for m in history],
#             message_count=len(history),
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================================
# # LIST CONVERSATIONS
# # ============================================================================

# @router.get("/conversations", response_model=list[ConversationSummaryResponse])
# async def list_conversations(user_id: str, limit: int = 20):
#     """
#     List all conversations for a user (most recent first).
#     Includes signal_id when the conversation was launched from a signal.
#     """
#     try:
#         conversations = service.list_user_conversations(
#             user_id=user_id,
#             limit=limit,
#         )
#         return [ConversationSummaryResponse(**c) for c in conversations]

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================================
# # DELETE CONVERSATION
# # ============================================================================

# @router.delete(
#     "/conversations/{conversation_id}",
#     response_model=DeleteConversationResponse,
# )
# async def delete_conversation(conversation_id: str, user_id: str):
#     """
#     Archive a conversation so it no longer appears in the user's list.
#     """
#     try:
#         deleted = service.delete_conversation(
#             conversation_id=conversation_id,
#             user_id=user_id,
#         )
#         if not deleted:
#             raise HTTPException(status_code=404, detail="Conversation not found")

#         return DeleteConversationResponse(
#             message="Conversation archived successfully",
#             conversation_id=conversation_id,
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))















# """
# API Routes for Mentor Service
# All endpoints are protected by JWT authentication.
# user_id is not required in request bodies — auth is token-based only.
# """

# from fastapi import APIRouter, Depends, HTTPException
# from core.dependencies import verify_token, get_mentor_service
# from services.mentor_service import MentorService
# from models.mentor import (
#     AskQuestionRequest,
#     AskQuestionResponse,
#     AnalyzeBacktestRequest,
#     AnalyzeBacktestResponse,
#     ConversationHistoryResponse,
#     ConversationMessageResponse,
#     ConversationSummaryResponse,
#     DeleteConversationResponse,
# )

# router = APIRouter(
#     prefix="/mentor",
#     tags=["Mentor"],
#     dependencies=[Depends(verify_token)],   # JWT required on ALL routes
# )


# # ============================================================================
# # ASK QUESTION
# # ============================================================================

# @router.post("/conversations/ask", response_model=AskQuestionResponse)
# async def ask_question(
#     request: AskQuestionRequest,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """
#     Ask the mentor a question.

#     - Pass signal_context + no conversation_id to start a new signal-linked session.
#     - Pass conversation_id alone to continue an existing conversation.
#     """
#     try:
#         result = await service.ask_question(
#             message=request.message,
#             conversation_id=request.conversation_id,
#             signal_context=request.signal_context.model_dump()
#             if request.signal_context
#             else None,
#         )
#         return AskQuestionResponse(**result)

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================================
# # ANALYZE BACKTEST
# # ============================================================================

# @router.post("/analyze-backtest", response_model=AnalyzeBacktestResponse)
# async def analyze_backtest(
#     request: AnalyzeBacktestRequest,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """
#     Analyze backtest results in the context of the signal that was tested.
#     Analysis is saved to the signal's mentor conversation.
#     """
#     try:
#         result = await service.analyze_backtest_results(
#             conversation_id=request.conversation_id,
#             signal_context=request.signal_context.model_dump(),
#             strategy_type=request.strategy_type,
#             results=request.results,
#             strategy_code=request.strategy_code,
#         )
#         return AnalyzeBacktestResponse(**result)

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ============================================================================
# # CONVERSATION HISTORY
# # ============================================================================

# @router.get(
#     "/conversations/{conversation_id}/messages",
#     response_model=ConversationHistoryResponse,
# )
# async def get_conversation_history(
#     conversation_id: str,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """Retrieve the full message history for a conversation."""
#     try:
#         history = service.get_conversation_history(conversation_id=conversation_id)
#         if history is None:
#             raise HTTPException(status_code=404, detail="Conversation not found")

#         return ConversationHistoryResponse(
#             conversation_id=conversation_id,
#             history=[ConversationMessageResponse(**m) for m in history],
#             message_count=len(history),
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.get("/conversations", response_model=list[ConversationSummaryResponse])
# async def list_conversations(
#     limit: int = 20,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """List all conversations (most recent first)."""
#     try:
#         conversations = service.list_user_conversations(limit=limit)
#         return [ConversationSummaryResponse(**c) for c in conversations]

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.delete(
#     "/conversations/{conversation_id}",
#     response_model=DeleteConversationResponse,
# )
# async def delete_conversation(
#     conversation_id: str,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """Archive a conversation so it no longer appears in the user's list."""
#     try:
#         deleted = service.delete_conversation(conversation_id=conversation_id)
#         if not deleted:
#             raise HTTPException(status_code=404, detail="Conversation not found")

#         return DeleteConversationResponse(
#             message="Conversation archived successfully",
#             conversation_id=conversation_id,
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))













































# old mentor_routes.py without dev-mode edits:

# """
# routes/mentor.py — FastAPI router for the Mentor module.

# Endpoints
# ─────────
# POST   /mentor/conversations                        start a generic conversation
# POST   /mentor/conversations/{id}/messages          ask a question (generic or follow-up)
# GET    /mentor/conversations/{id}/messages          get conversation history
# GET    /mentor/conversations                        list user's conversations
# DELETE /mentor/conversations/{id}                   delete a conversation

# POST   /mentor/backtest-conversations               seed a backtest conversation   ← NEW
#                                                     (called by backtest service)
# """

# from fastapi import APIRouter, HTTPException, Depends
# from datetime import datetime, timezone

# from models.mentor import (
#     AskQuestionRequest,
#     AskQuestionResponse,
#     ConversationHistoryResponse,
#     ConversationMessageResponse,
#     ConversationSummaryResponse,
#     DeleteConversationResponse,
#     StartBacktestConversationRequest,
#     StartBacktestConversationResponse,
#     AnalyzeBacktestRequest,
#     AnalyzeBacktestResponse,
# )
# from services.mentor_service import MentorService
# from core.dependencies import get_mentor_service, get_current_user_id

# router = APIRouter(prefix="/mentor", tags=["mentor"])


# # ---------------------------------------------------------------------------
# # Generic conversation endpoints
# # ---------------------------------------------------------------------------

# @router.post("/conversations", response_model=AskQuestionResponse)
# async def start_conversation(
#     request: AskQuestionRequest,
#     user_id: str = Depends(get_current_user_id),   # ← from token
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """Start a new generic mentor conversation."""
#     try:
#         result = await service.ask_question(
#             user_id         = request.user_id,
#             message         = request.message,
#         )
#         return AskQuestionResponse(**result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.post("/conversations/{conversation_id}/messages", response_model=AskQuestionResponse)
# async def ask_question(
#     conversation_id: str,
#     request:         AskQuestionRequest,
#     service:         MentorService = Depends(get_mentor_service),
# ):
#     """
#     Ask a question in an existing conversation.

#     Works for both generic conversations and backtest follow-ups.
#     When the conversation was seeded with backtest context the mentor
#     automatically grounds its answer in that specific strategy and run.
#     """
#     try:
#         result = await service.ask_question(
#             user_id         = request.user_id,
#             message         = request.message,
#             conversation_id = conversation_id,
#         )
#         return AskQuestionResponse(**result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.get("/conversations/{conversation_id}/messages", response_model=ConversationHistoryResponse)
# async def get_conversation_history(
#     conversation_id: str,
#     user_id:         str,
#     service:         MentorService = Depends(get_mentor_service),
# ):
#     """Retrieve full message history for a conversation."""
#     try:
#         history = await service.get_conversation_history(conversation_id, user_id)
#         if history is None:
#             raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
#         return ConversationHistoryResponse(
#             conversation_id = conversation_id,
#             history         = [ConversationMessageResponse(**m) for m in history],
#             message_count   = len(history),
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.get("/conversations", response_model=list[ConversationSummaryResponse])
# async def list_conversations(
#     user_id: str,
#     limit:   int = 20,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """List all conversations for a user (generic + backtest, newest first)."""
#     try:
#         conversations = await service.list_user_conversations(user_id, limit)
#         return [ConversationSummaryResponse(**c) for c in conversations]
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse)
# async def delete_conversation(
#     conversation_id: str,
#     user_id:         str,
#     service:         MentorService = Depends(get_mentor_service),
# ):
#     """Delete a conversation and all its messages."""
#     try:
#         deleted = await service.delete_conversation(conversation_id, user_id)
#         if not deleted:
#             raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
#         return DeleteConversationResponse(
#             message         = "Conversation deleted successfully.",
#             conversation_id = conversation_id,
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ---------------------------------------------------------------------------
# # Backtest-seeded conversation  (service-to-service)
# # ---------------------------------------------------------------------------

# @router.post("/backtest-conversations", response_model=StartBacktestConversationResponse)
# async def start_backtest_conversation(
#     request: StartBacktestConversationRequest,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """
#     Seed a new mentor conversation with full backtest context.

#     Called internally by the backtest service after a run completes.
#     Returns an initial analysis and a conversation_id the frontend
#     can use for unlimited follow-up questions via:
#       POST /mentor/conversations/{conversation_id}/messages
#     """
#     try:
#         result = await service.start_backtest_conversation(
#             user_id          = request.user_id,
#             backtest_context = request.backtest_context,
#         )
#         return StartBacktestConversationResponse(**result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ---------------------------------------------------------------------------
# # Pass / Fail analysis  (stateless, called by backtest service)
# # ---------------------------------------------------------------------------

# @router.post("/analyze-backtest", response_model=AnalyzeBacktestResponse)
# async def analyze_backtest(
#     request: AnalyzeBacktestRequest,
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """
#     Evaluate backtest results as PASS or FAIL and return an educational explanation.

#     Stateless — does not create a conversation.
#     The backtest service calls this right after a run and shows the
#     verdict + explanation to the user in the results view.
#     """
#     try:
#         result = await service.analyze_backtest_results(
#             strategy_type = request.strategy_type,
#             metrics       = request.metrics,
#         )
#         return AnalyzeBacktestResponse(**result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))































































# """
# routes/mentor_routes.py — FastAPI router for the Mentor module.

# Endpoints
# ─────────
# POST   /mentor/conversations                        start a generic conversation
# POST   /mentor/conversations/{id}/messages          ask a question (generic or follow-up)
# GET    /mentor/conversations/{id}/messages          get conversation history
# GET    /mentor/conversations                        list user's conversations
# DELETE /mentor/conversations/{id}                   delete a conversation
# POST   /mentor/backtest-conversations               seed a backtest conversation
# POST   /mentor/analyze-backtest                     pass/fail analysis (stateless)

# Auth
# ────
# All endpoints use get_current_user_id from core/dependencies.py.
# Set DEV_MODE=true in .env to skip auth during development.
# """

# from fastapi import APIRouter, HTTPException, Depends

# from models.mentor import (
#     AskQuestionRequest,
#     AskQuestionResponse,
#     ConversationHistoryResponse,
#     ConversationMessageResponse,
#     ConversationSummaryResponse,
#     DeleteConversationResponse,
#     StartBacktestConversationRequest,
#     StartBacktestConversationResponse,
# )
# from services.mentor_service import MentorService
# from core.dependencies import get_mentor_service, get_current_user_id

# router = APIRouter(prefix="/mentor", tags=["mentor"])


# # ---------------------------------------------------------------------------
# # Generic conversation endpoints
# # ---------------------------------------------------------------------------

# @router.post("/conversations", response_model=AskQuestionResponse)
# async def start_conversation(
#     request: AskQuestionRequest,
#     user_id: str            = Depends(get_current_user_id),
#     service: MentorService  = Depends(get_mentor_service),
# ):
#     """Start a new generic mentor conversation."""
#     try:
#         result = await service.ask_question(
#             user_id         = user_id,
#             message         = request.message,
#             conversation_id = None,
#         )
#         return AskQuestionResponse(**result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.post("/conversations/{conversation_id}/messages", response_model=AskQuestionResponse)
# async def ask_question(
#     conversation_id: str,
#     request:         AskQuestionRequest,
#     user_id:         str           = Depends(get_current_user_id),
#     service:         MentorService = Depends(get_mentor_service),
# ):
#     """
#     Ask a question in an existing conversation.
#     Works for both generic and backtest follow-up conversations.
#     """
#     try:
#         result = await service.ask_question(
#             user_id         = user_id,
#             message         = request.message,
#             conversation_id = conversation_id,
#         )
#         return AskQuestionResponse(**result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.get("/conversations/{conversation_id}/messages", response_model=ConversationHistoryResponse)
# async def get_conversation_history(
#     conversation_id: str,
#     user_id:         str           = Depends(get_current_user_id),
#     service:         MentorService = Depends(get_mentor_service),
# ):
#     """Retrieve full message history for a conversation."""
#     try:
#         history = await service.get_conversation_history(conversation_id, user_id)
#         if history is None:
#             raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
#         return ConversationHistoryResponse(
#             conversation_id = conversation_id,
#             history         = [ConversationMessageResponse(**m) for m in history],
#             message_count   = len(history),
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.get("/conversations", response_model=list[ConversationSummaryResponse])
# async def list_conversations(
#     limit:   int           = 20,
#     user_id: str           = Depends(get_current_user_id),
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """List all conversations for a user (generic + backtest, newest first)."""
#     try:
#         conversations = await service.list_user_conversations(user_id, limit)
#         return [ConversationSummaryResponse(**c) for c in conversations]
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse)
# async def delete_conversation(
#     conversation_id: str,
#     user_id:         str           = Depends(get_current_user_id),
#     service:         MentorService = Depends(get_mentor_service),
# ):
#     """Delete a conversation and all its messages."""
#     try:
#         deleted = await service.delete_conversation(conversation_id, user_id)
#         if not deleted:
#             raise HTTPException(status_code=404, detail="Conversation not found or unauthorized.")
#         return DeleteConversationResponse(
#             message         = "Conversation deleted successfully.",
#             conversation_id = conversation_id,
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # ---------------------------------------------------------------------------
# # Backtest-seeded conversation  (service-to-service)
# # ---------------------------------------------------------------------------

# @router.post("/backtest-conversations", response_model=StartBacktestConversationResponse)
# async def start_backtest_conversation(
#     request: StartBacktestConversationRequest,
#     user_id: str           = Depends(get_current_user_id),
#     service: MentorService = Depends(get_mentor_service),
# ):
#     """
#     Seed a new mentor conversation with full backtest context.
#     Returns an initial analysis + conversation_id for follow-up questions.
#     """
#     try:
#         result = await service.start_backtest_conversation(
#             user_id          = user_id,
#             backtest_context = request.backtest_context,
#         )
#         return StartBacktestConversationResponse(**result)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))



























"""
routes/mentor_routes.py — FastAPI router for the Mentor module.

Endpoints
─────────
POST   /mentor/conversations                        start a generic conversation
POST   /mentor/conversations/{id}/messages          ask a question (generic or follow-up)
GET    /mentor/conversations/{id}/messages          get conversation history
GET    /mentor/conversations                        list user's conversations
DELETE /mentor/conversations/{id}                   delete a conversation
POST   /mentor/backtest-conversations               seed a backtest conversation

Auth: uses get_current_user from api.middleware.auth_middleware
      user_id is extracted from the JWT token — not from the request body
"""

from fastapi import APIRouter, HTTPException, Depends

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


@router.post("/ask", response_model=AskQuestionResponse, include_in_schema=False)
async def ask_question_legacy(
    request:         AskQuestionRequest,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """Legacy frontend endpoint. Starts or continues a conversation."""
    try:
        result = await service.ask_question(
            user_id         = user.user_id,
            message         = request.message,
            conversation_id = request.conversation_id,
        )
        return AskQuestionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: str,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """Retrieve full message history for a conversation."""
    try:
        history = await service.get_conversation_history(conversation_id, user.user_id)
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
    Legacy frontend endpoint.
    Returns an empty history for a brand-new conversation id instead of failing the page.
    """
    try:
        history = await service.get_conversation_history(conversation_id, user.user_id)
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
    """
    Legacy frontend endpoint with user_id in the path.
    Returns an empty history for a brand-new conversation id instead of failing the page.
    """
    try:
        _assert_user_access(user_id, user)
        history = await service.get_conversation_history(conversation_id, user.user_id)
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


@router.get("/conversations", response_model=list[ConversationSummaryResponse])
async def list_conversations(
    limit:   int           = 20,
    user:    JWTPayload    = Depends(get_current_user),
    service: MentorService = Depends(get_mentor_service),
):
    """List all conversations for a user (generic + backtest, newest first)."""
    try:
        conversations = await service.list_user_conversations(user.user_id, limit)
        return [ConversationSummaryResponse(**c) for c in conversations]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    conversation_id: str,
    user:            JWTPayload    = Depends(get_current_user),
    service:         MentorService = Depends(get_mentor_service),
):
    """Delete a conversation and all its messages."""
    try:
        deleted = await service.delete_conversation(conversation_id, user.user_id)
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
    """Legacy frontend endpoint with user_id in the path."""
    try:
        _assert_user_access(user_id, user)
        deleted = await service.delete_conversation(conversation_id, user.user_id)
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
    Returns an initial analysis + conversation_id for follow-up questions.
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

from typing import Optional as _Optional
from pydantic import BaseModel as _BaseModel
from fastapi.responses import StreamingResponse
import json as _json


class AskStreamRequest(_BaseModel):
    message:         str
    conversation_id: _Optional[str] = None


@router.post("/ask/stream")
async def ask_stream(
    request: AskStreamRequest,
    user:    JWTPayload    = Depends(get_current_user),
    service: MentorService = Depends(get_mentor_service),
):
    """
    Stream an AI mentor response as Server-Sent Events (SSE).

    Request body: { "message": "...", "conversation_id": "..." (optional) }

    Each SSE frame:   data: "json-encoded text chunk"\\n\\n
    Final frame:      data: [DONE]\\n\\n

    Chunks are JSON-encoded strings so embedded newlines in markdown are safe.
    """

    async def event_generator():
        try:
            async for chunk in service.ask_question_stream(
                user_id         = user.user_id,
                message         = request.message,
                conversation_id = request.conversation_id,
            ):
                yield f"data: {_json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
