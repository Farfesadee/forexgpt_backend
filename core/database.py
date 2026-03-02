
# """
# core/database.py — Supabase Client & Repository Layer

# Provides one typed repository class per table, matching the service layer:
#     db.mentor          → mentor_conversations + mentor_messages
#     db.quant           → quant_sessions + quant_messages
#     db.signals         → signals
#     db.strategies      → strategies
#     db.backtests       → backtests + backtest_trades
#     db.llm_log         → llm_request_log      (write-only for services)
#     db.activity        → activity_log         (write-only for services)
#     db.profiles        → profiles

# FastAPI services use the service_role key → bypasses RLS.
# The React frontend uses the anon key → RLS enforced.
# """

# import logging
# from typing import Optional
# from supabase import create_client, Client
# from core.config import settings

# logger = logging.getLogger(__name__)

# _client: Optional[Client] = None

# def get_db() -> Client:
#     """Return (or lazily create) the Supabase service_role client singleton."""
#     global _client
#     if _client is None:
#         _client = create_client(
#             settings.SUPABASE_URL,
#             settings.SUPABASE_SERVICE_ROLE_KEY,  # bypasses RLS — backend only
#         )
#         logger.info("Supabase client initialised")
#     return _client

# # Profiles section
# # api/routes/auth.py, models/user.py

# class ProfilesRepo:
#     @property
#     def _t(self): return get_db().table("profiles")

#     def get(self, user_id: str) -> dict:
#         return self._t.select("*").eq("id", user_id).single().execute().data

#     def update(self, user_id: str, data: dict) -> dict:
#         res = self._t.update(data).eq("id", user_id).execute()
#         return res.data[0] if res.data else {}

#     def get_dashboard(self, user_id: str) -> dict:
#         """Calls the user_dashboard VIEW — aggregates all 5 module stats."""
#         return get_db().table("user_dashboard").select("*").eq("id", user_id).single().execute().data

#     def increment_counter(self, user_id: str, module: str) -> None:
#         """
#         Atomically increments the per-module counter.
#         module: 'mentor' | 'quant' | 'signals' | 'strategies' | 'backtests'
#         Called by each service after a successful response.
#         """
#         get_db().rpc("increment_usage_counter", {
#             "p_user_id": user_id,
#             "p_module":  module,
#         }).execute()

# # Mentor 
# # api/routes/mentor.py, services/mentor_service.py
# class MentorRepo:
#     @property
#     def _conv(self): return get_db().table("mentor_conversations")
#     @property
#     def _msg(self):  return get_db().table("mentor_messages")

#     # Conversations
#     def list_conversations(self, user_id: str, include_archived: bool = False, limit: int = 30) -> list[dict]:
#         q = get_db().table("mentor_history").select("*").eq("user_id", user_id)
#         if not include_archived:
#             q = q.eq("is_archived", False)
#         return q.limit(limit).execute().data

#     def create_conversation(self, user_id: str, difficulty: str = "intermediate") -> dict:
#         res = self._conv.insert({"user_id": user_id, "difficulty": difficulty}).execute()
#         return res.data[0]

#     def archive_conversation(self, conversation_id: str) -> None:
#         self._conv.update({"is_archived": True}).eq("id", conversation_id).execute()

#     # Messages
#     def get_history(self, conversation_id: str, limit: int = 40) -> list[dict]:
#         """
#         Returns the last N messages for conversation context.
#         mentor_service.py passes these as the messages[] array to the LLM.
#         """
#         return (
#             self._msg.select("role, content, created_at, topic_tags, follow_up_questions, thumbs_up")
#             .eq("conversation_id", conversation_id)
#             .order("created_at")
#             .limit(limit)
#             .execute().data
#         )

#     def add_message(self, conversation_id: str, user_id: str, role: str, content: str, **meta) -> dict:
#         payload = {"conversation_id": conversation_id, "user_id": user_id, "role": role, "content": content, **meta}
#         return self._msg.insert(payload).execute().data[0]

#     def set_feedback(self, message_id: str, thumbs_up: bool) -> None:
#         self._msg.update({"thumbs_up": thumbs_up}).eq("id", message_id).execute()

# # Quant Finance 
# # api/routes/quant_finance.py, services/quant_finance_service.py
# class QuantRepo:
#     @property
#     def _sess(self): return get_db().table("quant_sessions")
#     @property
#     def _msg(self):  return get_db().table("quant_messages")

#     # Sessions
#     def list_sessions(self, user_id: str, domain: Optional[str] = None, limit: int = 30) -> list[dict]:
#         q = get_db().table("quant_history").select("*").eq("user_id", user_id).eq("is_archived", False)
#         if domain:
#             q = q.eq("quant_domain", domain)
#         return q.limit(limit).execute().data

#     def create_session(self, user_id: str, quant_domain: str = "general", difficulty: str = "intermediate") -> dict:
#         res = self._sess.insert({
#             "user_id": user_id,
#             "quant_domain": quant_domain,
#             "difficulty": difficulty,
#         }).execute()
#         return res.data[0]

