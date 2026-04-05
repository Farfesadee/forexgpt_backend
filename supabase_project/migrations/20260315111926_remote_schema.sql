


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."create_conversation_if_missing"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    -- Check if the conversation already exists
    -- If not, insert it. ON CONFLICT handles the case where it was created 
    -- by another process at the exact same time.
    INSERT INTO public.mentor_conversations (id, user_id, title, created_at, updated_at)
    VALUES (
        NEW.conversation_id, 
        NEW.user_id, 
        'New Conversation', -- Default title, the sync trigger will update this later
        NOW(), 
        NOW()
    )
    ON CONFLICT (id) DO NOTHING;
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."create_conversation_if_missing"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."signals" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "company_name" "text",
    "transcript_excerpt" "text",
    "extraction_result" "jsonb" NOT NULL,
    "direction" "text",
    "magnitude" "text",
    "currency_pair" "text"[],
    "confidence" numeric(4,3),
    "reasoning" "text",
    "time_horizon" "text",
    "user_notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "signals_confidence_check" CHECK ((("confidence" >= (0)::numeric) AND ("confidence" <= (1)::numeric))),
    CONSTRAINT "signals_direction_check" CHECK (("direction" = ANY (ARRAY['short'::"text", 'long'::"text", 'neutral'::"text"]))),
    CONSTRAINT "signals_magnitude_check" CHECK (("magnitude" = ANY (ARRAY['high'::"text", 'moderate'::"text", 'low'::"text"]))),
    CONSTRAINT "signals_time_horizon_check" CHECK (("time_horizon" = ANY (ARRAY['current_quarter'::"text", 'long_term'::"text", 'next_quarter'::"text", 'full_term'::"text", 'short_term'::"text", 'full_year'::"text"])))
);


ALTER TABLE "public"."signals" OWNER TO "postgres";


COMMENT ON TABLE "public"."signals" IS 'Forex signals extracted by signal_service.py via hf_client.py (fine-tuned HF endpoint). hf_endpoint_id and hf_model_version trace exactly which model produced the signal.';



CREATE OR REPLACE FUNCTION "public"."get_signals_for_pair"("p_user_id" "uuid", "p_pair" "text", "p_source_type" "text" DEFAULT NULL::"text", "p_limit" integer DEFAULT 20, "p_offset" integer DEFAULT 0) RETURNS SETOF "public"."signals"
    LANGUAGE "sql" STABLE
    AS $$
    SELECT *
    FROM public.signals
    WHERE
        user_id       = p_user_id
        AND p_pair    = ANY(currency_pair)
    ORDER BY created_at DESC
    LIMIT p_limit
    OFFSET p_offset;
$$;


ALTER FUNCTION "public"."get_signals_for_pair"("p_user_id" "uuid", "p_pair" "text", "p_source_type" "text", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."handle_new_user"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name)
    VALUES (
      NEW.id,
      NEW.email,
      COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1))
    );
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."handle_new_user"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."increment_usage_counter"("p_module" "text", "p_user_id" "uuid") RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    -- Update the profiles table based on which module was used
    -- We use dynamic column names based on the p_module input
    UPDATE public.profiles
    SET 
        mentor_questions_asked = CASE WHEN p_module = 'mentor' THEN mentor_questions_asked + 1 ELSE mentor_questions_asked END,
        signals_extracted = CASE WHEN p_module = 'signals' THEN signals_extracted + 1 ELSE signals_extracted END,
        strategies_generated = CASE WHEN p_module = 'codegen' THEN strategies_generated + 1 ELSE strategies_generated END,
        backtests_run = CASE WHEN p_module = 'backtest' THEN backtests_run + 1 ELSE backtests_run END
    WHERE id = p_user_id;
END;
$$;


