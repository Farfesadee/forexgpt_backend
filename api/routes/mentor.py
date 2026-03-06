# # import logging
# # from fastapi import APIRouter, Depends
# # from models.mentor import MentorAskRequest, MentorMessageResponse
# # from services.ai_service import ask_mentor
# # from services.auth_service import verify_token

# # logger = logging.getLogger(__name__)
# # router = APIRouter(prefix="/mentor", tags=["Mentor"])


# # @router.post("/ask", response_model=MentorMessageResponse)
# # async def ask_mentor_endpoint(
# #     body: MentorAskRequest,
# #     user: dict = Depends(verify_token),
# # ):
# #     logger.info(f"Mentor question from user: {user['user_id']}")
# #     result = await ask_mentor(
# #         question=body.question,
# #         context=None,  # For simplicity, no conversation history context is included in this example.
# #         user_id=user["user_id"],
# #     )
# #     return MentorMessageResponse(**result)


# """
# api/routes/mentor.py — Forex Theory Mentor REST API.

# Endpoints:
#   POST   /mentor/conversations              Create new conversation session
#   GET    /mentor/conversations              List user's conversations (sidebar)
#   DELETE /mentor/conversations/{id}        Archive a conversation

#   POST   /mentor/conversations/{id}/ask    ← PRIMARY ENDPOINT: ask a question
#   GET    /mentor/conversations/{id}/messages  Full message history

#   PATCH  /mentor/messages/{id}/feedback    Thumbs up/down on an answer

#   GET    /mentor/topics                    Topic taxonomy (for UI chips)
#   GET    /mentor/status                    Pipeline health (which models are live)

# All endpoints require: Authorization: Bearer <access_token>
# Request flows through auth_middleware.get_current_user → JWTPayload → user_id.
# """

# import logging
# from fastapi import APIRouter, Depends, HTTPException, Query, status

# from api.middleware.auth_middleware import get_current_user
# from models.user import JWTPayload
# from models.mentor import (
#     ConversationCreate,
#     ConversationResponse,
#     ConversationListResponse,
#     MentorAskRequest,
#     MentorAskResponse,
#     MessageFeedbackRequest,
#     MessageHistoryResponse,
#     DifficultyLevel,
# )
# import services.mentor as mentor_service

# logger = logging.getLogger(__name__)
# router = APIRouter()

# # Conversation management 

# @router.post(
#     "/conversations",
#     response_model=ConversationResponse,
#     status_code=status.HTTP_201_CREATED,
#     summary="Start a new mentor conversation",
# )
# async def create_conversation(
#     body: ConversationCreate,
#     user: JWTPayload = Depends(get_current_user),
# ):
#     """
#     Create a new mentor conversation session.

#     Each conversation groups related Q&A messages. The title is auto-generated
#     from the first question asked. Set `difficulty` to match the student's level —
#     this controls the system prompt used for all messages in the session.
#     """
#     try:
#         return await mentor_service.create_conversation(user.user_id, body.difficulty.value)
#     except Exception as e:
#         logger.error(f"Create conversation error: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Failed to create conversation.")

# @router.get(
#     "/conversations",
#     response_model=ConversationListResponse,
#     summary="List your mentor conversations",
# )
# async def list_conversations(
#     include_archived: bool = Query(False, description="Include archived conversations."),
#     limit: int        = Query(30,  ge=1, le=100),
#     user: JWTPayload  = Depends(get_current_user),
# ):
#     """
#     Returns all of the user's mentor conversations for the sidebar.
#     Each item includes the conversation title, topic tags, difficulty,
#     message count, and a 140-char preview of the last assistant reply.

#     Results are ordered by `last_message_at DESC` (most recent first).
#     """
#     try:
#         return await mentor_service.list_conversations(user.user_id, include_archived, limit)
#     except Exception as e:
#         logger.error(f"List conversations error: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Failed to fetch conversations.")

# @router.delete(
#     "/conversations/{conversation_id}",
#     status_code=status.HTTP_204_NO_CONTENT,
#     summary="Archive a conversation",
# )
# async def archive_conversation(
#     conversation_id: str,
#     user: JWTPayload = Depends(get_current_user),
# ):
#     """
#     Soft-delete (archive) a conversation. Messages are preserved in the DB.
#     Archived conversations are hidden from the default list view.
#     """
#     try:
#         await mentor_service.archive_conversation(conversation_id)
#     except Exception as e:
#         logger.error(f"Archive conversation error: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Failed to archive conversation.")

# # PRIMARY ENDPOINT 
# @router.post(
#     "/conversations/{conversation_id}/ask",
#     response_model=MentorAskResponse,
#     summary="Ask the Forex Mentor a question",
#     description="""
# Ask the Forex theory mentor a question within a conversation.

