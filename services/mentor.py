
"""
services/mentor_service.py — Forex Theory Mentor LLM Pipeline.

Pipeline per ask request:
  1. Persist user question to mentor_messages
  2. Load conversation history (last 10 turns) for context window
  3. Retrieve RAG passages from ChromaDB (graceful degradation if down)
  4. Resolve system_prompt_key from difficulty + stage
  5. llm_router.route_mentor() → Mistral draft → Claude Sonnet 4.6 refinement
  6. Parse response: split answer / follow-up questions, extract topic tags
  7. Persist assistant message to mentor_messages
  8. Increment mentor_questions_asked counter on profile
  9. Log to activity_log + llm_request_log
  10. Return MentorAskResponse

All DB writes use core/database.db (service_role key — bypasses RLS).
"""

import logging
import re
import time
from typing import Optional

from core.database import db
from core.llm_router import llm_router
from models.mentor import (
    DifficultyLevel,
    MentorAskRequest,
    MentorAskResponse,
    MentorMessageResponse,
    MentorLLMContext,
    LLMMessage,
    MessageRole,
    ConversationResponse,
    ConversationListResponse,
    ConversationListItem,
    MessageHistoryResponse,
    MessageFeedbackRequest,
)

logger = logging.getLogger(__name__)

# Topic Taxonomy 

CONCEPT_TAGS: dict[str, list[str]] = {
    "pip":                  ["pip", "pips", "pipette", "spread"],
    "leverage":             ["leverage", "margin", "lot size", "position size", "exposure"],
    "technical_analysis":   ["RSI", "MACD", "Bollinger", "EMA", "SMA", "Ichimoku",
                             "support", "resistance", "fibonacci", "candlestick", "chart"],
    "fundamental_analysis": ["GDP", "CPI", "NFP", "interest rate", "central bank",
                             "inflation", "employment", "PMI", "retail sales", "monetary policy"],
    "risk_management":      ["stop loss", "take profit", "risk reward", "drawdown",
                             "Kelly", "position sizing", "VaR", "risk per trade", "max loss"],
    "strategies":           ["carry trade", "momentum", "mean reversion", "breakout",
                             "scalping", "swing trading", "grid trading", "trend following"],
    "market_structure":     ["liquidity", "order flow", "COT", "market maker",
                             "trading session", "slippage", "bid ask"],
    "statistics":           ["Sharpe", "Sortino", "correlation", "volatility",
                             "beta", "skewness", "kurtosis", "standard deviation"],
    "quant_methods":        ["backtest", "Monte Carlo", "optimization",
                             "walk-forward", "overfitting", "regime detection"],
    "macroeconomics":       ["purchasing power parity", "interest rate differential",
                             "balance of payments", "current account", "capital flows", "PPP"],
}

def _extract_topic_tags(text: str) -> list[str]:
    text_lower = text.lower()
    tags = [
        tag for tag, keywords in CONCEPT_TAGS.items()
        if any(kw.lower() in text_lower for kw in keywords)
    ]
    return tags or ["general_forex"]

def _extract_related_concepts(topic_tags: list[str]) -> list[str]:
    all_topics = list(CONCEPT_TAGS.keys())
    return [t for t in all_topics if t not in topic_tags][:3]

def _parse_follow_ups(raw: str) -> tuple[str, list[str]]:
    """Split Claude's output into main answer + follow-up questions."""
    if "FOLLOW-UP QUESTIONS:" in raw:
        parts = raw.split("FOLLOW-UP QUESTIONS:", 1)
        main     = parts[0].strip()
        fq_block = parts[1].strip()
        questions = []
        for line in fq_block.splitlines():
            line = re.sub(r"^[\s\d\.\)\-]+", "", line).strip()
            if len(line) > 15:
                questions.append(line)
        return main, questions[:3]
    return raw.strip(), []

def _row_to_response(row: dict) -> MentorMessageResponse:
    return MentorMessageResponse(
        id=str(row["id"]),
        conversation_id=str(row["conversation_id"]),
        role=MessageRole(row["role"]),
        content=row["content"],
        topic_tags=row.get("topic_tags") or [],
        related_concepts=row.get("related_concepts") or [],
        follow_up_questions=row.get("follow_up_questions") or [],
        system_prompt_key=row.get("system_prompt_key"),
        model_used=row.get("model_used"),
        adapter_used=row.get("adapter_used"),
        tokens_used=row.get("tokens_used"),
        latency_ms=row.get("latency_ms"),
        thumbs_up=row.get("thumbs_up"),
        created_at=row["created_at"],
    )

# CRUD helpers 

async def create_conversation(user_id: str, difficulty: str) -> ConversationResponse:
    row = db.mentor.create_conversation(user_id, difficulty)
    return ConversationResponse(**{k: row[k] for k in ConversationResponse.model_fields if k in row})