#     def archive_session(self, session_id: str) -> None:
#         self._sess.update({"is_archived": True}).eq("id", session_id).execute()

#     def get_domain_stats(self, user_id: str) -> list[dict]:
#         """Per-domain usage breakdown — used by quant_finance_service for suggestions."""
#         return get_db().rpc("get_quant_domain_stats", {"p_user_id": user_id}).execute().data

#     # Messages
#     def get_history(self, session_id: str, limit: int = 40) -> list[dict]:
#         """Returns messages for LLM context window — quant_finance_service.py."""
#         return (
#             self._msg.select("role, content, created_at, contains_formula, system_prompt_key, thumbs_up")
#             .eq("session_id", session_id)
#             .order("created_at")
#             .limit(limit)
#             .execute().data
#         )

#     def add_message(self, session_id: str, user_id: str, role: str, content: str, **meta) -> dict:
#         payload = {"session_id": session_id, "user_id": user_id, "role": role, "content": content, **meta}
#         return self._msg.insert(payload).execute().data[0]

#     def set_feedback(self, message_id: str, thumbs_up: bool) -> None:
#         self._msg.update({"thumbs_up": thumbs_up}).eq("id", message_id).execute()

# # Signals 
# # api/routes/signals.py, services/signal_service.py

# class SignalsRepo:
#     @property
#     def _t(self): return get_db().table("signals")

#     def create(self, user_id: str, data: dict) -> dict:
#         return self._t.insert({"user_id": user_id, **data}).execute().data[0]

#     def list(
#         self, user_id: str,
#         source_type: Optional[str] = None,
#         sentiment: Optional[str] = None,
#         pair: Optional[str] = None,
#         saved_only: bool = False,
#         limit: int = 20,
#         offset: int = 0,
#     ) -> list[dict]:
#         q = (
#             self._t.select(
#                 "id, source_type, source_label, base_currency, primary_sentiment, "
#                 "primary_direction, primary_strength, affected_pairs, confidence, "
#                 "hf_endpoint_id, hf_model_version, is_saved, created_at"
#             ).eq("user_id", user_id)
#         )
#         if source_type:  q = q.eq("source_type", source_type)
#         if sentiment:    q = q.eq("primary_sentiment", sentiment)
#         if saved_only:   q = q.eq("is_saved", True)
#         if pair:         q = q.contains("affected_pairs", [pair])
#         return q.order("created_at", desc=True).range(offset, offset + limit - 1).execute().data

#     def get(self, signal_id: str) -> dict:
#         return self._t.select("*").eq("id", signal_id).single().execute().data

#     def get_for_pair(self, user_id: str, pair: str, source_type: Optional[str] = None, limit: int = 20) -> list[dict]:
#         return get_db().rpc("get_signals_for_pair", {
#             "p_user_id": user_id, "p_pair": pair,
#             "p_source_type": source_type, "p_limit": limit, "p_offset": 0,
#         }).execute().data

#     def update(self, signal_id: str, data: dict) -> None:
#         self._t.update(data).eq("id", signal_id).execute()

# # Strategies 
# # api/routes/codegen.py, services/codegen_service.py
# class StrategiesRepo:
#     @property
#     def _t(self): return get_db().table("strategies")

#     def create(self, user_id: str, data: dict) -> dict:
#         return self._t.insert({"user_id": user_id, **data}).execute().data[0]

#     def list(self, user_id: str, strategy_type: Optional[str] = None, limit: int = 30) -> list[dict]:
#         q = (
#             self._t.select(
#                 "id, name, description, strategy_type, target_pairs, timeframe, "
#                 "complexity, sandbox_passed, is_saved, created_at"
#             ).eq("user_id", user_id)
#         )
#         if strategy_type: q = q.eq("strategy_type", strategy_type)
#         return q.order("created_at", desc=True).limit(limit).execute().data

#     def get(self, strategy_id: str) -> dict:
#         return self._t.select("*").eq("id", strategy_id).single().execute().data

#     def update(self, strategy_id: str, data: dict) -> dict:
#         return self._t.update(data).eq("id", strategy_id).execute().data[0]

#     def delete(self, strategy_id: str) -> None:
#         self._t.delete().eq("id", strategy_id).execute()

#     def get_leaderboard(self, limit: int = 20) -> list[dict]:
#         return get_db().table("strategy_leaderboard").select("*").limit(limit).execute().data

# # Backtests 
# # api/routes/backtest.py, services/backtest_service.py
# class BacktestsRepo:
#     @property
#     def _bt(self):  return get_db().table("backtests")
#     @property
#     def _tr(self):  return get_db().table("backtest_trades")

#     def create(self, user_id: str, data: dict) -> dict:
#         return self._bt.insert({"user_id": user_id, "status": "pending", **data}).execute().data[0]

#     def set_status(self, backtest_id: str, status: str, error: Optional[str] = None) -> None:
#         payload = {"status": status}
#         if error: payload["error_message"] = error
#         self._bt.update(payload).eq("id", backtest_id).execute()