ALTER FUNCTION "public"."increment_usage_counter"("p_module" "text", "p_user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."log_activity"("p_user_id" "uuid", "p_action" "text", "p_entity_type" "text" DEFAULT NULL::"text", "p_entity_id" "uuid" DEFAULT NULL::"uuid", "p_metadata" "jsonb" DEFAULT '{}'::"jsonb") RETURNS "uuid"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE v_id UUID;
BEGIN
    INSERT INTO public.activity_log (user_id, action, entity_type, entity_id, metadata)
    VALUES (p_user_id, p_action, p_entity_type, p_entity_id, p_metadata)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;


ALTER FUNCTION "public"."log_activity"("p_user_id" "uuid", "p_action" "text", "p_entity_type" "text", "p_entity_id" "uuid", "p_metadata" "jsonb") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."log_activity"("p_user_id" "uuid", "p_action" "text", "p_entity_type" "text", "p_entity_id" "uuid", "p_metadata" "jsonb") IS 'Appends a user action to activity_log. Called by all api/routes/*.py handlers with service_role key.';



CREATE OR REPLACE FUNCTION "public"."log_llm_request"("p_user_id" "uuid", "p_source_module" "text", "p_system_prompt_key" "text", "p_model_used" "text", "p_adapter_used" "text", "p_hf_endpoint_id" "text", "p_input_tokens" integer, "p_output_tokens" integer, "p_latency_ms" integer, "p_success" boolean, "p_error_type" "text", "p_error_message" "text", "p_fallback_used" boolean, "p_entity_type" "text", "p_entity_id" "uuid") RETURNS "uuid"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE v_id UUID;
BEGIN
    INSERT INTO public.llm_request_log (
        user_id, source_module, system_prompt_key, model_used, adapter_used,
        hf_endpoint_id, input_tokens, output_tokens, latency_ms,
        success, error_type, error_message, fallback_used,
        entity_type, entity_id
    ) VALUES (
        p_user_id, p_source_module, p_system_prompt_key, p_model_used, p_adapter_used,
        p_hf_endpoint_id, p_input_tokens, p_output_tokens, p_latency_ms,
        p_success, p_error_type, p_error_message, p_fallback_used,
        p_entity_type, p_entity_id
    ) RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;


ALTER FUNCTION "public"."log_llm_request"("p_user_id" "uuid", "p_source_module" "text", "p_system_prompt_key" "text", "p_model_used" "text", "p_adapter_used" "text", "p_hf_endpoint_id" "text", "p_input_tokens" integer, "p_output_tokens" integer, "p_latency_ms" integer, "p_success" boolean, "p_error_type" "text", "p_error_message" "text", "p_fallback_used" boolean, "p_entity_type" "text", "p_entity_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."log_llm_request"("p_user_id" "uuid", "p_source_module" "text", "p_system_prompt_key" "text", "p_model_used" "text", "p_adapter_used" "text", "p_hf_endpoint_id" "text", "p_input_tokens" integer, "p_output_tokens" integer, "p_latency_ms" integer, "p_success" boolean, "p_error_type" "text", "p_error_message" "text", "p_fallback_used" boolean, "p_entity_type" "text", "p_entity_id" "uuid") IS 'Inserts one row into llm_request_log. Called by core/llm_router.py after every model invocation.';



CREATE OR REPLACE FUNCTION "public"."set_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."set_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."sync_backtest_on_complete"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        NEW.completed_at      = NOW();
        NEW.total_return_pct  = (NEW.metrics->>'total_return_pct')::NUMERIC;
        NEW.sharpe_ratio      = (NEW.metrics->>'sharpe_ratio')::NUMERIC;
        NEW.sortino_ratio     = (NEW.metrics->>'sortino_ratio')::NUMERIC;
        NEW.calmar_ratio      = (NEW.metrics->>'calmar_ratio')::NUMERIC;
        NEW.max_drawdown_pct  = (NEW.metrics->>'max_drawdown_pct')::NUMERIC;
        NEW.win_rate_pct      = (NEW.metrics->>'win_rate_pct')::NUMERIC;
        NEW.profit_factor     = (NEW.metrics->>'profit_factor')::NUMERIC;
        NEW.total_trades      = (NEW.metrics->>'total_trades')::INTEGER;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."sync_backtest_on_complete"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."sync_mentor_conversation"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    UPDATE public.mentor_conversations
    SET
        message_count   = message_count + 1,
        last_message_at = NOW(),
        title = CASE
            WHEN title IS NULL AND NEW.role = 'user'
            THEN LEFT(NEW.content, 80)
            ELSE title
        END
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."sync_mentor_conversation"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."activity_log" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "action" "text" NOT NULL,
    "entity_type" "text",
    "entity_id" "uuid",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."activity_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."activity_log" IS 'Append-only product analytics log. Written by all api/routes/*.py handlers. Never updated or deleted — partition by month for large deployments.';



CREATE TABLE IF NOT EXISTS "public"."backtest_trades" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "backtest_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "trade_number" integer NOT NULL,
    "direction" "text",
    "entry_time" timestamp with time zone,
    "exit_time" timestamp with time zone,
    "entry_price" numeric(12,5) NOT NULL,
    "exit_price" numeric(12,5) NOT NULL,
    "lot_size" numeric(8,2),
    "pnl_pips" numeric(10,2),
    "pnl_usd" numeric(12,2),
    "duration_hours" numeric(8,2),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "entry_date" timestamp without time zone,
    "exit_date" timestamp without time zone,
    "quantity" numeric(20,8),
    "side" "text",
    "gross_pnl" numeric(15,4),
    "net_pnl" numeric(15,4),
    "return_pct" numeric(10,4),
    "holding_days" integer,
    "total_cost" numeric(15,4),
    "spread_cost" numeric(15,6),
    "slippage_cost" numeric(15,6),
    "commission" numeric(15,6),
    "financing_cost" numeric(15,6),
    "exchange_fees" numeric(15,6),
    CONSTRAINT "backtest_trades_direction_check" CHECK (("direction" = ANY (ARRAY['long'::"text", 'short'::"text", 'neutral'::"text"]))),
    CONSTRAINT "backtest_trades_side_check" CHECK (("side" = ANY (ARRAY['long'::"text", 'short'::"text"])))
);


ALTER TABLE "public"."backtest_trades" OWNER TO "postgres";


COMMENT ON TABLE "public"."backtest_trades" IS 'Individual trade records for each backtest. Paginated separately from backtests table since high-frequency strategies can produce 1000+ trades.';



CREATE TABLE IF NOT EXISTS "public"."backtests" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "symbol" "text",
    "start_date" "date",
    "end_date" "date",
    "equity_curve" "jsonb",
    "trades" "jsonb",
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "error_message" "text",
    "educational_analysis" "text",
    "improvement_suggestions" "text"[],
    "is_saved" boolean DEFAULT false,
    "user_notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "completed_at" timestamp with time zone,
    "pair" "text",
    "strategy_id" "uuid",
    "position_size_pct" integer,
    "data_source" "text",
    "timeframe" "text" DEFAULT '1d'::"text",
    "metrics" "jsonb",
    "total_return_pct" numeric(10,4),
    "sharpe_ratio" numeric(10,4),
    "max_drawdown_pct" numeric(10,4),
    "win_rate_pct" numeric(10,4),
    "total_trades" integer,
    "initial_capital" numeric(15,2) DEFAULT 10000.00,
    "strategy_config" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "strategy_name" "text",
    "performance_metrics" "jsonb",
    "sortino_ratio" numeric(10,4),
    "calmar_ratio" numeric(10,4),
    "profit_factor" numeric(10,4),
    "custom_code" "text",
    CONSTRAINT "backtests_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'running'::"text", 'completed'::"text", 'failed'::"text"]))),
    CONSTRAINT "check_strategy_config_structure" CHECK ((("jsonb_typeof"("strategy_config") = 'object'::"text") AND ("strategy_config" ? 'strategy_params'::"text") AND ("strategy_config" ? 'cost_preset'::"text") AND ("strategy_config" ? 'position_size_pct'::"text") AND ("strategy_config" ? 'data_source'::"text") AND ("jsonb_typeof"(("strategy_config" -> 'strategy_params'::"text")) = 'object'::"text") AND ("jsonb_typeof"(("strategy_config" -> 'cost_preset'::"text")) = 'string'::"text") AND ("jsonb_typeof"(("strategy_config" -> 'position_size_pct'::"text")) = 'number'::"text") AND ("jsonb_typeof"(("strategy_config" -> 'data_source'::"text")) = 'string'::"text")))
);