# **Pipeline:**
# 1. User question is persisted to `mentor_messages`
# 2. Last 10 turns loaded as conversation context
# 3. Mistral 7B (base) produces a fast factual draft answer
# 4. Claude Sonnet 4.6 refines the draft — adds depth, examples, follow-up questions —
#    calibrated to the conversation's difficulty level
# 5. Assistant reply persisted with full metadata (model, tokens, latency, topic tags)

# **Response includes:**
# - `user_message`: the persisted question
# - `assistant_message`: the polished answer with topic tags, related concepts,
#    and 3 follow-up questions to guide further learning
# """,
# )
# async def ask(
#     conversation_id: str,
#     body: MentorAskRequest,
#     user: JWTPayload = Depends(get_current_user),
# ):
#     """
#     **Primary mentor endpoint.**

#     POST body:
#     ```json
#     {
#       "question": "What is the carry trade and what are its main risks?",
#       "include_examples": true,
#       "include_formulas": false
#     }
#     ```

#     Returns both the persisted user message and the assistant's answer.
#     The assistant message includes:
#     - `content` — the full answer
#     - `topic_tags` — Forex concept areas identified in the Q&A
#     - `related_concepts` — adjacent topics worth exploring next
#     - `follow_up_questions` — 3 suggested next questions
#     - `model_used` — which model(s) produced this answer
#     - `tokens_used`, `latency_ms` — for transparency

#     Errors:
#     - 404 if `conversation_id` doesn't exist or belongs to another user
#     - 502 if the LLM service is temporarily unavailable
#     """
#     # Verify the conversation belongs to this user and get its difficulty
#     conv = _get_conversation_or_404(conversation_id, user.user_id)
#     difficulty = DifficultyLevel(conv.get("difficulty", "intermediate"))

#     try:
#         return await mentor_service.ask(
#             conversation_id=conversation_id,
#             user_id=user.user_id,
#             request=body,
#             difficulty=difficulty,
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Mentor ask error (conv={conversation_id}): {e}", exc_info=True)
#         # Return a degraded 502 rather than 500 — signals upstream LLM issue
#         raise HTTPException(
#             status_code=status.HTTP_502_BAD_GATEWAY,
#             detail="The mentor LLM service is temporarily unavailable. Please try again.",
#         )

# # Message history

# @router.get(
#     "/conversations/{conversation_id}/messages",
#     response_model=MessageHistoryResponse,
#     summary="Fetch full message history for a conversation",
# )
# async def get_message_history(
#     conversation_id: str,
#     limit: int       = Query(40, ge=1, le=200),
#     user: JWTPayload = Depends(get_current_user),
# ):
#     """
#     Returns the full ordered message history for a conversation.
#     Used to re-render a conversation thread after page reload.
#     """
#     _get_conversation_or_404(conversation_id, user.user_id)
#     try:
#         return await mentor_service.get_message_history(conversation_id, limit)
#     except Exception as e:
#         logger.error(f"Get history error: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Failed to fetch message history.")

# # Message feedback 

# @router.patch(
#     "/messages/{message_id}/feedback",
#     status_code=status.HTTP_204_NO_CONTENT,
#     summary="Submit thumbs up/down feedback on an answer",
# )
# async def set_message_feedback(
#     message_id: str,
#     body: MessageFeedbackRequest,
#     user: JWTPayload = Depends(get_current_user),
# ):
#     """
#     Record user feedback on an assistant message.
#     `thumbs_up: true` = helpful, `thumbs_up: false` = not helpful.
#     Feedback is stored on the message row and surfaced in admin analytics.
#     """
#     try:
#         await mentor_service.set_message_feedback(message_id, body.thumbs_up)
#     except Exception as e:
#         logger.error(f"Feedback error: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Failed to record feedback.")

# # Meta / utility endpoints 

