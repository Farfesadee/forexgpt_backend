"""
services/mentor_service.py

Mentor Service — Educational Q&A for Forex and Quantitative Finance.

Two conversation modes
──────────────────────
1. Generic        User starts a normal conversation and asks forex/quant
                  questions.  No backtest context.

2. Backtest-aware The backtest service calls start_backtest_conversation()
                  which seeds a new conversation with the full strategy
                  config + metrics, and returns an initial deep-dive
                  analysis.  The user then asks follow-up questions via the
                  standard ask_question() method — the mentor always has the
                  backtest context in scope so every answer is grounded in
                  the user's actual run.

DB table: mentor_conversations
  id              uuid PK
  conversation_id uuid  (groups messages)
  user_id         text
  role            text  ('system_context' | 'user' | 'assistant')
  content         text
  created_at      timestamptz

The backtest context is stored as a single 'system_context' role message
at the top of the conversation so it survives across sessions.
"""

import os
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import logging
import asyncio

from prompts.mentor_system_prompt import MENTOR_SYSTEM_PROMPT
from models.mentor import BacktestContext

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MentorService:
    """
    Educational mentor service for forex and quantitative finance questions.
    Maintains conversation history and provides structured educational responses.
    Supports both generic Q&A and backtest-grounded analysis conversations.
    """

    def __init__(self, mistral_client, db, model_id: str = "mistral-small-latest"):
        """
        Args:
            mistral_client : Mistral async client instance
            db             : Database connection (Supabase or similar)
            model_id       : Mistral model to use
        """
        self.client        = mistral_client
        self.db            = db
        self.model_id      = model_id
        self.system_prompt = MENTOR_SYSTEM_PROMPT
        self._deleted_conversations: set = set()

    # =========================================================================
    # PUBLIC — backtest-seeded conversation (called by backtest service)
    # =========================================================================

    async def start_backtest_conversation(
        self,
        user_id:          str,
        backtest_context: BacktestContext,
    ) -> Dict[str, Any]:
        """
        Seed a new conversation with the full backtest context and return
        an initial analysis.

        Called service-to-service by the backtest service after a run.
        The returned conversation_id is stored by the frontend and passed
        back for every follow-up question.

        Args:
            user_id          : User's unique identifier
            backtest_context : Strategy config + performance metrics

        Returns:
            {
                analysis        : str   — initial mentor analysis
                conversation_id : str
                backtest_id     : str | None
                timestamp       : str
            }
        """
        conversation_id = str(uuid.uuid4())
        logger.info(
            f"Seeding backtest conversation {conversation_id} "
            f"for user {user_id} | backtest_id={backtest_context.backtest_id}"
        )

        if not DEV_MODE:
            # 1. Create the conversation record
            self.db.mentor.create_conversation(
                id      = conversation_id,
                user_id = user_id,
                title   = f"Backtest: {backtest_context.strategy_type}",
            )

            # 2. Persist backtest context as a system_context message
            context_blob = json.dumps(backtest_context.model_dump(), indent=2)
            self.db.mentor.add_message(
                conversation_id = conversation_id,
                user_id         = user_id,
                role            = "system_context",
                content         = context_blob,
            )

        # 2. Build the initial analysis prompt — specific to this exact run.
        initial_prompt = self._build_initial_analysis_prompt(backtest_context)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": self._format_context_for_llm(backtest_context)},
            {"role": "user",   "content": initial_prompt},
        ]

        # 3. Generate and persist the initial analysis
        analysis = await self._generate_response(messages, max_tokens=1200)
        if not DEV_MODE:
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
    # PUBLIC — ask a question (generic or follow-up on a backtest conversation)
    # =========================================================================

    async def ask_question(
        self,
        user_id:         str,
        message:         str,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ask the mentor a question.

        Works for both generic conversations and backtest follow-ups.
        When the conversation was seeded with backtest context, the mentor
        automatically grounds its answer in that specific strategy and run.

        Args:
            user_id         : User's unique identifier
            message         : User's question
            conversation_id : Continue an existing conversation, or None to start new

        Returns:
            {
                response        : str
                conversation_id : str
                message_count   : int
                timestamp       : str
            }
        """
        try:
            if DEV_MODE:
                # In dev mode — skip DB entirely, use in-memory conversation
                conversation_id  = conversation_id or str(uuid.uuid4())
                history          = []
                backtest_context = None
            elif conversation_id:
                logger.info(f"Loading conversation {conversation_id} for user {user_id}")
                history, backtest_context = await self._load_conversation(conversation_id, user_id)
                if history is None:
                    logger.warning(f"Conversation {conversation_id} not found or unauthorized — starting fresh")
                    conversation_id = str(uuid.uuid4())
                    self.db.mentor.create_conversation(
                        id      = conversation_id,
                        user_id = user_id,
                        title   = None,
                    )
                    history          = []
                    backtest_context = None
            else:
                logger.info(f"Creating new generic conversation for user {user_id}")
                conversation_id = str(uuid.uuid4())
                self.db.mentor.create_conversation(
                    id      = conversation_id,
                    user_id = user_id,
                    title   = None,
                )
                history          = []
                backtest_context = None

            # Build message list for LLM
            messages = self._build_messages(history, message, backtest_context)

            logger.info(f"Generating response for conversation {conversation_id}")
            response = await self._generate_response(messages, max_tokens=2000)

            # Persist user message and assistant response (skip in dev mode)
            if not DEV_MODE:
                await self._save_message(conversation_id, user_id, role="user",      content=message)
                await self._save_message(conversation_id, user_id, role="assistant", content=response)

            message_count = len([m for m in history if m["role"] != "system_context"]) + 2

            logger.info(f"Response generated for conversation {conversation_id}")
            return {
                "response":        response,
                "conversation_id": conversation_id,
                "message_count":   message_count,
                "timestamp":       _utcnow(),
            }

        except Exception as e:
            logger.error(f"Error in ask_question: {e}", exc_info=True)
            raise

    # =========================================================================
    # PUBLIC — backtest pass/fail analysis (stateless, no conversation needed)
    # =========================================================================

    async def analyze_backtest_results(
        self,
        strategy_type: str,
        metrics:       Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate backtest results as a simple PASS or FAIL and explain why.

        Stateless — does not create or require a conversation.
        The backtest service calls this after a run and gets back a verdict
        plus a plain-language educational explanation.

        Args:
            strategy_type : e.g. "mean_reversion", "trend_following"
            metrics       : sharpe_ratio, max_drawdown, total_return,
                            win_rate, total_trades

        Returns:
            {
                verdict     : "PASS" | "FAIL"
                explanation : str
                timestamp   : str
            }
        """
        verdict = self._evaluate_strategy(metrics)
        prompt  = self._build_verdict_prompt(strategy_type, metrics, verdict)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": prompt},
        ]

        try:
            logger.info(
                f"Analyzing backtest — strategy='{strategy_type}' verdict={verdict}"
            )
            explanation = await self._generate_response(messages, max_tokens=800)
            logger.info("Backtest analysis complete.")

            return {
                "verdict":     verdict,
                "explanation": explanation,
                "timestamp":   _utcnow(),
            }

        except Exception as e:
            logger.error(f"Backtest analysis failed: {e}", exc_info=True)
            raise

    # =========================================================================
    # PRIVATE — pass/fail verdict helpers
    # =========================================================================

    @staticmethod
    def _evaluate_strategy(metrics: Dict[str, Any]) -> str:
        """
        Decide PASS or FAIL from the core performance metrics.

        All three conditions must be met to PASS:
          - Sharpe ratio  >= 1.0
          - Total return  >  0 %
          - Max drawdown  <  15 %
        """
        sharpe       = float(metrics.get("sharpe_ratio",  0) or 0)
        total_return = float(metrics.get("total_return",  0) or 0)
        max_drawdown = float(metrics.get("max_drawdown",  0) or 0)

        if sharpe >= 1.0 and total_return > 0 and max_drawdown < 15:
            return "PASS"
        return "FAIL"

    @staticmethod
    def _build_verdict_prompt(
        strategy_type: str,
        metrics:       Dict[str, Any],
        verdict:       str,
    ) -> str:
        """Build the user-turn prompt for the LLM pass/fail analysis."""
       
        def fmt(key, label, suffix=""):
            val = metrics.get(key)
            if val is None:
                return None
            return f"  - {label}: {val}{suffix}"
 
        metric_lines = [
            fmt("pair",                "Currency Pair"),
            fmt("start_date",          "Backtest Start"),
            fmt("end_date",            "Backtest End"),
            fmt("total_return_pct",    "Total Return",       "%"),
            fmt("sharpe_ratio",        "Sharpe Ratio"),
            fmt("sortino_ratio",       "Sortino Ratio"),
            fmt("max_drawdown_pct",    "Max Drawdown",       "%"),
            fmt("win_rate_pct",        "Win Rate",           "%"),
            fmt("profit_factor",       "Profit Factor"),
            fmt("total_trades",        "Total Trades"),
            fmt("winning_trades",      "Winning Trades"),
            fmt("losing_trades",       "Losing Trades"),
            fmt("avg_win",             "Avg Win"),
            fmt("avg_loss",            "Avg Loss"),
            fmt("avg_risk_reward",     "Avg Risk/Reward"),
            fmt("avg_holding_days",    "Avg Holding Days",   " days"),
            fmt("volatility_annual_pct","Annual Volatility", "%"),
            fmt("cagr_pct",            "CAGR",               "%"),
        ]
        metrics_str = "\n".join(line for line in metric_lines if line)
        
        if verdict == "PASS":
            instruction = (
                f"This {strategy_type} strategy PASSED. "
                "Explain clearly why it worked, what market conditions favoured it, "
                "and what risks the trader should still watch going forward."
            )
        else:
            instruction = (
                f"This {strategy_type} strategy FAILED. "
                "Explain clearly why it failed, what the metrics reveal about "
                "what went wrong, and what the trader should learn from this."
            )

        return f"""A trader ran a backtest for a {strategy_type} strategy.

VERDICT: {verdict}

PERFORMANCE METRICS:
{metrics_str}

{instruction}

Important: Start your response directly with the analysis. Do not repeat or reformat the metrics above."""

    # =========================================================================
    # PUBLIC — conversation management
    # =========================================================================

    async def get_conversation_history(
        self,
        conversation_id: str,
        user_id:         str,
    ) -> Optional[List[Dict]]:
        """
        Retrieve full conversation history (excluding internal system_context rows).

        Returns None if the conversation doesn't belong to the user.
        """
        try:
            history, _ = await self._load_conversation(conversation_id, user_id)
            if history is None:
                return None

            return [
                {
                    "role":      msg["role"],
                    "content":   msg["content"],
                    "timestamp": msg.get("timestamp", ""),
                }
                for msg in history
                if msg["role"] != "system_context"
            ]
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}", exc_info=True)
            raise

    async def list_user_conversations(
        self,
        user_id: str,
        limit:   int = 20,
    ) -> List[Dict]:
        """List all conversations for a user with a preview and backtest badge."""
        try:
            rows = self.db.mentor.list_conversations(user_id, limit=limit)

            conversations = []
            for row in rows:
                is_backtest   = row.get("role") == "system_context"
                preview       = row.get("last_response_preview") or row.get("content", "")

                if is_backtest:
                    try:
                        ctx     = json.loads(preview)
                        preview = (
                            f"[Backtest] {ctx.get('strategy_type', 'strategy')} — "
                            f"Sharpe {ctx.get('metrics', {}).get('sharpe_ratio', 'N/A')}"
                        )
                    except (json.JSONDecodeError, KeyError):
                        preview = "[Backtest conversation]"
                else:
                    preview = preview[:100] + "..." if len(preview) > 100 else preview

                conversations.append({
                    "conversation_id": row.get("id"),
                    "started_at":      row.get("created_at", ""),
                    "preview":         preview,
                    "message_count":   row.get("message_count", 0),
                    "is_backtest":     is_backtest,
                })

            return conversations

        except Exception as e:
            logger.error(f"Error listing conversations: {e}", exc_info=True)
            raise

    async def delete_conversation(
        self,
        conversation_id: str,
        user_id:         str,
    ) -> bool:
        """Delete a conversation. Returns True if deleted, False if not found."""
        try:
            # Verify ownership first
            rows = self.db.mentor._msg.select("id") \
                .eq("conversation_id", conversation_id) \
                .eq("user_id", user_id) \
                .limit(1).execute().data

            if not rows:
                logger.warning(f"Conversation {conversation_id} not found or unauthorized")
                return False

            # Delete all messages
            self.db.mentor._msg.delete() \
                .eq("conversation_id", conversation_id) \
                .eq("user_id", user_id) \
                .execute()

            self._deleted_conversations.add(conversation_id)
            logger.info(f"Deleted conversation {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
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
        Assemble the full message list to send to the LLM.

        Structure:
          [system prompt]
          [backtest context block — only for backtest conversations]
          [conversation history — user/assistant turns only]
          [new user message]
        """
        messages = [{"role": "system", "content": self.system_prompt}]

        # Inject backtest context right after system prompt so the model
        # treats it as authoritative background for the whole conversation.
        if backtest_context:
            messages.append({
                "role":    "system",
                "content": self._format_context_for_llm(backtest_context),
            })

        # Add prior turns (skip system_context storage rows)
        for msg in history:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": new_message})
        return messages

    def _build_initial_analysis_prompt(self, ctx: BacktestContext) -> str:
        """
        Construct the first user turn that kicks off a backtest conversation.
        This prompt asks the mentor to produce a full structured analysis of
        this specific run rather than a generic explanation.
        """
        params_str  = "\n".join(f"  - {k}: {v}" for k, v in ctx.parameters.items())
        metrics_str = "\n".join(f"  - {k}: {v}" for k, v in ctx.metrics.items())

        return f"""I just ran a backtest for my {ctx.strategy_type} strategy with these exact settings:

STRATEGY PARAMETERS:
{params_str}

PERFORMANCE RESULTS:
{metrics_str}

Please give me a thorough educational analysis of this specific run:
1. What do these exact metrics tell me about how my strategy performed?
2. Given my specific parameters (e.g. RSI period of {ctx.parameters.get('rsi_period', 'N/A')}, \
stop loss of {ctx.parameters.get('stop_loss_pct', 'N/A')}), why might these results have occurred?
3. Which of my parameter choices likely contributed most to the performance issues?
4. What market conditions would have made these specific settings struggle?
5. What conceptual adjustments to my parameters would you suggest and why?"""

    @staticmethod
    def _format_context_for_llm(ctx: BacktestContext) -> str:
        """
        Format BacktestContext as a clear system-level context block for the LLM.
        Injected before every response so the model never loses track of the run.
        """
        params_str  = "\n".join(f"  {k}: {v}" for k, v in ctx.parameters.items())
        metrics_str = "\n".join(f"  {k}: {v}" for k, v in ctx.metrics.items())
        backtest_ref = f"  backtest_id: {ctx.backtest_id}" if ctx.backtest_id else ""

        return f"""═══ ACTIVE BACKTEST CONTEXT ═══
The user is discussing a specific backtest run. ALL your answers must be
grounded in these exact parameters and results — do not give generic advice.

Strategy Type : {ctx.strategy_type}
{backtest_ref}

Parameters:
{params_str}

Performance Metrics:
{metrics_str}
═══════════════════════════════"""

    # =========================================================================
    # PRIVATE — DB helpers
    # =========================================================================

    async def _load_conversation(
        self,
        conversation_id: str,
        user_id:         str,
    ) -> tuple[Optional[List[Dict]], Optional[BacktestContext]]:
        """
        Load conversation history and reconstruct BacktestContext if present.

        Returns:
            (history, backtest_context)
            None if conversation exists but belongs to a different user.
            [] if conversation doesn't exist (deleted).
        """
        if conversation_id in self._deleted_conversations:
            return [], None

        rows = self.db.mentor.get_history(conversation_id)

        if not rows:
            return [], None

        # Verify ownership — check first row belongs to this user
        full = self.db.mentor._msg.select("user_id") \
            .eq("conversation_id", conversation_id) \
            .limit(1).execute().data
        if full and full[0].get("user_id") != user_id:
            return None, None

        history: List[Dict] = []
        backtest_context: Optional[BacktestContext] = None

        for msg in rows:
            if msg["role"] == "system_context":
                try:
                    backtest_context = BacktestContext(**json.loads(msg["content"]))
                except Exception:
                    logger.warning("Failed to deserialise stored BacktestContext — ignoring.")
            else:
                history.append({
                    "role":      msg["role"],
                    "content":   msg["content"],
                    "timestamp": msg.get("created_at", ""),
                })

        return history, backtest_context

    async def _save_message(
        self,
        conversation_id: str,
        user_id:         str,
        role:            str,
        content:         str,
    ) -> None:
        """Insert a single message via MentorRepo."""
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
    # PRIVATE — LLM call with retry
    # =========================================================================

    async def _generate_response(
        self,
        messages:   List[Dict],
        max_tokens: int = 2000,
    ) -> str:
        """
        Call the Mistral API with exponential back-off retry (3 attempts).
        """
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
                    await asyncio.sleep(2 ** attempt)   # 1s, 2s

        logger.error(f"All LLM retries failed: {last_error}", exc_info=True)
        raise last_error