ALTER TABLE "public"."backtests" OWNER TO "postgres";


COMMENT ON TABLE "public"."backtests" IS 'Backtest runs executed by backtest_service.py. metrics and equity_curve are raw JSONB; key metrics are denormalized by trigger for fast leaderboard ordering.';



CREATE TABLE IF NOT EXISTS "public"."codegen_conversations" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "conversation_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "role" "text" NOT NULL,
    "content" "text" NOT NULL,
    "tokens_used" integer,
    "model_version" "text" DEFAULT 'mistral-7b-finetuned'::"text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "codegen_conversations_role_check" CHECK (("role" = ANY (ARRAY['user'::"text", 'assistant'::"text", 'system'::"text"])))
);


ALTER TABLE "public"."codegen_conversations" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."codegen_history" WITH ("security_invoker"='on') AS
 SELECT "id",
    "user_id",
    "conversation_id",
    "role",
    "left"("content", 140) AS "last_message_preview",
    "tokens_used",
    "model_version",
    "created_at"
   FROM "public"."codegen_conversations" "qs"
  WHERE ("role" = 'assistant'::"text")
  ORDER BY "created_at" DESC;


ALTER VIEW "public"."codegen_history" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."generated_codes" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "conversation_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "strategy_name" "text",
    "description" "text" NOT NULL,
    "code" "text" NOT NULL,
    "language" "text" DEFAULT 'python'::"text",
    "is_runnable" boolean DEFAULT false,
    "last_validated" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."generated_codes" OWNER TO "postgres";


COMMENT ON TABLE "public"."generated_codes" IS 'Stores final Python backtesting scripts generated from user descriptions. Used as input for backtest_service.py.';



CREATE TABLE IF NOT EXISTS "public"."llm_request_log" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid",
    "source_module" "text" NOT NULL,
    "system_prompt_key" "text",
    "model_used" "text",
    "adapter_used" "text",
    "hf_endpoint_id" "text",
    "input_tokens" integer,
    "output_tokens" integer,
    "total_tokens" integer GENERATED ALWAYS AS ((COALESCE("input_tokens", 0) + COALESCE("output_tokens", 0))) STORED,
    "latency_ms" integer,
    "success" boolean DEFAULT true NOT NULL,
    "error_type" "text",
    "error_message" "text",
    "fallback_used" boolean DEFAULT false,
    "entity_type" "text",
    "entity_id" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "llm_request_log_source_module_check" CHECK (("source_module" = ANY (ARRAY['mentor_service'::"text", 'quant_finance_service'::"text", 'signal_service'::"text", 'codegen_service'::"text", 'backtest_service'::"text"])))
);


ALTER TABLE "public"."llm_request_log" OWNER TO "postgres";


COMMENT ON TABLE "public"."llm_request_log" IS 'Audit log of every call routed through core/llm_router.py. Used for cost tracking, latency analysis, and adapter A/B comparison. Append-only — no UPDATE or DELETE.';



CREATE OR REPLACE VIEW "public"."llm_router_stats" WITH ("security_invoker"='on') AS
 SELECT "source_module",
    "model_used",
    "adapter_used",
    "system_prompt_key",
    "date_trunc"('day'::"text", "created_at") AS "day",
    "count"(*) AS "total_requests",
    "count"(*) FILTER (WHERE "success") AS "successful",
    "count"(*) FILTER (WHERE (NOT "success")) AS "failed",
    "count"(*) FILTER (WHERE "fallback_used") AS "fallbacks",
    "round"("avg"("latency_ms")) AS "avg_latency_ms",
    "round"("percentile_cont"((0.95)::double precision) WITHIN GROUP (ORDER BY (("latency_ms")::double precision))) AS "p95_latency_ms",
    "sum"("total_tokens") AS "total_tokens",
    "round"("avg"("total_tokens")) AS "avg_tokens_per_request"
   FROM "public"."llm_request_log"
  GROUP BY "source_module", "model_used", "adapter_used", "system_prompt_key", ("date_trunc"('day'::"text", "created_at"))
  ORDER BY ("date_trunc"('day'::"text", "created_at")) DESC, ("count"(*)) DESC;


ALTER VIEW "public"."llm_router_stats" OWNER TO "postgres";


COMMENT ON VIEW "public"."llm_router_stats" IS 'Daily rollup of llm_router.py performance by module, model, adapter, and prompt. Used for cost tracking, latency monitoring, and adapter A/B comparison.';



CREATE TABLE IF NOT EXISTS "public"."mentor_conversations" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "title" "text",
    "topic_tags" "text"[] DEFAULT ARRAY[]::"text"[],
    "message_count" integer DEFAULT 0,
    "is_archived" boolean DEFAULT false,
    "last_message_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."mentor_conversations" OWNER TO "postgres";


COMMENT ON TABLE "public"."mentor_conversations" IS 'Forex theory mentor chat sessions (mentor_service.py). Distinct from quant_sessions which handle mathematical/statistical questions.';