# @router.get(
#     "/topics",
#     summary="List all Forex topic areas the mentor covers",
# )
# async def list_topics(_: JWTPayload = Depends(get_current_user)):
#     """
#     Returns the full taxonomy of Forex and finance topics the mentor covers.
#     Use to build UI chips, filter conversations, or surface related content.
#     """
#     return {
#         "topics": [
#             {
#                 "id": "pip",
#                 "name": "Pips & Spreads",
#                 "concepts": ["pip value", "spread", "pipette", "bid-ask"],
#             },
#             {
#                 "id": "leverage",
#                 "name": "Leverage & Margin",
#                 "concepts": ["lot size", "margin call", "exposure", "notional value"],
#             },
#             {
#                 "id": "technical_analysis",
#                 "name": "Technical Analysis",
#                 "concepts": ["RSI", "MACD", "Bollinger Bands", "EMA", "Ichimoku", "Fibonacci"],
#             },
#             {
#                 "id": "fundamental_analysis",
#                 "name": "Fundamental Analysis",
#                 "concepts": ["interest rates", "inflation", "NFP", "GDP", "central banks", "PMI"],
#             },
#             {
#                 "id": "risk_management",
#                 "name": "Risk Management",
#                 "concepts": ["stop loss", "take profit", "risk/reward", "drawdown", "Kelly criterion", "VaR"],
#             },
#             {
#                 "id": "strategies",
#                 "name": "Trading Strategies",
#                 "concepts": ["carry trade", "momentum", "mean reversion", "breakout", "scalping"],
#             },
#             {
#                 "id": "market_structure",
#                 "name": "Market Structure",
#                 "concepts": ["liquidity", "order flow", "COT reports", "trading sessions", "slippage"],
#             },
#             {
#                 "id": "statistics",
#                 "name": "Statistics & Metrics",
#                 "concepts": ["Sharpe ratio", "Sortino ratio", "correlation", "volatility", "beta"],
#             },
#             {
#                 "id": "quant_methods",
#                 "name": "Quantitative Methods",
#                 "concepts": ["backtesting", "walk-forward", "Monte Carlo", "optimisation", "overfitting"],
#             },
#             {
#                 "id": "macroeconomics",
#                 "name": "Macro Economics",
#                 "concepts": ["interest rate differentials", "PPP", "current account", "capital flows"],
#             },
#         ]
#     }

# @router.get(
#     "/status",
#     summary="Check which models are active in the mentor pipeline",
# )
# async def pipeline_status(_: JWTPayload = Depends(get_current_user)):
#     """
#     Returns live pipeline configuration.
#     Useful for the frontend to show which model(s) are answering questions.
#     """
#     from core.llm_router import llm_router
#     from core.config import settings

#     return {
#         "pipeline_mode":     "dual_model" if llm_router.mistral_available else "claude_solo",
#         "draft_model":       settings.MISTRAL_BASE_MODEL_NAME if llm_router.mistral_available else None,
#         "refinement_model":  settings.CLAUDE_MODEL,
#         "rag_enabled":       True,
#         "difficulty_levels": ["beginner", "intermediate", "advanced"],
#     }


# # ── Internal helper ────────────────────────────────────────────────────────────

# def _get_conversation_or_404(conversation_id: str, user_id: str) -> dict:
#     """
#     Fetch a conversation row and verify it belongs to this user.
#     Raises 404 if not found or not owned by this user (prevents enumeration).
#     """
#     from core.database import db
#     try:
#         from supabase import PostgrestAPIError
#     except ImportError:
#         PostgrestAPIError = Exception

#     try:
#         row = (
#             db._t("mentor_conversations")
#             .select("id, user_id, difficulty, is_archived")
#             .eq("id", conversation_id)
#             .eq("user_id", user_id)
#             .single()
#             .execute()
#             .data
#         )
#         if not row:
#             raise HTTPException(status_code=404, detail="Conversation not found.")
#         return row
#     except HTTPException:
#         raise
#     except Exception:
#         raise HTTPException(status_code=404, detail="Conversation not found.")

from fastapi import APIRouter, Depends, HTTPException, status
from models.mentor import (
    AskQuestionRequest,
    AskQuestionResponse,
    ConversationHistoryResponse,
    ConversationSummaryResponse,
    DeleteConversationResponse
)
from models.user import JWTPayload
from api.middleware.auth_middleware import get_current_user
from core.dependencies import get_mentor_service

router = APIRouter(prefix="/mentor", tags=["mentor"])
service = get_mentor_service()

def _assert_user_access(requested_user_id: str, user: JWTPayload) -> None:
    if requested_user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources.",
        )


@router.post("/ask", response_model=AskQuestionResponse)
async def ask_question(
    request: AskQuestionRequest,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        if request.user_id and request.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only ask questions for your own account.",
            )
        result = await service.ask_question(
            user_id=user.user_id,
            message=request.message,
            conversation_id=request.conversation_id
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        # raise HTTPException(
        #     status_code=503,
        #     detail="Our AI service is temporarily unavailable. Please try again in a moment."
        # )


@router.get("/conversations/{user_id}", response_model=list[ConversationSummaryResponse])
async def list_conversations(
    user_id: str,
    limit: int = 20,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        _assert_user_access(user_id, user)
        conversations = service.list_user_conversations(user_id, limit)
        return conversations
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{user_id}/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation(
    conversation_id: str,
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        _assert_user_access(user_id, user)
        history = await service.get_conversation_history(conversation_id, user_id)
        if history is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {
            "conversation_id": conversation_id,
            "history": history,
            "message_count": len(history)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversations/{user_id}/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    conversation_id: str,
    user_id: str,
    user: JWTPayload = Depends(get_current_user),
):
    try:
        _assert_user_access(user_id, user)
        deleted = await service.delete_conversation(conversation_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"message": "Conversation deleted successfully", "conversation_id": conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
