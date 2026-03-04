# ForexGPT — Database Reference

Complete documentation for the ForexGPT Supabase database layer: schema, migrations, RLS policies, views, functions, and the Python repository layer.

---

## Table of Contents

1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [Running Migrations](#running-migrations)
4. [Schema — 11 Tables](#schema--11-tables)
   - [profiles](#1-profiles)
   - [mentor_conversations](#2-mentor_conversations)
   - [mentor_messages](#3-mentor_messages)
   - [quant_sessions](#4-quant_sessions)
   - [quant_messages](#5-quant_messages)
   - [signals](#6-signals)
   - [strategies](#7-strategies)
   - [backtests](#8-backtests)
   - [backtest_trades](#9-backtest_trades)
   - [llm_request_log](#10-llm_request_log)
   - [activity_log](#11-activity_log)
5. [Triggers](#triggers)
6. [Row Level Security](#row-level-security)
7. [Views — 5 Views](#views--5-views)
8. [Functions — 5 RPCs](#functions--5-rpcs)
9. [Python Repository Layer](#python-repository-layer)
10. [Environment Variables](#environment-variables)
11. [Key Design Decisions](#key-design-decisions)

---

## Overview

ForexGPT uses **Supabase** (hosted Postgres) as its sole database. The schema is divided across three ordered migrations:

| File | Purpose |
|------|---------|
| `001_core_schema.sql` | All 11 tables, indexes, and triggers |
| `002_rls_policies.sql` | Row Level Security policies for every table |
| `003_views_functions.sql` | 5 views and 5 RPC helper functions |

The FastAPI backend accesses Postgres exclusively through `core/database.py`, which provides a typed repository class per table. Services never write raw SQL — they call repository methods which call the Supabase Python client.

**Two Supabase keys are in use:**

| Key | Used by | RLS |
|-----|---------|-----|
| `SUPABASE_ANON_KEY` | Auth operations in `api/routes/auth.py` | Enforced |
| `SUPABASE_SERVICE_ROLE_KEY` | All DB reads/writes in `core/database.py` | Bypassed |

---

## File Structure

```
forexgpt_supabase/
├── migrations/
│   ├── 001_core_schema.sql      # Tables, indexes, triggers
│   ├── 002_rls_policies.sql     # Row Level Security
│   └── 003_views_functions.sql  # Views + RPC functions
├── database.py                  # Python repository layer (→ core/database.py)
└── SCHEMA_REFERENCE.sql         # Quick-reference column listing
```

---

## Running Migrations

Migrations must be run **in order** in the Supabase SQL Editor or via the CLI.

### Via Supabase Dashboard

1. Open your project → **SQL Editor**
2. Paste and run `001_core_schema.sql`
3. Paste and run `002_rls_policies.sql`
4. Paste and run `003_views_functions.sql`

### Via Supabase CLI

```bash
supabase db push
```

Or run each file directly:

```bash
supabase db execute --file migrations/001_core_schema.sql
supabase db execute --file migrations/002_rls_policies.sql
supabase db execute --file migrations/003_views_functions.sql
```

### Re-running migrations

All functions and views use `CREATE OR REPLACE` and are safe to re-run. Tables use `CREATE TABLE` (not `IF NOT EXISTS`) — drop them first if re-running from scratch:

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```


---

## Schema — 11 Tables

### 1. `profiles`

**Owned by:** `api/routes/auth.py`, `models/user.py`

Extends Supabase's built-in `auth.users` with app-specific fields. One row per user, auto-created by the `handle_new_user` trigger the moment a user signs up.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | FK → `auth.users(id)` |
| `email` | `TEXT` | Copied from `auth.users` at signup |
| `display_name` | `TEXT` | Nullable; set from `full_name` meta or email prefix |
| `avatar_url` | `TEXT` | Optional profile picture |
Forwarded to `system_prompts.py` to personalise LLM responses |
| `created_at` | `TIMESTAMPTZ` | Auto-set |
| `updated_at` | `TIMESTAMPTZ` | Auto-updated by trigger |

---

### 2. `mentor_conversations`

**Owned by:** `api/routes/mentor.py`, `services/mentor_service.py`

Groups mentor messages into logical sessions. The title is auto-generated from the first question asked and shown in the sidebar.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `user_id` | `UUID FK` | → `profiles(id)` |
| `title` | `TEXT` | Auto-generated from first message |
| `is_archived` | `BOOLEAN` | Soft delete; hidden from default list view |
| `last_message_at` | `TIMESTAMPTZ` | Used to sort sidebar by recency |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | Auto-updated by trigger |

**Indexes:** `user_id`, `last_message_at DESC`

---

### 3. `mentor_messages`

**Owned by:** `api/routes/mentor.py`, `services/mentor_service.py`

Individual messages within a mentor conversation. Both user questions and assistant answers are stored here. The `role` column mirrors the OpenAI message format used by the Mistral/Claude API.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `conversation_id` | `UUID FK` | → `mentor_conversations(id)` |
| `user_id` | `UUID FK` | → `profiles(id)` |
| `role` | `TEXT` | `user` \| `assistant` \| `system` |
| `content` | `TEXT` | Full message text |
| `topic_tags` | `TEXT[]` | Populated on assistant messages by `mentor_service.py` |
| `related_concepts` | `TEXT[]` | Adjacent topics worth exploring |
| `follow_up_questions` | `TEXT[]` | 3 suggested next questions, parsed from LLM output |
| `thumbs_up` | `BOOLEAN` | `NULL` = no feedback, `TRUE` = helpful, `FALSE` = not helpful |
| `created_at` | `TIMESTAMPTZ` | |

**Indexes:** `conversation_id`, `user_id`

---

### 4. `generated_codes`

**Owned by:** `api/routes/codegen.py`, `services/codegen_service.py`


| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `user_id` | `UUID FK` | → `profiles(id)` |
| `conversation_id` | `UUID FK` |
| `strategy_name` | `TEXT[]` | |
| `description` | `TEXT` |  |
| `difficulty` | `TEXT` | `beginner` \| `intermediate` \| `advanced` |
| `code` | `TEXT` | |
| `language` | `TEXT` | |
| `is_runnable` | `BOOLEAN` | |
| `last_validated` | `TIMESTAMPTZ` | |
| `created_at` | `TIMESTAMPTZ` | |

**Indexes:** `user_id`, `last_message_at DESC`, `quant_domain`

---

### 5. ``

**Owned by:** `api/routes/codegen.py`, `services/codegen_service.py`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `conv_id` | `UUID FK` |  |
| `user_id` | `UUID FK` | → `profiles(id)` |
| `role` | `TEXT` | `user` \| `assistant` |
| `content` | `TEXT` | |
| `model_version` | `TEXT` | |
| `tokens_used` | `INTEGER` | |
| `created_at` | `TIMESTAMPTZ` | |

**Indexes:** `conv_id`, `user_id`

---

### 6. `signals`

**Owned by:** `api/routes/signals.py`, `services/signal_service.py`

Stores extracted directional signals from Forex news, central bank speeches, economic reports, and earnings calls. The `extraction_result` JSONB column holds the full structured output from the HuggingFace fine-tuned model. Key fields are denormalized to flat columns for fast filtering.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `user_id` | `UUID FK` | → `profiles(id)` |
| `company_name` | `TEXT` |  |
| `currency_pair` | `TEXT` | |
| `transcript_excerpt` | `TEXT` | | 
| `extraction_result` | `JSONB` | |
| `confidence` | `NUMERIC(4,3)` | 0.000–1.000 |
| `magnitude` | `TEXT` |  |
| `direction` | `TEXT` |  |
| `reasoning` | `TEXT` |  |
| `time_horizon` | `TEXT` | |
| `user_notes` | `TEXT` | Optional user annotation |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | Auto-updated |

**Indexes:** `user_id`, `currency_pair` (GIN), `created_at DESC`

---


### 8. `backtests`

**Owned by:** `api/routes/backtest.py`, `services/backtest_service.py`

One row per backtest run. The full `metrics` and `equity_curve` are stored as JSONB. The `sync_backtest_on_complete` trigger automatically denormalizes the 8 most-queried metric fields to flat columns when `status` transitions to `completed`, enabling fast leaderboard ordering without parsing JSONB.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `user_id` | `UUID FK` | → `profiles(id)` |
| `strategy_id` | `UUID FK` | → `strategies(id)`. `NULL` if inline code was used |
| `pair` | `TEXT` | yfinance ticker, e.g. `EURUSD=X` |
| `start_date` | `DATE` | |
| `end_date` | `DATE` | |
| `timeframe` | `TEXT` | `1m` \| `5m` \| `15m` \| `1h` \| `4h` \| `1d` |
| `initial_capital` | `NUMERIC(12,2)` | Default `10,000` |
| `spread_pips` | `NUMERIC(6,2)` | From `TradingCosts` model |
| `commission_per_lot` | `NUMERIC(6,2)` | Round-trip USD per standard lot |
| `slippage_pips` | `NUMERIC(6,2)` | Per-execution slippage |
| `leverage` | `INTEGER` | Default `30` |
| `status` | `TEXT` | `pending` → `running` → `completed` \| `failed` |
| `error_message` | `TEXT` | Populated on `failed` status |
| `equity_curve` | `JSONB` | `[{date, equity, drawdown}, ...]` time series |
| `total_return_pct` | `NUMERIC(8,2)` | **Denormalized** by trigger on completion |
| `improvement_suggestions` | `TEXT[]` | Actionable suggestions |
| `is_saved` | `BOOLEAN` | User bookmarked |
| `user_notes` | `TEXT` | Optional annotation |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | Auto-updated |
| `completed_at` | `TIMESTAMPTZ` | Set by trigger on completion |

**Indexes:** `user_id`, `strategy_id`, `pair`, `status`, `created_at DESC`

---

### 9. `backtest_trades`

**Owned by:** `services/backtest_service.py`

Individual trade ledger, kept separate from `backtests` because high-frequency strategies can generate 1,000+ trades. Fetched via a paginated `GET /backtest/results/{id}/trades` endpoint rather than being bundled with the main backtest row.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `backtest_id` | `UUID FK` | → `backtests(id)` CASCADE DELETE |
| `user_id` | `UUID FK` | → `profiles(id)` |
| `trade_number` | `INTEGER` | Sequential within the backtest |
| `direction` | `TEXT` | `long` \| `short` |
| `entry_time` | `TIMESTAMPTZ` | Bar open time of entry |
| `exit_time` | `TIMESTAMPTZ` | Bar time of exit |
| `entry_price` | `NUMERIC(12,5)` | |
| `exit_price` | `NUMERIC(12,5)` | |
| `lot_size` | `NUMERIC(8,2)` | Standard lots |
| `pnl_pips` | `NUMERIC(10,2)` | Net pips after costs |
| `pnl_usd` | `NUMERIC(12,2)` | Net USD including swap |
| `duration_hours` | `NUMERIC(8,2)` | Hours between entry and exit |
| `created_at` | `TIMESTAMPTZ` | |

**Indexes:** `backtest_id`, `user_id`, `entry_time`

---

### 10. `llm_request_log`

**Owned by:** `core/llm_router.py`

Append-only audit log of every LLM call routed through `llm_router.py`. Never updated or deleted. Used for cost tracking, latency analysis, adapter A/B testing, and failure rate monitoring. Not exposed to users — read exclusively via `service_role` key.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `user_id` | `UUID FK` | `SET NULL` on user delete |
| `source_module` | `TEXT` | `mentor_service` \| `quant_finance_service` \| `signal_service` \| `codegen_service` \| `backtest_service` |
| `system_prompt_key` | `TEXT` | e.g. `mentor_intermediate` |
| `model_used` | `TEXT` | e.g. `claude-sonnet-4-6` |
| `adapter_used` | `TEXT` | LoRA adapter name or `NULL` |
| `hf_endpoint_id` | `TEXT` | HuggingFace endpoint ID or `NULL` |
| `input_tokens` | `INTEGER` | |
| `output_tokens` | `INTEGER` | |
| `total_tokens` | `INTEGER` | **Generated column**: `input + output` |
| `latency_ms` | `INTEGER` | End-to-end |
| `success` | `BOOLEAN` | |
| `error_type` | `TEXT` | e.g. `timeout`, `rate_limit` |
| `error_message` | `TEXT` | Truncated to 500 chars |
| `fallback_used` | `BOOLEAN` | `TRUE` if primary model failed and fallback was used |
| `entity_type` | `TEXT` | e.g. `mentor_message` |
| `entity_id` | `UUID` | FK to the resulting entity |
| `created_at` | `TIMESTAMPTZ` | |

**Indexes:** `user_id`, `source_module`, `model_used`, `success`, `created_at DESC`

---

### 11. `activity_log`

**Owned by:** All `api/routes/*.py` handlers

Append-only product analytics log. Every meaningful user action is recorded here. Never updated. Written by the backend with `service_role` key; users can read their own rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID PK` | |
| `user_id` | `UUID FK` | → `profiles(id)` CASCADE DELETE |
| `action` | `TEXT` | See action vocabulary below |
| `entity_type` | `TEXT` | e.g. `mentor_conversation`, `backtest` |
| `entity_id` | `UUID` | The specific record |
| `metadata` | `JSONB` | Action-specific context |
| `created_at` | `TIMESTAMPTZ` | |

**Action vocabulary:**

| Module | Actions |
|--------|---------|
| Auth | `signed_up`, `signed_in`, `signed_out`, `email_confirmed`, `password_updated`, `plan_upgraded` |
| Mentor | `mentor_question_asked`, `mentor_message_feedback` |
| Quant | `quant_question_asked`, `quant_message_feedback` |
| Signals | `signal_extracted`, `signal_saved`, `signal_shared` |
| Codegen | `strategy_generated`, `strategy_saved`, `strategy_validated` |
| Backtest | `backtest_started`, `backtest_completed`, `backtest_failed` |

**Indexes:** `user_id`, `action`, `(entity_type, entity_id)`, `created_at DESC`

---

## Triggers

| Trigger | Table | Function | Fires |
|---------|-------|----------|-------|
| `on_auth_user_created` | `auth.users` | `handle_new_user()` | `AFTER INSERT` — auto-creates the `profiles` row |
| `profiles_updated_at` | `profiles` | `set_updated_at()` | `BEFORE UPDATE` |
| `mentor_conversations_updated_at` | `mentor_conversations` | `set_updated_at()` | `BEFORE UPDATE` |
| `codegen_conv_updated_at` | `quant_sessions` | `set_updated_at()` | `BEFORE UPDATE` |
| `signals_updated_at` | `signals` | `set_updated_at()` | `BEFORE UPDATE` |
| `backtests_updated_at` | `backtests` | `set_updated_at()` | `BEFORE UPDATE` |
| `backtest_on_complete` | `backtests` | `sync_backtest_on_complete()` | `BEFORE UPDATE` — denormalizes metrics when `status → completed` |

### `handle_new_user`

Runs as `SECURITY DEFINER` (elevated privileges). Inserts into `public.profiles` using data from `auth.users.raw_user_meta_data`. This is why the `profiles` table has no `INSERT` RLS policy — the trigger handles it.

### `sync_backtest_on_complete`

When `backtests.status` transitions to `completed`, this trigger copies the 8 key metrics from the `metrics` JSONB blob into flat columns (`sharpe_ratio`, `total_return_pct`, `max_drawdown_pct`, etc.) and sets `completed_at = NOW()`. This enables the leaderboard and list views to sort and filter by these values without parsing JSONB on every query.

---

## Row Level Security

RLS is enabled on all 11 tables. The default is **DENY ALL** — every table starts with zero access, and policies grant narrowly scoped permissions.

### Policy philosophy

- Users can only access rows where `user_id = auth.uid()`
- The FastAPI backend uses `service_role` key which **bypasses RLS entirely**
- Append-only tables (`llm_request_log`) have no user policies — the service writes them

### Policy summary

| Table | SELECT | INSERT | UPDATE | DELETE |
|-------|--------|--------|--------|--------|
| `profiles` | owner | trigger only | owner | — |
| `mentor_conversations` | owner | owner | owner | owner |
| `mentor_messages` | owner | owner | owner (feedback only) | — |
| `codegen_conv` | owner | owner | owner | owner |
| `generated_codes` | owner | owner | owner (feedback only) | — |
| `signals` | owner | owner | owner | owner |
| `backtests` | owner | owner | owner | owner |
| `backtest_trades` | owner | service_role | — | — |
| `llm_request_log` | — | service_role | — | — |
| `activity_log` | owner | service_role | — | — |

---

## Views 

### `user_dashboard`

**Called by:** `GET /auth/me/dashboard`

Joins `profiles` with all 5 module tables to produce aggregated stats. Returns one row per user. Exposed via `db.profiles.get_dashboard(user_id)`.

Key computed columns: `active_mentor_conversations`, `active_codegen_conv`, `total_signals`, `validated_strategies`, `completed_backtests`, `avg_return_pct`, `last_mentor_activity`.

---

### `mentor_history`

**Called by:** `GET /mentor/conversations`

Extends `mentor_conversations` with two correlated subquery columns: `last_response_preview` (first 140 chars of the most recent assistant message) and `last_model_used`. Used to render the conversation sidebar without loading full message histories.

---


### `llm_router_stats`

**Called by:** Internal analytics / admin dashboard

Daily rollup of `llm_request_log` grouped by `source_module`, `model_used`, `adapter_used`, and `system_prompt_key`. Computes `total_requests`, `successful`, `failed`, `fallbacks`, `avg_latency_ms`, `p95_latency_ms`, `total_tokens`, `avg_tokens_per_request`.

---

## Functions — 5 RPCs

All functions run as `SECURITY DEFINER` and are called via `db.rpc()` from `core/database.py`. They never need to be called from user-facing frontend code directly.

### `increment_usage_counter(p_user_id, p_module)`

Atomically increments the per-module usage counter on `profiles`. Called by each service after a successful LLM response.

```python
# Called in services after each successful response
db.profiles.increment_counter(user_id, "mentor")    # → mentor_questions_asked + 1
db.profiles.increment_counter(user_id, "backtests") # → backtests_run + 1
```

Valid values for `p_module`: `mentor`, `quant`, `signals`, `strategies`, `backtests`.

---

### `log_llm_request(...)`

Inserts one row into `llm_request_log`. Called by `core/llm_router.py` after every model invocation, whether successful or failed. Returns the new row's `UUID`.

```python
db.llm_log.log(
    user_id=user_id,
    source_module="mentor_service",
    system_prompt_key="mentor_intermediate",
    model_used="claude-sonnet-4-6",
    input_tokens=1100,
    output_tokens=820,
    latency_ms=2340,
    success=True,
    entity_type="mentor_message",
    entity_id=message_id,
)
```

---

### `log_activity(p_user_id, p_action, p_entity_type, p_entity_id, p_metadata)`

Appends a row to `activity_log`. Called by all route handlers after successful operations. `p_entity_type` and `p_entity_id` are optional.

```python
db.activity.log(
    user_id=user_id,
    action="backtest_completed",
    entity_type="backtest",
    entity_id=backtest_id,
    metadata={"pair": "EURUSD=X", "sharpe": 1.12, "trades": 86},
)
```

---

### `get_signals_for_pair(p_user_id, p_pair, p_source_type, p_limit, p_offset)`

Returns `signals` rows where `p_pair` is in `affected_pairs[]`. Uses the GIN index for efficient array containment queries. Called by `SignalsRepo.get_for_pair()`.

---

### `get_quant_domain_stats(p_user_id)`

Returns per-domain session and message counts for a user. Called by `quant_finance_service.py` to surface under-explored domains and suggest what to study next.

---

## Python Repository Layer

`core/database.py` provides a single `db` singleton with one typed repository per table group. Services import `db` and call methods — they never write raw SQL or use the Supabase client directly.

```python
from core.database import db

# Profiles
db.profiles.get(user_id)
db.profiles.update(user_id, {"display_name": "Alex"})
db.profiles.get_dashboard(user_id)
db.profiles.increment_counter(user_id, "mentor")

# Mentor
db.mentor.create_conversation(user_id, "intermediate")
db.mentor.list_conversations(user_id, include_archived=False)
db.mentor.get_history(conversation_id, limit=20)
db.mentor.add_message(conversation_id, user_id, "assistant", content, topic_tags=[...])
db.mentor.set_feedback(message_id, thumbs_up=True)
db.mentor.archive_conversation(conversation_id)

# Quant
db.quant.create_session(user_id, "statistics", "advanced")
db.quant.list_sessions(user_id, domain="risk_models")
db.quant.get_domain_stats(user_id)
db.quant.add_message(session_id, user_id, "assistant", content, formula_latex=[...])

# Signals
db.signals.create(user_id, {...})
db.signals.list(user_id, source_type="central_bank", sentiment="hawkish")
db.signals.get_for_pair(user_id, "EUR/USD")
db.signals.update(signal_id, {"is_saved": True})



# Backtests
db.backtests.create(user_id, {...})
db.backtests.set_status(backtest_id, "running")
db.backtests.save_results(backtest_id, results_dict)
db.backtests.save_trades(backtest_id, user_id, trades_list)
db.backtests.get_trades(backtest_id, limit=500)

# Logging (called by llm_router.py and route handlers)
db.llm_log.log(user_id, source_module, ...)
db.activity.log(user_id, action, entity_type, entity_id, metadata)
```

### Two Supabase clients

The repository layer initialises one client via `get_db()` using the `service_role` key. Auth operations in `api/routes/auth.py` use a **separate** client created with the `anon` key, because Supabase Auth methods (`sign_up`, `sign_in_with_password`, `verify_otp`) require the anon key — not the service role key.

```python
# core/database.py — service_role (bypasses RLS)
_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

# api/routes/auth.py — anon key (for auth operations only)
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
```

---

## Environment Variables

All secrets are loaded from `.env` via `core/config.py`. Required variables for the database layer:

```env
# Supabase project URL
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co

# Anon key — used by api/routes/auth.py for auth operations
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Service role key — used by core/database.py for all DB reads/writes
# Never expose this to the frontend
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# JWT secret — used by auth_middleware.py to verify tokens locally (no network call)
# Found at: Supabase Dashboard → Project Settings → API → JWT Secret
SUPABASE_JWT_SECRET=your-jwt-secret

# Frontend URL — embedded in confirmation and password reset emails
SITE_URL=http://localhost:3000
```

Find these values at: **Supabase Dashboard → Project Settings → API**

---

## Key Design Decisions

**Why `service_role` in the backend but `anon` for auth?**
The service role key bypasses RLS, which is necessary for cross-user reads (e.g. the leaderboard view). Auth operations (`sign_up`, `verify_otp`) are designed to run with the anon key — using service role there would bypass Supabase Auth's own security layer.

**Why are backtest metrics denormalized into flat columns?**
The full `metrics` blob is stored as JSONB for flexibility. However, Postgres cannot index inside JSONB efficiently. The 8 denormalized columns (`sharpe_ratio`, `total_return_pct`, etc.) get B-tree indexes, enabling the leaderboard to `ORDER BY sharpe_ratio DESC` without a full table scan or JSONB parsing. The `sync_backtest_on_complete` trigger keeps them in sync automatically.

**Why is `backtest_trades` a separate table?**
High-frequency strategies on 1-minute timeframes can generate thousands of trades per backtest. Bundling them with the main `backtests` row would make list queries slow (fetching the full JSONB on every row) and bloat the response payload. A separate table with its own pagination endpoint keeps both concerns clean.

**Why are `llm_request_log` and `activity_log` append-only?**
Both tables are audit logs. Making them append-only (no UPDATE, no DELETE in user-facing policies) preserves the integrity of the audit trail and aligns with standard data governance practice. For large deployments, partition `activity_log` by month to keep query performance stable.

**Why does `profiles` have no INSERT policy?**
The `handle_new_user` trigger runs as `SECURITY DEFINER` (elevated privileges) and inserts the profile row immediately after Supabase creates the `auth.users` entry. A user-facing INSERT policy would allow users to manually insert profile rows for arbitrary UUIDs — the trigger-only pattern prevents that.

**Why does `strategies` have a `is_public` SELECT policy in addition to the owner policy?**
The leaderboard shows strategies from all users, not just the current user. The `is_public = TRUE` policy lets any authenticated user read public strategy metadata, while the owner policy gives full access to the strategy owner including the code and private strategies.