CREATE TABLE IF NOT EXISTS "public"."mentor_messages" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "conversation_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "role" "text" NOT NULL,
    "content" "text" NOT NULL,
    "topic_tags" "text"[] DEFAULT ARRAY[]::"text"[],
    "related_concepts" "text"[] DEFAULT ARRAY[]::"text"[],
    "tokens_used" integer,
    "thumbs_up" boolean,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "model_used" "text",
    "adapter_used" "text",
    "latency_ms" integer,
    "system_prompt_key" "text",
    CONSTRAINT "mentor_messages_role_check" CHECK (("role" = ANY (ARRAY['user'::"text", 'assistant'::"text", 'system'::"text"])))
);


ALTER TABLE "public"."mentor_messages" OWNER TO "postgres";


COMMENT ON TABLE "public"."mentor_messages" IS 'Messages for the Forex theory mentor (mentor_service.py). system_prompt_key and adapter_used trace which llm_router.py path was taken.';



CREATE OR REPLACE VIEW "public"."mentor_history" WITH ("security_invoker"='on') AS
 SELECT "id",
    "user_id",
    "title",
    "message_count",
    "is_archived",
    "last_message_at",
    "created_at",
    ( SELECT "left"("mm"."content", 140) AS "left"
           FROM "public"."mentor_messages" "mm"
          WHERE (("mm"."conversation_id" = "mc"."id") AND ("mm"."role" = 'assistant'::"text"))
          ORDER BY "mm"."created_at" DESC
         LIMIT 1) AS "last_response_preview",
    ( SELECT COALESCE("mm"."model_used", 'unknown'::"text") AS "coalesce"
           FROM "public"."mentor_messages" "mm"
          WHERE (("mm"."conversation_id" = "mc"."id") AND ("mm"."role" = 'assistant'::"text"))
          ORDER BY "mm"."created_at" DESC
         LIMIT 1) AS "last_model_used"
   FROM "public"."mentor_conversations" "mc"
  ORDER BY "last_message_at" DESC NULLS LAST;


ALTER VIEW "public"."mentor_history" OWNER TO "postgres";


COMMENT ON VIEW "public"."mentor_history" IS 'Mentor conversation list with preview snippet and last model used. Used by api/routes/mentor.py for the conversation sidebar.';



CREATE TABLE IF NOT EXISTS "public"."profiles" (
    "id" "uuid" NOT NULL,
    "email" "text" NOT NULL,
    "display_name" "text",
    "avatar_url" "text",
    "timezone" "text" DEFAULT 'UTC'::"text",
    "backtests_run" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "mentor_questions_asked" integer DEFAULT 0,
    "signals_extracted" integer DEFAULT 0,
    "strategies_generated" integer DEFAULT 0
);


ALTER TABLE "public"."profiles" OWNER TO "postgres";


COMMENT ON TABLE "public"."profiles" IS 'App user profile linked to Supabase Auth. One row per user. experience_level is forwarded to system_prompts.py to tailor LLM responses.';



CREATE OR REPLACE VIEW "public"."user_dashboard" WITH ("security_invoker"='on') AS
 SELECT "p"."id",
    "p"."display_name",
    "p"."email",
    "count"(DISTINCT "mc"."id") FILTER (WHERE (NOT "mc"."is_archived")) AS "active_mentor_conversations",
    "count"(DISTINCT "s"."id") AS "total_signals",
    "count"(DISTINCT "st"."id") AS "total_strategies",
    "count"(DISTINCT "st"."id") FILTER (WHERE "st"."is_runnable") AS "validated_strategies",
    "count"(DISTINCT "bt"."id") FILTER (WHERE ("bt"."status" = 'completed'::"text")) AS "completed_backtests",
    "max"("mc"."last_message_at") AS "last_mentor_activity",
    "max"("s"."created_at") AS "last_signal_extracted",
    "p"."created_at" AS "member_since"
   FROM (((("public"."profiles" "p"
     LEFT JOIN "public"."mentor_conversations" "mc" ON (("mc"."user_id" = "p"."id")))
     LEFT JOIN "public"."signals" "s" ON (("s"."user_id" = "p"."id")))
     LEFT JOIN "public"."generated_codes" "st" ON (("st"."user_id" = "p"."id")))
     LEFT JOIN "public"."backtests" "bt" ON (("bt"."user_id" = "p"."id")))
  GROUP BY "p"."id", "p"."display_name", "p"."email", "p"."created_at";


ALTER VIEW "public"."user_dashboard" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."users" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "email" "text" NOT NULL,
    "full_name" "text",
    "created_at" timestamp without time zone DEFAULT "now"(),
    "updated_at" timestamp without time zone DEFAULT "now"()
);


ALTER TABLE "public"."users" OWNER TO "postgres";


ALTER TABLE ONLY "public"."activity_log"
    ADD CONSTRAINT "activity_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."backtest_trades"
    ADD CONSTRAINT "backtest_trades_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."backtests"
    ADD CONSTRAINT "backtests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."codegen_conversations"
    ADD CONSTRAINT "codegen_conversations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."generated_codes"
    ADD CONSTRAINT "generated_codes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."llm_request_log"
    ADD CONSTRAINT "llm_request_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mentor_conversations"
    ADD CONSTRAINT "mentor_conversations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mentor_messages"
    ADD CONSTRAINT "mentor_messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."signals"
    ADD CONSTRAINT "signals_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_activity_action" ON "public"."activity_log" USING "btree" ("action");



CREATE INDEX "idx_activity_created_at" ON "public"."activity_log" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_activity_entity" ON "public"."activity_log" USING "btree" ("entity_type", "entity_id");



CREATE INDEX "idx_activity_user_id" ON "public"."activity_log" USING "btree" ("user_id");



CREATE INDEX "idx_backtests_created_at" ON "public"."backtests" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_backtests_pair" ON "public"."backtests" USING "btree" ("pair");



CREATE INDEX "idx_backtests_status" ON "public"."backtests" USING "btree" ("status");