#     def save_results(self, backtest_id: str, results: dict) -> None:
#         """
#         Saves completed results and triggers denormalization of key metrics.
#         The sync_backtest_on_complete trigger fires and fills:
#         sharpe_ratio, total_return_pct, max_drawdown_pct, etc.
#         """
#         self._bt.update({
#             "status":                   "completed",
#             "metrics":                  results["metrics"],
#             "equity_curve":             results["equity_curve"],
#             "educational_analysis":     results.get("educational_analysis", ""),
#             "improvement_suggestions":  results.get("improvement_suggestions", []),
#         }).eq("id", backtest_id).execute()

#     def save_trades(self, backtest_id: str, user_id: str, trades: list[dict]) -> None:
#         if not trades:
#             return
#         rows = [{"backtest_id": backtest_id, "user_id": user_id, "trade_number": i + 1, **t}
#                 for i, t in enumerate(trades)]
#         self._tr.insert(rows).execute()

#     def list(self, user_id: str, pair: Optional[str] = None, limit: int = 20) -> list[dict]:
#         q = (
#             self._bt.select(
#                 "id, strategy_id, pair, start_date, end_date, timeframe, "
#                 "initial_capital, status, total_return_pct, sharpe_ratio, "
#                 "max_drawdown_pct, win_rate_pct, total_trades, is_saved, created_at"
#             ).eq("user_id", user_id).eq("status", "completed")
#         )
#         if pair: q = q.eq("pair", pair)
#         return q.order("created_at", desc=True).limit(limit).execute().data

#     def get(self, backtest_id: str) -> dict:
#         return self._bt.select("*").eq("id", backtest_id).single().execute().data

#     def get_trades(self, backtest_id: str, limit: int = 500, offset: int = 0) -> list[dict]:
#         return (
#             self._tr.select("*")
#             .eq("backtest_id", backtest_id)
#             .order("trade_number")
#             .range(offset, offset + limit - 1)
#             .execute().data
#         )


# # LLM Request Log 
# # core/llm_router.py
# class LLMLogRepo:
#     def log(
#         self,
#         user_id: str,
#         source_module: str,
#         system_prompt_key: Optional[str],
#         model_used: str,
#         adapter_used: Optional[str],
#         hf_endpoint_id: Optional[str],
#         input_tokens: Optional[int],
#         output_tokens: Optional[int],
#         latency_ms: Optional[int],
#         success: bool,
#         error_type: Optional[str] = None,
#         error_message: Optional[str] = None,
#         fallback_used: bool = False,
#         entity_type: Optional[str] = None,
#         entity_id: Optional[str] = None,
#     ) -> str:
#         """Called by core/llm_router.py after every model invocation."""
#         res = get_db().rpc("log_llm_request", {
#             "p_user_id":          user_id,
#             "p_source_module":    source_module,
#             "p_system_prompt_key": system_prompt_key,
#             "p_model_used":       model_used,
#             "p_adapter_used":     adapter_used,
#             "p_hf_endpoint_id":   hf_endpoint_id,
#             "p_input_tokens":     input_tokens,
#             "p_output_tokens":    output_tokens,
#             "p_latency_ms":       latency_ms,
#             "p_success":          success,
#             "p_error_type":       error_type,
#             "p_error_message":    error_message,
#             "p_fallback_used":    fallback_used,
#             "p_entity_type":      entity_type,
#             "p_entity_id":        entity_id,
#         }).execute()
#         return res.data

#     def get_stats(self) -> list[dict]:
#         """Returns the llm_router_stats view — adapter performance summary."""
#         return get_db().table("llm_router_stats").select("*").execute().data

# # Activity Log 
# # all api/routes/*.py
# class ActivityRepo:
#     def log(
#         self,
#         user_id: str,
#         action: str,
#         entity_type: Optional[str] = None,
#         entity_id: Optional[str] = None,
#         metadata: Optional[dict] = None,
#     ) -> None:
#         get_db().rpc("log_activity", {
#             "p_user_id":     user_id,
#             "p_action":      action,
#             "p_entity_type": entity_type,
#             "p_entity_id":   entity_id,
#             "p_metadata":    metadata or {},
#         }).execute()

# # Single Database Access Object 
# class Database:
#     """
#     Single import point for all repos.

#     Usage in services:
#         from core.database import db
#         db.mentor.add_message(...)
#         db.signals.create(user_id, {...})
#         db.llm_log.log(...)
#     """
#     profiles   = ProfilesRepo()
#     mentor     = MentorRepo()
#     quant      = QuantRepo()
#     signals    = SignalsRepo()
#     strategies = StrategiesRepo()
#     backtests  = BacktestsRepo()
#     llm_log    = LLMLogRepo()
#     activity   = ActivityRepo()

# db = Database()

from supabase import create_client, Client
from core.config import settings

def get_supabase_client() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

supabase = get_supabase_client()