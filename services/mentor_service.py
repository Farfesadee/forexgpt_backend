"""
services/mentor_service.py

Mentor Service — Educational Q&A for Forex and Quantitative Finance.

Two conversation modes
──────────────────────
1. Generic        User starts a normal conversation and asks forex/quant
                  questions. History is persisted so follow-up questions
                  have full context.

2. Backtest-aware The backtest service seeds a conversation with full
                  strategy context + metrics. The mentor gives an initial
                  analysis and the user can ask unlimited follow-up
                  questions grounded in that specific run.

DB tables used:
  mentor_conversations  — one row per conversation (id, user_id, title)
  mentor_messages       — all messages (role: user | assistant | system)
"""

import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import logging
import asyncio

from prompts.mentor_system_prompt import MENTOR_SYSTEM_PROMPT
from models.mentor import BacktestContext

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MentorService:
    """
    Educational mentor service for forex and quantitative finance questions.
    Persists full conversation history so users can ask follow-up questions.
    """

    def __init__(self, mistral_client, db, model_id: str = "mistral-small-latest"):
        """
        Args:
            mistral_client : Mistral async client instance
            db             : Database instance (core.database.db)
            model_id       : Mistral model to use
        """
        self.client        = mistral_client
        self.db            = db
        self.model_id      = model_id
        self.system_prompt = MENTOR_SYSTEM_PROMPT
        self._deleted_conversations: set = set()

    # =========================================================================
    # PUBLIC — start a backtest conversation
    # =========================================================================

    async def start_backtest_conversation(
        self,
        user_id:          str,
        backtest_context: BacktestContext,
    ) -> Dict[str, Any]:
        """
        Seed a new conversation with backtest context and return initial analysis.
        The frontend stores conversation_id and uses it for all follow-up questions.
        """
        conversation_id = str(uuid.uuid4())
        logger.info(f"Seeding backtest conversation {conversation_id} for user {user_id}")

        # 1. Create conversation record
        self.db.mentor.create_conversation(
            id      = conversation_id,
            user_id = user_id,
            title   = f"Backtest: {backtest_context.strategy_type}",
        )

        # 2. Save backtest context as system message so it loads on every follow-up
        self.db.mentor.add_message(
            conversation_id = conversation_id,
            user_id         = user_id,
            role            = "system",
            content         = json.dumps(backtest_context.model_dump(), indent=2),
        )

        # 3. Build and send initial analysis prompt
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": self._format_context_for_llm(backtest_context)},
            {"role": "user",   "content": self._build_initial_analysis_prompt(backtest_context)},
        ]

        analysis = await self._generate_response(messages, max_tokens=400)

        # 4. Save the initial analysis so it's part of the conversation history
        self.db.mentor.add_message(
            conversation_id = conversation_id,
            user_id         = user_id,
            role            = "assistant",
            content         = analysis,
        )

        logger.info(f"Backtest conversation {conversation_id} seeded successfully.")

        return {
            "analysis":        analysis,
            "conversation_id": conversation_id,
            "backtest_id":     backtest_context.backtest_id,
            "timestamp":       _utcnow(),
        }

    # =========================================================================
    # PUBLIC — ask a question (generic or follow-up)
    # =========================================================================

    async def ask_question(
        self,
        user_id:         str,
        message:         str,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ask the mentor a question.

        - conversation_id is None  → starts a new conversation
        - conversation_id provided → loads full history and continues

        For backtest conversations the mentor automatically injects the
        original backtest context so every answer is grounded in that run.
        """
        try:
            if conversation_id:
                logger.info(f"Loading conversation {conversation_id} for user {user_id}")
                history, backtest_context = self._load_conversation(conversation_id, user_id)

                if history is None:
                    logger.warning(f"Unauthorized access to conversation {conversation_id}")
                    raise PermissionError("Conversation not found or unauthorized.")

            else:
                logger.info(f"Starting new conversation for user {user_id}")
                conversation_id = str(uuid.uuid4())
                self.db.mentor.create_conversation(
                    id      = conversation_id,
                    user_id = user_id,
                    title   = None,
                )
                history          = []
                backtest_context = None

            # Build full message list including all prior history
            messages = self._build_messages(history, message, backtest_context)

            logger.info(f"Generating response for conversation {conversation_id}")
            response = await self._generate_response(messages, max_tokens=600)

            # Persist both user message and assistant response
            self._save_message(conversation_id, user_id, role="user",      content=message)
            self._save_message(conversation_id, user_id, role="assistant", content=response)

            message_count = len([m for m in history if m["role"] in ("user", "assistant")]) + 2

            logger.info(f"Response generated for conversation {conversation_id}")
            return {
                "response":        response,
                "conversation_id": conversation_id,
                "message_count":   message_count,
                "timestamp":       _utcnow(),
            }

        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Error in ask_question: {e}", exc_info=True)
            raise

    # =========================================================================
    # PUBLIC — conversation management
    # =========================================================================

    def get_conversation_history(
        self,
        conversation_id: str,
        user_id:         str,
    ) -> Optional[List[Dict]]:
        """Returns full message history. Returns None if unauthorized."""
        try:
            history, _ = self._load_conversation(conversation_id, user_id)
            if history is None:
                return None
            return [
                {
                    "role":      msg["role"],
                    "content":   msg["content"],
                    "timestamp": msg.get("timestamp", ""),
                }
                for msg in history
                if msg["role"] in ("user", "assistant")
            ]
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}", exc_info=True)
            raise

    def list_user_conversations(
        self,
        user_id: str,
        limit:   int = 20,
    ) -> List[Dict]:
        """List all conversations for a user."""
        try:
            rows = self.db.mentor.list_conversations(user_id, limit=limit)
            conversations = []
            for row in rows:
                preview = row.get("last_response_preview") or ""
                conversations.append({
                    "conversation_id": row.get("id"),
                    "started_at":      row.get("created_at", ""),
                    "preview":         preview[:100] + "..." if len(preview) > 100 else preview,
                    "message_count":   row.get("message_count", 0),
                    "is_backtest":     str(row.get("title", "")).startswith("Backtest:"),
                })
            return conversations
        except Exception as e:
            logger.error(f"Error listing conversations: {e}", exc_info=True)
            raise

    def delete_conversation(
        self,
        conversation_id: str,
        user_id:         str,
    ) -> bool:
        """Delete a conversation. Returns True if deleted, False if not found."""
        try:
            rows = self.db.mentor._msg.select("id") \
                .eq("conversation_id", conversation_id) \
                .eq("user_id", user_id) \
                .limit(1).execute().data

            if not rows:
                return False

            self.db.mentor._msg.delete() \
                .eq("conversation_id", conversation_id) \
                .eq("user_id", user_id) \
                .execute()

            self.db.mentor._conv.delete() \
                .eq("id", conversation_id) \
                .eq("user_id", user_id) \
                .execute()

            self._deleted_conversations.add(conversation_id)
            logger.info(f"Deleted conversation {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            raise

    # =========================================================================
    # PRIVATE — DB helpers (synchronous — Supabase client is sync)
    # =========================================================================

    def _load_conversation(
        self,
        conversation_id: str,
        user_id:         str,
    ) -> tuple[Optional[List[Dict]], Optional[BacktestContext]]:
        """
        Load full conversation history from DB.

        Returns:
            (history, backtest_context)
            history=None  → unauthorized
            history=[]    → new or deleted conversation
        """
        if conversation_id in self._deleted_conversations:
            return [], None

        rows = self.db.mentor.get_history(conversation_id)

        if not rows:
            return [], None

        # Verify ownership
        ownership = self.db.mentor._msg \
            .select("user_id") \
            .eq("conversation_id", conversation_id) \
            .limit(1).execute().data

        if ownership and ownership[0].get("user_id") != user_id:
            return None, None

        history: List[Dict] = []
        backtest_context: Optional[BacktestContext] = None

        for msg in rows:
            if msg["role"] == "system":
                # Reconstruct backtest context from stored JSON
                try:
                    backtest_context = BacktestContext(**json.loads(msg["content"]))
                except Exception:
                    logger.warning("Failed to deserialise BacktestContext — ignoring.")
            else:
                history.append({
                    "role":      msg["role"],
                    "content":   msg["content"],
                    "timestamp": msg.get("created_at", ""),
                })

        return history, backtest_context

    def _save_message(
        self,
        conversation_id: str,
        user_id:         str,
        role:            str,
        content:         str,
    ) -> None:
        """Save a single message to mentor_messages."""
        try:
            self.db.mentor.add_message(
                conversation_id = conversation_id,
                user_id         = user_id,
                role            = role,
                content         = content,
            )
        except Exception as e:
            logger.error(f"Error saving message: {e}", exc_info=True)
            raise

    # =========================================================================
    # PRIVATE — message construction
    # =========================================================================

    def _build_messages(
        self,
        history:          List[Dict],
        new_message:      str,
        backtest_context: Optional[BacktestContext],
    ) -> List[Dict]:
        """
        Build the full message list to send to Mistral.

        Structure:
          [system prompt]
          [backtest context block — only for backtest conversations]
          [full conversation history — user/assistant turns]
          [new user message]
        """
        messages = [{"role": "system", "content": self.system_prompt}]

        # Inject backtest context so the LLM never loses track of the run
        if backtest_context:
            messages.append({
                "role":    "system",
                "content": self._format_context_for_llm(backtest_context),
            })

        # Add all prior turns for full conversation continuity
        for msg in history:
            if msg["role"] in ("user", "assistant"):
                messages.append({
                    "role":    msg["role"],
                    "content": msg["content"],
                })

        messages.append({"role": "user", "content": new_message})
        return messages

    def _build_initial_analysis_prompt(self, ctx: BacktestContext) -> str:
        """Build the first user turn for a backtest conversation."""
        def fmt(key, label, suffix=""):
            val = ctx.metrics.get(key)
            return f"  - {label}: {val}{suffix}" if val is not None else None

        metric_lines = [
            fmt("pair",                 "Currency Pair"),
            fmt("start_date",           "Backtest Start"),
            fmt("end_date",             "Backtest End"),
            fmt("total_return_pct",     "Total Return",       "%"),
            fmt("sharpe_ratio",         "Sharpe Ratio"),
            fmt("sortino_ratio",        "Sortino Ratio"),
            fmt("max_drawdown_pct",     "Max Drawdown",       "%"),
            fmt("win_rate_pct",         "Win Rate",           "%"),
            fmt("profit_factor",        "Profit Factor"),
            fmt("total_trades",         "Total Trades"),
            fmt("winning_trades",       "Winning Trades"),
            fmt("losing_trades",        "Losing Trades"),
            fmt("avg_win",              "Avg Win"),
            fmt("avg_loss",             "Avg Loss"),
            fmt("avg_risk_reward",      "Avg Risk/Reward"),
            fmt("avg_holding_days",     "Avg Holding Days",   " days"),
            fmt("volatility_annual_pct","Annual Volatility",  "%"),
            fmt("cagr_pct",             "CAGR",               "%"),
            fmt("calmar_ratio",         "Calmar Ratio"),
            fmt("expectancy",           "Expectancy"),
        ]
        metrics_str = "\n".join(line for line in metric_lines if line)

        params_section = ""
        if ctx.parameters:
            params_str = "\n".join(f"  - {k}: {v}" for k, v in ctx.parameters.items())
            params_section = f"\nSTRATEGY PARAMETERS:\n{params_str}\n"

        return f"""I just ran a backtest for my {ctx.strategy_type} strategy.
{params_section}
PERFORMANCE RESULTS:
{metrics_str}

Give me a concise analysis — under 150 words.
Structure:
- VERDICT (1 sentence: PASS or FAIL + main reason)
- WHY (2-3 bullets: key reasons only)
- NEXT STEPS (2 bullets: most impactful improvements)

After this initial analysis, answer all my follow-up questions with full
educational depth — explain metrics, concepts, and theory thoroughly."""

    @staticmethod
    def _format_context_for_llm(ctx: BacktestContext) -> str:
        """Format backtest context as a system block injected before every LLM call."""
        metrics_str  = "\n".join(f"  {k}: {v}" for k, v in ctx.metrics.items())
        params_str   = "\n".join(f"  {k}: {v}" for k, v in ctx.parameters.items()) if ctx.parameters else "  None provided"
        backtest_ref = f"  backtest_id: {ctx.backtest_id}" if ctx.backtest_id else ""

        return f"""═══ ACTIVE BACKTEST CONTEXT ═══
Ground ALL answers in these specific results — no generic advice.

Strategy : {ctx.strategy_type}
{backtest_ref}

Parameters:
{params_str}

Metrics:
{metrics_str}
═══════════════════════════════"""

    # =========================================================================
    # PRIVATE — verdict helper
    # =========================================================================

    @staticmethod
    def _evaluate_strategy(metrics: Dict[str, Any]) -> str:
        """PASS if sharpe >= 1.0, total_return > 0, max_drawdown > -15%."""
        sharpe       = float(metrics.get("sharpe_ratio",     0) or 0)
        total_return = float(metrics.get("total_return_pct", 0) or 0)
        max_drawdown = float(metrics.get("max_drawdown_pct", 0) or 0)
        if sharpe >= 1.0 and total_return > 0 and max_drawdown > -15:
            return "PASS"
        return "FAIL"

    # =========================================================================
    # PRIVATE — LLM call with retry
    # =========================================================================

    async def _generate_response(
        self,
        messages:   List[Dict],
        max_tokens: int = 600,
    ) -> str:
        """Call Mistral with exponential back-off retry (3 attempts)."""
        last_error = None

        for attempt in range(3):
            try:
                response = await self.client.chat.complete_async(
                    model       = self.model_id,
                    messages    = messages,
                    max_tokens  = max_tokens,
                    temperature = 0.7,
                    top_p       = 0.9,
                )
                return response.choices[0].message.content

            except Exception as e:
                last_error = e
                logger.warning(f"LLM attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

        logger.error(f"All LLM retries failed: {last_error}", exc_info=True)
        raise last_error

    # =========================================================================
    # PUBLIC — streaming ask (yields text chunks for SSE endpoint)
    # =========================================================================

    async def ask_question_stream(
        self,
        user_id:         str,
        message:         str,
        conversation_id: Optional[str] = None,
    ):
        """
        Streaming version of ask_question.
        Yields raw text chunks as they arrive from Mistral.
        Persists the complete response to DB after stream ends.
        """
        try:
            if conversation_id:
                logger.info(f"[stream] Loading conversation {conversation_id} for user {user_id}")
                history, backtest_context = self._load_conversation(conversation_id, user_id)
                if history is None:
                    raise PermissionError("Conversation not found or unauthorized.")
            else:
                logger.info(f"[stream] Starting new conversation for user {user_id}")
                conversation_id = str(uuid.uuid4())
                self.db.mentor.create_conversation(
                    id      = conversation_id,
                    user_id = user_id,
                    title   = None,
                )
                history          = []
                backtest_context = None

            # Save user message before streaming starts
            self._save_message(conversation_id, user_id, role="user", content=message)

            messages = self._build_messages(history, message, backtest_context)

            logger.info(f"[stream] Streaming response for conversation {conversation_id}")
            full_response = ""
            async for chunk in self._generate_response_stream(messages, max_tokens=600):
                full_response += chunk
                yield chunk

            # Save complete assistant response after stream ends
            self._save_message(conversation_id, user_id, role="assistant", content=full_response)
            logger.info(f"[stream] Completed for conversation {conversation_id}")

        except Exception as e:
            logger.error(f"[stream] Error in ask_question_stream: {e}", exc_info=True)
            raise

    # =========================================================================
    # PRIVATE — streaming LLM call
    # =========================================================================

    async def _generate_response_stream(
        self,
        messages:   List[Dict],
        max_tokens: int = 600,
    ):
        """Call Mistral in streaming mode and yield text delta chunks."""
        async with await self.client.chat.stream_async(
            model       = self.model_id,
            messages    = messages,
            max_tokens  = max_tokens,
            temperature = 0.7,
            top_p       = 0.9,
        ) as stream:
            async for event in stream:
                choices = event.data.choices
                if choices and choices[0].delta.content:
                    yield choices[0].delta.content