CREATE INDEX "idx_backtests_user_id" ON "public"."backtests" USING "btree" ("user_id");



CREATE INDEX "idx_backtests_user_status" ON "public"."backtests" USING "btree" ("user_id", "status");



CREATE INDEX "idx_bt_trades_backtest_id" ON "public"."backtest_trades" USING "btree" ("backtest_id");



CREATE INDEX "idx_bt_trades_entry_time" ON "public"."backtest_trades" USING "btree" ("entry_time");



CREATE INDEX "idx_bt_trades_user_id" ON "public"."backtest_trades" USING "btree" ("user_id");



CREATE INDEX "idx_codegen_conv_created" ON "public"."codegen_conversations" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_codegen_conv_group" ON "public"."codegen_conversations" USING "btree" ("conversation_id");



CREATE INDEX "idx_codegen_conv_user" ON "public"."codegen_conversations" USING "btree" ("user_id");



CREATE INDEX "idx_gen_codes_created_at" ON "public"."generated_codes" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_gen_codes_user_id" ON "public"."generated_codes" USING "btree" ("user_id");



CREATE INDEX "idx_llm_log_created_at" ON "public"."llm_request_log" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_llm_log_model_used" ON "public"."llm_request_log" USING "btree" ("model_used");



CREATE INDEX "idx_llm_log_source_module" ON "public"."llm_request_log" USING "btree" ("source_module");



CREATE INDEX "idx_llm_log_success" ON "public"."llm_request_log" USING "btree" ("success");



CREATE INDEX "idx_llm_log_user_id" ON "public"."llm_request_log" USING "btree" ("user_id");



CREATE INDEX "idx_mentor_conv_last_message" ON "public"."mentor_conversations" USING "btree" ("last_message_at" DESC NULLS LAST);



CREATE INDEX "idx_mentor_conv_user_id" ON "public"."mentor_conversations" USING "btree" ("user_id");



CREATE INDEX "idx_mentor_msg_conversation" ON "public"."mentor_messages" USING "btree" ("conversation_id");



CREATE INDEX "idx_mentor_msg_created_at" ON "public"."mentor_messages" USING "btree" ("created_at");



CREATE INDEX "idx_mentor_msg_user_id" ON "public"."mentor_messages" USING "btree" ("user_id");



CREATE INDEX "idx_signals_confidence" ON "public"."signals" USING "btree" ("confidence" DESC);



CREATE INDEX "idx_signals_created_at" ON "public"."signals" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_signals_direction" ON "public"."signals" USING "btree" ("direction");



CREATE INDEX "idx_signals_user_id" ON "public"."signals" USING "btree" ("user_id");



CREATE INDEX "idx_users_email" ON "public"."users" USING "btree" ("email");



CREATE OR REPLACE TRIGGER "auto_create_conversation" BEFORE INSERT ON "public"."mentor_messages" FOR EACH ROW EXECUTE FUNCTION "public"."create_conversation_if_missing"();



CREATE OR REPLACE TRIGGER "backtest_on_complete" BEFORE UPDATE ON "public"."backtests" FOR EACH ROW EXECUTE FUNCTION "public"."sync_backtest_on_complete"();



CREATE OR REPLACE TRIGGER "backtests_updated_at" BEFORE UPDATE ON "public"."backtests" FOR EACH ROW EXECUTE FUNCTION "public"."set_updated_at"();



CREATE OR REPLACE TRIGGER "mentor_conversations_updated_at" BEFORE UPDATE ON "public"."mentor_conversations" FOR EACH ROW EXECUTE FUNCTION "public"."set_updated_at"();



CREATE OR REPLACE TRIGGER "mentor_messages_sync" AFTER INSERT ON "public"."mentor_messages" FOR EACH ROW EXECUTE FUNCTION "public"."sync_mentor_conversation"();



CREATE OR REPLACE TRIGGER "profiles_updated_at" BEFORE UPDATE ON "public"."profiles" FOR EACH ROW EXECUTE FUNCTION "public"."set_updated_at"();



CREATE OR REPLACE TRIGGER "signals_updated_at" BEFORE UPDATE ON "public"."signals" FOR EACH ROW EXECUTE FUNCTION "public"."set_updated_at"();



CREATE OR REPLACE TRIGGER "update_users_updated_at" BEFORE UPDATE ON "public"."users" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