async def list_conversations(
    user_id: str,
    include_archived: bool = False,
    limit: int = 30,
) -> ConversationListResponse:
    rows = db.mentor.list_conversations(user_id, include_archived, limit)
    items = [ConversationListItem(**{k: r.get(k) for k in ConversationListItem.model_fields}) for r in rows]
    return ConversationListResponse(items=items, total=len(items))

async def get_message_history(conversation_id: str, limit: int = 40) -> MessageHistoryResponse:
    rows = db.mentor.get_history(conversation_id, limit)
    return MessageHistoryResponse(
        conversation_id=conversation_id,
        messages=[_row_to_response(r) for r in rows],
    )

async def set_message_feedback(message_id: str, thumbs_up: bool) -> None:
    db.mentor.set_feedback(message_id, thumbs_up)

async def archive_conversation(conversation_id: str) -> None:
    db.mentor.archive_conversation(conversation_id)

# Core Ask Pipeline
async def ask(
    conversation_id: str,
    user_id: str,
    request: MentorAskRequest,
    difficulty: DifficultyLevel,
) -> MentorAskResponse:
    """
    Execute the full mentor pipeline for a single question.
    See module docstring for step-by-step breakdown.
    """
    t_start = time.perf_counter()

    # Step 1: Save user message
    user_row = db.mentor.add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=request.question,
    )

    # Step 2: Load conversation history (exclude the message we just saved)
    history_rows = db.mentor.get_history(conversation_id, limit=22)
    history = [
        LLMMessage(role=MessageRole(r["role"]), content=r["content"])
        for r in history_rows
        if str(r["id"]) != str(user_row["id"]) and r["role"] in ("user", "assistant")
    ][-10:]

    # Step 3: Resolve system_prompt_key
    system_prompt_key = f"mentor_{difficulty.value}"  # e.g. 'mentor_intermediate'

    # Step 4: Build context for llm_router
    ctx = MentorLLMContext(
        conversation_id=conversation_id,
        user_id=user_id,
        difficulty=difficulty,
        history=history,
        new_question=request.question,
        include_examples=request.include_examples,
        include_formulas=request.include_formulas,
        system_prompt_key=system_prompt_key,
    )

    # Step 5: Route through LLM pipeline
    try:
        llm_result = await llm_router.route_mentor(ctx)
    except Exception as e:
        logger.error(f"LLM pipeline error: {e}", exc_info=True)
        _log_llm_failure(user_id, system_prompt_key, e)
        raise

    t_total_ms = int((time.perf_counter() - t_start) * 1000)

    # Step 6: Parse
    main_answer, follow_up_questions = _parse_follow_ups(llm_result.content)
    topic_tags       = _extract_topic_tags(request.question + " " + main_answer)
    related_concepts = _extract_related_concepts(topic_tags)

    # Step 7: Save assistant message
    asst_row = db.mentor.add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content=main_answer,
        topic_tags=topic_tags,
        related_concepts=related_concepts,
        follow_up_questions=follow_up_questions,
        system_prompt_key=system_prompt_key,
        model_used=llm_result.model_used,
        adapter_used=llm_result.adapter_used,
        tokens_used=llm_result.tokens_used,
        latency_ms=t_total_ms,
    )

    # Step 8: Analytics
    db.profiles.increment_counter(user_id, "mentor")
    db.activity.log(
        user_id=user_id,
        action="mentor_question_asked",
        entity_type="mentor_conversation",
        entity_id=conversation_id,
        metadata={
            "topic_tags": topic_tags,
            "model_used": llm_result.model_used,
            "latency_ms": t_total_ms,
        },
    )
    db.llm_log.log(
        user_id=user_id,
        source_module="mentor_service",
        system_prompt_key=system_prompt_key,
        model_used=llm_result.model_used,
        adapter_used=llm_result.adapter_used,
        hf_endpoint_id=None,
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        latency_ms=t_total_ms,
        success=True,
        entity_type="mentor_message",
        entity_id=str(asst_row["id"]),
    )

    return MentorAskResponse(
        user_message=_row_to_response(user_row),
        assistant_message=_row_to_response(asst_row),
    )

def _log_llm_failure(user_id: str, prompt_key: str, exc: Exception) -> None:
    """Best-effort failure logging — never raises."""
    try:
        db.llm_log.log(
            user_id=user_id,
            source_module="mentor_service",
            system_prompt_key=prompt_key,
            model_used=None,
            adapter_used=None,
            hf_endpoint_id=None,
            input_tokens=None,
            output_tokens=None,
            latency_ms=None,
            success=False,
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
        )
    except Exception:
        pass