ALTER TABLE ONLY "public"."activity_log"
    ADD CONSTRAINT "activity_log_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."backtest_trades"
    ADD CONSTRAINT "backtest_trades_backtest_id_fkey" FOREIGN KEY ("backtest_id") REFERENCES "public"."backtests"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."backtest_trades"
    ADD CONSTRAINT "backtest_trades_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."backtests"
    ADD CONSTRAINT "backtests_strategy_id_fkey" FOREIGN KEY ("strategy_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."backtests"
    ADD CONSTRAINT "backtests_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."codegen_conversations"
    ADD CONSTRAINT "codegen_conversations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."generated_codes"
    ADD CONSTRAINT "generated_codes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."llm_request_log"
    ADD CONSTRAINT "llm_request_log_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."mentor_conversations"
    ADD CONSTRAINT "mentor_conversations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."mentor_messages"
    ADD CONSTRAINT "mentor_messages_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."mentor_conversations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."mentor_messages"
    ADD CONSTRAINT "mentor_messages_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."signals"
    ADD CONSTRAINT "signals_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



CREATE POLICY "Users can update own profile" ON "public"."users" FOR UPDATE USING (("auth"."uid"() = "id"));



CREATE POLICY "Users can view own profile" ON "public"."users" FOR SELECT USING (("auth"."uid"() = "id"));



ALTER TABLE "public"."activity_log" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "activity_log: owner select" ON "public"."activity_log" FOR SELECT USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."backtest_trades" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."backtests" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "backtests: owner delete" ON "public"."backtests" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "backtests: owner insert" ON "public"."backtests" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "backtests: owner select" ON "public"."backtests" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "backtests: owner update" ON "public"."backtests" FOR UPDATE USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "bt_trades: owner select" ON "public"."backtest_trades" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "codegen_conv: owner delete" ON "public"."codegen_conversations" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "codegen_conv: owner insert" ON "public"."codegen_conversations" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "codegen_conv: owner select" ON "public"."codegen_conversations" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "codegen_conv: owner update" ON "public"."codegen_conversations" FOR UPDATE USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."codegen_conversations" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "gen_msg: owner insert" ON "public"."generated_codes" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "gen_msg: owner select" ON "public"."generated_codes" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "gen_msg: owner update feedback" ON "public"."generated_codes" FOR UPDATE USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."generated_codes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."llm_request_log" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "mentor_conv: owner delete" ON "public"."mentor_conversations" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "mentor_conv: owner insert" ON "public"."mentor_conversations" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "mentor_conv: owner select" ON "public"."mentor_conversations" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "mentor_conv: owner update" ON "public"."mentor_conversations" FOR UPDATE USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."mentor_conversations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."mentor_messages" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "mentor_msg: owner insert" ON "public"."mentor_messages" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "mentor_msg: owner select" ON "public"."mentor_messages" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "mentor_msg: owner update feedback" ON "public"."mentor_messages" FOR UPDATE USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."profiles" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "profiles: owner select" ON "public"."profiles" FOR SELECT USING (("auth"."uid"() = "id"));



CREATE POLICY "profiles: owner update" ON "public"."profiles" FOR UPDATE USING (("auth"."uid"() = "id")) WITH CHECK (("auth"."uid"() = "id"));



ALTER TABLE "public"."signals" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "signals: owner delete" ON "public"."signals" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "signals: owner insert" ON "public"."signals" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "signals: owner select" ON "public"."signals" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "signals: owner update" ON "public"."signals" FOR UPDATE USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."users" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";

























































































































































GRANT ALL ON FUNCTION "public"."create_conversation_if_missing"() TO "anon";
GRANT ALL ON FUNCTION "public"."create_conversation_if_missing"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."create_conversation_if_missing"() TO "service_role";



GRANT ALL ON TABLE "public"."signals" TO "anon";
GRANT ALL ON TABLE "public"."signals" TO "authenticated";
GRANT ALL ON TABLE "public"."signals" TO "service_role";



GRANT ALL ON FUNCTION "public"."get_signals_for_pair"("p_user_id" "uuid", "p_pair" "text", "p_source_type" "text", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_signals_for_pair"("p_user_id" "uuid", "p_pair" "text", "p_source_type" "text", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_signals_for_pair"("p_user_id" "uuid", "p_pair" "text", "p_source_type" "text", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."handle_new_user"() TO "anon";
GRANT ALL ON FUNCTION "public"."handle_new_user"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."handle_new_user"() TO "service_role";



GRANT ALL ON FUNCTION "public"."increment_usage_counter"("p_module" "text", "p_user_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."increment_usage_counter"("p_module" "text", "p_user_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."increment_usage_counter"("p_module" "text", "p_user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."log_activity"("p_user_id" "uuid", "p_action" "text", "p_entity_type" "text", "p_entity_id" "uuid", "p_metadata" "jsonb") TO "anon";
GRANT ALL ON FUNCTION "public"."log_activity"("p_user_id" "uuid", "p_action" "text", "p_entity_type" "text", "p_entity_id" "uuid", "p_metadata" "jsonb") TO "authenticated";
GRANT ALL ON FUNCTION "public"."log_activity"("p_user_id" "uuid", "p_action" "text", "p_entity_type" "text", "p_entity_id" "uuid", "p_metadata" "jsonb") TO "service_role";



GRANT ALL ON FUNCTION "public"."log_llm_request"("p_user_id" "uuid", "p_source_module" "text", "p_system_prompt_key" "text", "p_model_used" "text", "p_adapter_used" "text", "p_hf_endpoint_id" "text", "p_input_tokens" integer, "p_output_tokens" integer, "p_latency_ms" integer, "p_success" boolean, "p_error_type" "text", "p_error_message" "text", "p_fallback_used" boolean, "p_entity_type" "text", "p_entity_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."log_llm_request"("p_user_id" "uuid", "p_source_module" "text", "p_system_prompt_key" "text", "p_model_used" "text", "p_adapter_used" "text", "p_hf_endpoint_id" "text", "p_input_tokens" integer, "p_output_tokens" integer, "p_latency_ms" integer, "p_success" boolean, "p_error_type" "text", "p_error_message" "text", "p_fallback_used" boolean, "p_entity_type" "text", "p_entity_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."log_llm_request"("p_user_id" "uuid", "p_source_module" "text", "p_system_prompt_key" "text", "p_model_used" "text", "p_adapter_used" "text", "p_hf_endpoint_id" "text", "p_input_tokens" integer, "p_output_tokens" integer, "p_latency_ms" integer, "p_success" boolean, "p_error_type" "text", "p_error_message" "text", "p_fallback_used" boolean, "p_entity_type" "text", "p_entity_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."set_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."set_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."set_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."sync_backtest_on_complete"() TO "anon";
GRANT ALL ON FUNCTION "public"."sync_backtest_on_complete"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."sync_backtest_on_complete"() TO "service_role";



GRANT ALL ON FUNCTION "public"."sync_mentor_conversation"() TO "anon";
GRANT ALL ON FUNCTION "public"."sync_mentor_conversation"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."sync_mentor_conversation"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";


















GRANT ALL ON TABLE "public"."activity_log" TO "anon";
GRANT ALL ON TABLE "public"."activity_log" TO "authenticated";
GRANT ALL ON TABLE "public"."activity_log" TO "service_role";



GRANT ALL ON TABLE "public"."backtest_trades" TO "anon";
GRANT ALL ON TABLE "public"."backtest_trades" TO "authenticated";
GRANT ALL ON TABLE "public"."backtest_trades" TO "service_role";



GRANT ALL ON TABLE "public"."backtests" TO "anon";
GRANT ALL ON TABLE "public"."backtests" TO "authenticated";
GRANT ALL ON TABLE "public"."backtests" TO "service_role";



GRANT ALL ON TABLE "public"."codegen_conversations" TO "anon";
GRANT ALL ON TABLE "public"."codegen_conversations" TO "authenticated";
GRANT ALL ON TABLE "public"."codegen_conversations" TO "service_role";



GRANT ALL ON TABLE "public"."codegen_history" TO "anon";
GRANT ALL ON TABLE "public"."codegen_history" TO "authenticated";
GRANT ALL ON TABLE "public"."codegen_history" TO "service_role";



GRANT ALL ON TABLE "public"."generated_codes" TO "anon";
GRANT ALL ON TABLE "public"."generated_codes" TO "authenticated";
GRANT ALL ON TABLE "public"."generated_codes" TO "service_role";



GRANT ALL ON TABLE "public"."llm_request_log" TO "anon";
GRANT ALL ON TABLE "public"."llm_request_log" TO "authenticated";
GRANT ALL ON TABLE "public"."llm_request_log" TO "service_role";



GRANT ALL ON TABLE "public"."llm_router_stats" TO "anon";
GRANT ALL ON TABLE "public"."llm_router_stats" TO "authenticated";
GRANT ALL ON TABLE "public"."llm_router_stats" TO "service_role";



GRANT ALL ON TABLE "public"."mentor_conversations" TO "anon";
GRANT ALL ON TABLE "public"."mentor_conversations" TO "authenticated";
GRANT ALL ON TABLE "public"."mentor_conversations" TO "service_role";



GRANT ALL ON TABLE "public"."mentor_messages" TO "anon";
GRANT ALL ON TABLE "public"."mentor_messages" TO "authenticated";
GRANT ALL ON TABLE "public"."mentor_messages" TO "service_role";



GRANT ALL ON TABLE "public"."mentor_history" TO "anon";
GRANT ALL ON TABLE "public"."mentor_history" TO "authenticated";
GRANT ALL ON TABLE "public"."mentor_history" TO "service_role";



GRANT ALL ON TABLE "public"."profiles" TO "anon";
GRANT ALL ON TABLE "public"."profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."profiles" TO "service_role";



GRANT ALL ON TABLE "public"."user_dashboard" TO "anon";
GRANT ALL ON TABLE "public"."user_dashboard" TO "authenticated";
GRANT ALL ON TABLE "public"."user_dashboard" TO "service_role";



GRANT ALL ON TABLE "public"."users" TO "anon";
GRANT ALL ON TABLE "public"."users" TO "authenticated";
GRANT ALL ON TABLE "public"."users" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































drop extension if exists "pg_net";

drop trigger if exists "backtest_on_complete" on "public"."backtests";

drop trigger if exists "backtests_updated_at" on "public"."backtests";

drop trigger if exists "mentor_conversations_updated_at" on "public"."mentor_conversations";

drop trigger if exists "auto_create_conversation" on "public"."mentor_messages";

drop trigger if exists "mentor_messages_sync" on "public"."mentor_messages";

drop trigger if exists "profiles_updated_at" on "public"."profiles";

drop trigger if exists "signals_updated_at" on "public"."signals";

drop trigger if exists "update_users_updated_at" on "public"."users";

alter table "public"."activity_log" drop constraint "activity_log_user_id_fkey";

alter table "public"."backtest_trades" drop constraint "backtest_trades_backtest_id_fkey";

alter table "public"."backtest_trades" drop constraint "backtest_trades_user_id_fkey";

alter table "public"."backtests" drop constraint "backtests_strategy_id_fkey";

alter table "public"."backtests" drop constraint "backtests_user_id_fkey";

alter table "public"."codegen_conversations" drop constraint "codegen_conversations_user_id_fkey";

alter table "public"."generated_codes" drop constraint "generated_codes_user_id_fkey";

alter table "public"."llm_request_log" drop constraint "llm_request_log_user_id_fkey";

alter table "public"."mentor_conversations" drop constraint "mentor_conversations_user_id_fkey";

alter table "public"."mentor_messages" drop constraint "mentor_messages_conversation_id_fkey";

alter table "public"."mentor_messages" drop constraint "mentor_messages_user_id_fkey";

alter table "public"."signals" drop constraint "signals_user_id_fkey";

alter table "public"."activity_log" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."backtest_trades" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."backtests" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."codegen_conversations" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."generated_codes" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."llm_request_log" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."mentor_conversations" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."mentor_messages" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."signals" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."users" alter column "id" set default extensions.uuid_generate_v4();

alter table "public"."activity_log" add constraint "activity_log_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."activity_log" validate constraint "activity_log_user_id_fkey";

alter table "public"."backtest_trades" add constraint "backtest_trades_backtest_id_fkey" FOREIGN KEY (backtest_id) REFERENCES public.backtests(id) ON DELETE CASCADE not valid;

alter table "public"."backtest_trades" validate constraint "backtest_trades_backtest_id_fkey";

alter table "public"."backtest_trades" add constraint "backtest_trades_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."backtest_trades" validate constraint "backtest_trades_user_id_fkey";

alter table "public"."backtests" add constraint "backtests_strategy_id_fkey" FOREIGN KEY (strategy_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."backtests" validate constraint "backtests_strategy_id_fkey";

alter table "public"."backtests" add constraint "backtests_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."backtests" validate constraint "backtests_user_id_fkey";

alter table "public"."codegen_conversations" add constraint "codegen_conversations_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."codegen_conversations" validate constraint "codegen_conversations_user_id_fkey";

alter table "public"."generated_codes" add constraint "generated_codes_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."generated_codes" validate constraint "generated_codes_user_id_fkey";

alter table "public"."llm_request_log" add constraint "llm_request_log_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE SET NULL not valid;

alter table "public"."llm_request_log" validate constraint "llm_request_log_user_id_fkey";

alter table "public"."mentor_conversations" add constraint "mentor_conversations_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."mentor_conversations" validate constraint "mentor_conversations_user_id_fkey";

alter table "public"."mentor_messages" add constraint "mentor_messages_conversation_id_fkey" FOREIGN KEY (conversation_id) REFERENCES public.mentor_conversations(id) ON DELETE CASCADE not valid;

alter table "public"."mentor_messages" validate constraint "mentor_messages_conversation_id_fkey";

alter table "public"."mentor_messages" add constraint "mentor_messages_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."mentor_messages" validate constraint "mentor_messages_user_id_fkey";

alter table "public"."signals" add constraint "signals_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."signals" validate constraint "signals_user_id_fkey";

set check_function_bodies = off;

create or replace view "public"."codegen_history" as  SELECT id,
    user_id,
    conversation_id,
    role,
    "left"(content, 140) AS last_message_preview,
    tokens_used,
    model_version,
    created_at
   FROM public.codegen_conversations qs
  WHERE (role = 'assistant'::text)
  ORDER BY created_at DESC;


CREATE OR REPLACE FUNCTION public.get_signals_for_pair(p_user_id uuid, p_pair text, p_source_type text DEFAULT NULL::text, p_limit integer DEFAULT 20, p_offset integer DEFAULT 0)
 RETURNS SETOF public.signals
 LANGUAGE sql
 STABLE
AS $function$
    SELECT *
    FROM public.signals
    WHERE
        user_id       = p_user_id
        AND p_pair    = ANY(currency_pair)
    ORDER BY created_at DESC
    LIMIT p_limit
    OFFSET p_offset;
$function$
;

create or replace view "public"."llm_router_stats" as  SELECT source_module,
    model_used,
    adapter_used,
    system_prompt_key,
    date_trunc('day'::text, created_at) AS day,
    count(*) AS total_requests,
    count(*) FILTER (WHERE success) AS successful,
    count(*) FILTER (WHERE (NOT success)) AS failed,
    count(*) FILTER (WHERE fallback_used) AS fallbacks,
    round(avg(latency_ms)) AS avg_latency_ms,
    round(percentile_cont((0.95)::double precision) WITHIN GROUP (ORDER BY ((latency_ms)::double precision))) AS p95_latency_ms,
    sum(total_tokens) AS total_tokens,
    round(avg(total_tokens)) AS avg_tokens_per_request
   FROM public.llm_request_log
  GROUP BY source_module, model_used, adapter_used, system_prompt_key, (date_trunc('day'::text, created_at))
  ORDER BY (date_trunc('day'::text, created_at)) DESC, (count(*)) DESC;


create or replace view "public"."mentor_history" as  SELECT id,
    user_id,
    title,
    message_count,
    is_archived,
    last_message_at,
    created_at,
    ( SELECT "left"(mm.content, 140) AS "left"
           FROM public.mentor_messages mm
          WHERE ((mm.conversation_id = mc.id) AND (mm.role = 'assistant'::text))
          ORDER BY mm.created_at DESC
         LIMIT 1) AS last_response_preview,
    ( SELECT COALESCE(mm.model_used, 'unknown'::text) AS "coalesce"
           FROM public.mentor_messages mm
          WHERE ((mm.conversation_id = mc.id) AND (mm.role = 'assistant'::text))
          ORDER BY mm.created_at DESC
         LIMIT 1) AS last_model_used
   FROM public.mentor_conversations mc
  ORDER BY last_message_at DESC NULLS LAST;


create or replace view "public"."user_dashboard" as  SELECT p.id,
    p.display_name,
    p.email,
    count(DISTINCT mc.id) FILTER (WHERE (NOT mc.is_archived)) AS active_mentor_conversations,
    count(DISTINCT s.id) AS total_signals,
    count(DISTINCT st.id) AS total_strategies,
    count(DISTINCT st.id) FILTER (WHERE st.is_runnable) AS validated_strategies,
    count(DISTINCT bt.id) FILTER (WHERE (bt.status = 'completed'::text)) AS completed_backtests,
    max(mc.last_message_at) AS last_mentor_activity,
    max(s.created_at) AS last_signal_extracted,
    p.created_at AS member_since
   FROM ((((public.profiles p
     LEFT JOIN public.mentor_conversations mc ON ((mc.user_id = p.id)))
     LEFT JOIN public.signals s ON ((s.user_id = p.id)))
     LEFT JOIN public.generated_codes st ON ((st.user_id = p.id)))
     LEFT JOIN public.backtests bt ON ((bt.user_id = p.id)))
  GROUP BY p.id, p.display_name, p.email, p.created_at;


CREATE TRIGGER backtest_on_complete BEFORE UPDATE ON public.backtests FOR EACH ROW EXECUTE FUNCTION public.sync_backtest_on_complete();

CREATE TRIGGER backtests_updated_at BEFORE UPDATE ON public.backtests FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER mentor_conversations_updated_at BEFORE UPDATE ON public.mentor_conversations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER auto_create_conversation BEFORE INSERT ON public.mentor_messages FOR EACH ROW EXECUTE FUNCTION public.create_conversation_if_missing();

CREATE TRIGGER mentor_messages_sync AFTER INSERT ON public.mentor_messages FOR EACH ROW EXECUTE FUNCTION public.sync_mentor_conversation();

CREATE TRIGGER profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER signals_updated_at BEFORE UPDATE ON public.signals FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


