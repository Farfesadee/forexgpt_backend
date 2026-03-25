#!/bin/bash

# =============================================================================
# ForexGPT - API Integration Test Script
# Engineer 4 - Database & Integration
# =============================================================================
#
# What this script does:
#   Walks through the complete ForexGPT flow by hitting real API endpoints,
#   exactly the same way the frontend would. No mocking, no shortcuts.
#
#   Step 1 → CodeGen generates a strategy
#   Step 2 → Backtest runs that strategy
#   Step 3 → Mentor analyzes the results (only if Sharpe < 1.0)
#   Step 4 → CodeGen improves the strategy based on mentor feedback
#   Step 5 → Backtest runs the improved strategy
#
# Requirements:
#   - The FastAPI server must be running on localhost:8000
#   - jq must be installed (used to parse and build JSON safely)
#
# How to run:
#   chmod +x tests/test_api_integration.sh
#   ./tests/test_api_integration.sh
# =============================================================================

set -e  # Stop the script immediately if any command fails

BASE_URL="http://localhost:8000"

# =============================================================================
# ✏️  UPDATE THESE TWO VALUES BEFORE RUNNING
# =============================================================================

# Your test user's UUID from the profiles table in Supabase
USER_ID="ceabb23f-ca80-4fd7-a811-40c3a03ad344"

# Your JWT token — get it from browser DevTools after logging into the app:
#   1. Open the app in your browser and log in
#   2. Open DevTools → Network tab
#   3. Click any API request
#   4. Look for the Authorization header → copy everything after "Bearer "
TOKEN="eyJhbGciOiJFUzI1NiIsImtpZCI6IjU0ZTRjODZmLTQ4ZjEtNDNmYi05NjMxLWQyNWU3MDYxNTEzYiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2pjd2h2cmlmbGF1bHBmdnNxdnNrLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiJjZWFiYjIzZi1jYTgwLTRmZDctYTgxMS00MGMzYTAzYWQzNDQiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzc0MzUwODkyLCJpYXQiOjE3NzQzNDcyOTIsImVtYWlsIjoibWFzajMzNzMzQGdtYWlsLmNvbSIsInBob25lIjoiIiwiYXBwX21ldGFkYXRhIjp7InByb3ZpZGVyIjoiZW1haWwiLCJwcm92aWRlcnMiOlsiZW1haWwiXX0sInVzZXJfbWV0YWRhdGEiOnsiZW1haWwiOiJtYXNqMzM3MzNAZ21haWwuY29tIiwiZW1haWxfdmVyaWZpZWQiOnRydWUsImZ1bGxfbmFtZSI6IlJveWFsIFRyYWRlciIsInBob25lX3ZlcmlmaWVkIjpmYWxzZSwic3ViIjoiY2VhYmIyM2YtY2E4MC00ZmQ3LWE4MTEtNDBjM2EwM2FkMzQ0In0sInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiYWFsIjoiYWFsMSIsImFtciI6W3sibWV0aG9kIjoicGFzc3dvcmQiLCJ0aW1lc3RhbXAiOjE3NzQzNDM3MTl9XSwic2Vzc2lvbl9pZCI6IjgwYTAzOTcyLWM3YTItNDhjNC1iZDMzLTdlOTlhOWQ3NWRmNyIsImlzX2Fub255bW91cyI6ZmFsc2V9.ANdg0XW86LqjZoaTPVFN9Hy7qjMCetu12kiVZaNJsJRBS-7PvnJd-fmda9qaHlNqWk6BBFQeaINPvr2khXjHoA"

# =============================================================================


# Shared headers used by every curl call in this script
AUTH_HEADER="Authorization: Bearer $TOKEN"
CONTENT_HEADER="Content-Type: application/json"

# A small helper to print section headers cleanly
section() {
    echo ""
    echo "---------------------------------------------"
    echo "  $1"
    echo "---------------------------------------------"
}

# A helper to check if a response contains an error field.
# FastAPI returns {"detail": "..."} for 4xx and 5xx errors.
check_for_error() {
    local response=$1
    local step_name=$2

    if echo "$response" | jq -e '.detail' > /dev/null 2>&1; then
        echo ""
        echo "✗ $step_name failed."
        echo "  Error: $(echo $response | jq -r '.detail')"
        echo ""
        exit 1
    fi
}

echo ""
echo "============================================="
echo "   ForexGPT API Integration Test"
echo "============================================="
echo "  Server : $BASE_URL"
echo "  User   : $USER_ID"
echo "============================================="


# -----------------------------------------------------------------------------
# Step 1: Ask CodeGen to generate a basic RSI mean reversion strategy.
# We use jq -n to build the JSON body safely — this handles any special
# characters in the values automatically without breaking the JSON.
# -----------------------------------------------------------------------------
section "Step 1 of 5 — Generating strategy code"

STEP1_BODY=$(jq -n \
  --arg user_id "$USER_ID" \
  --arg strategy_description "Create a simple RSI mean reversion strategy" \
  '{user_id: $user_id, strategy_description: $strategy_description}')

CODE_RESPONSE=$(curl -s -X POST "$BASE_URL/codegen/generate" \
  -H "$CONTENT_HEADER" \
  -H "$AUTH_HEADER" \
  -d "$STEP1_BODY")

check_for_error "$CODE_RESPONSE" "CodeGen /generate"

# GENERATED_CODE=$(echo "$CODE_RESPONSE" | jq -r '.code')
GENERATED_CODE=$(echo "$CODE_RESPONSE" | jq -r '.code' | tr -d '\r' | tr -d '\000-\010' | tr -d '\013-\037')
CONV_ID=$(echo "$CODE_RESPONSE"        | jq -r '.conversation_id')

echo "✓ Strategy code generated successfully"
echo "  Conversation ID : $CONV_ID"
echo "  Code length     : ${#GENERATED_CODE} characters"


# -----------------------------------------------------------------------------
# Step 2: Run that generated code through the backtest engine.
# We strip \r (Windows line endings) from the code before sending —
# Git Bash sometimes adds them and FastAPI rejects the malformed body.
# -----------------------------------------------------------------------------
section "Step 2 of 5 — Running backtest on generated strategy"

GENERATED_CODE_CLEAN=$(echo "$GENERATED_CODE" | tr -d '\r')

STEP2_BODY=$(jq -n \
  --arg user_id          "$USER_ID" \
  --arg custom_code      "$GENERATED_CODE_CLEAN" \
  --arg pair             "EURUSD" \
  --arg start_date       "2023-01-01" \
  --arg end_date         "2023-12-31" \
  --argjson initial_capital   10000 \
  --argjson position_size_pct 0.1 \
  '{
    user_id:           $user_id,
    custom_code:       $custom_code,
    pair:              $pair,
    start_date:        $start_date,
    end_date:          $end_date,
    initial_capital:   $initial_capital,
    position_size_pct: $position_size_pct
  }')

BACKTEST_RESPONSE=$(curl -s -X POST "$BASE_URL/backtest/run/custom" \
  -H "$CONTENT_HEADER" \
  -H "$AUTH_HEADER" \
  -d "$STEP2_BODY")

check_for_error "$BACKTEST_RESPONSE" "Backtest /run/custom"

SHARPE=$(echo "$BACKTEST_RESPONSE"       | jq -r '.sharpe_ratio')
DRAWDOWN=$(echo "$BACKTEST_RESPONSE"     | jq -r '.max_drawdown_pct')
WIN_RATE=$(echo "$BACKTEST_RESPONSE"     | jq -r '.win_rate_pct')
TOTAL_RETURN=$(echo "$BACKTEST_RESPONSE" | jq -r '.total_return_pct')
TOTAL_TRADES=$(echo "$BACKTEST_RESPONSE" | jq -r '.total_trades')

echo "✓ Backtest completed successfully"
echo ""
echo "  Results:"
echo "    Sharpe Ratio  : $SHARPE"
echo "    Max Drawdown  : $DRAWDOWN%"
echo "    Win Rate      : $WIN_RATE%"
echo "    Total Return  : $TOTAL_RETURN%"
echo "    Total Trades  : $TOTAL_TRADES"


# -----------------------------------------------------------------------------
# Steps 3-5 only run if the strategy performed poorly (Sharpe below 1.0).
# We use Python for the float comparison since bc is not available on
# Windows Git Bash by default.
# -----------------------------------------------------------------------------
if python -c "exit(0 if float('$SHARPE') < 1.0 else 1)"; then

    echo ""
    echo "  Sharpe ratio of $SHARPE is below 1.0 — strategy underperformed."
    echo "  Moving on to analysis and improvement..."


    # -------------------------------------------------------------------------
    # Step 3: Send the poor backtest results to the Mentor for analysis.
    # Note: user_id is NOT in the body — the server reads it from the JWT token.
    # -------------------------------------------------------------------------
    section "Step 3 of 5 — Mentor analyzing poor results"

    STEP3_BODY=$(jq -n \
      --argjson metrics "$(echo "$BACKTEST_RESPONSE" | jq -c '.')" \
      '{
        backtest_context: {
          strategy_type: "custom",
          metrics: $metrics
        }
      }')

    ANALYSIS_RESPONSE=$(curl -s -X POST "$BASE_URL/mentor/backtest-conversations" \
      -H "$CONTENT_HEADER" \
      -H "$AUTH_HEADER" \
      -d "$STEP3_BODY")

    check_for_error "$ANALYSIS_RESPONSE" "Mentor /backtest-conversations"

    ANALYSIS=$(echo "$ANALYSIS_RESPONSE"       | jq -r '.analysis')
    MENTOR_CONV_ID=$(echo "$ANALYSIS_RESPONSE" | jq -r '.conversation_id')

    echo "✓ Mentor analysis received"
    echo "  Conversation ID : $MENTOR_CONV_ID"
    echo "  Analysis length : ${#ANALYSIS} characters"
    echo ""
    echo "  Preview (first 200 chars):"
    echo "  $(echo "$ANALYSIS" | cut -c1-200)..."


    # -------------------------------------------------------------------------
    # Step 4: Pass original code + backtest results + mentor analysis to
    # CodeGen and ask it to produce an improved version of the strategy.
    # All values are passed via jq --arg / --argjson so special characters,
    # newlines, and quotes in the code and analysis are handled safely.
    # -------------------------------------------------------------------------

    section "Step 4 of 5 — CodeGen improving the strategy"

# Temporarily disable exit-on-error for this step so we can
# capture and inspect the response even if something fails
set +e

IMPROVE_BODY_FILE=$(mktemp /tmp/improve_body_XXXXXX.json)

jq -n \
  --arg     user_id          "$USER_ID" \
  --arg     original_code    "$GENERATED_CODE_CLEAN" \
  --argjson backtest_results "$(echo "$BACKTEST_RESPONSE" | jq -c '.')" \
  --arg     mentor_analysis  "$ANALYSIS" \
  '{
    user_id:          $user_id,
    original_code:    $original_code,
    backtest_results: $backtest_results,
    mentor_analysis:  $mentor_analysis
  }' > "$IMPROVE_BODY_FILE"

IMPROVE_RESPONSE=$(curl -s -X POST "$BASE_URL/codegen/improve" \
  -H "$CONTENT_HEADER" \
  -H "$AUTH_HEADER" \
  --data-binary "@$IMPROVE_BODY_FILE")

rm -f "$IMPROVE_BODY_FILE"

# Re-enable exit-on-error
set -e

check_for_error "$IMPROVE_RESPONSE" "CodeGen /improve"

IMPROVED_CODE=$(echo "$IMPROVE_RESPONSE"    | jq -r '.code')
IMPROVED_CODE_ID=$(echo "$IMPROVE_RESPONSE" | jq -r '.code_id')

echo "✓ Improved strategy generated"
echo "  Code ID     : $IMPROVED_CODE_ID"
echo "  Code length : ${#IMPROVED_CODE} characters"
echo "  (Improved code should be longer than original — improvements were added)"

    # -------------------------------------------------------------------------
    # Step 5: Run the improved strategy through the backtest engine again
    # and compare results against the original run.
    # -------------------------------------------------------------------------
    section "Step 5 of 5 — Backtesting the improved strategy"

    IMPROVED_CODE_CLEAN=$(echo "$IMPROVED_CODE" | tr -d '\r')

    STEP5_BODY=$(jq -n \
      --arg user_id          "$USER_ID" \
      --arg custom_code      "$IMPROVED_CODE_CLEAN" \
      --arg pair             "EURUSD" \
      --arg start_date       "2023-01-01" \
      --arg end_date         "2023-12-31" \
      --argjson initial_capital   10000 \
      --argjson position_size_pct 0.1 \
      '{
        user_id:           $user_id,
        custom_code:       $custom_code,
        pair:              $pair,
        start_date:        $start_date,
        end_date:          $end_date,
        initial_capital:   $initial_capital,
        position_size_pct: $position_size_pct
      }')

    IMPROVED_BACKTEST=$(curl -s -X POST "$BASE_URL/backtest/run/custom" \
      -H "$CONTENT_HEADER" \
      -H "$AUTH_HEADER" \
      -d "$STEP5_BODY")

    check_for_error "$IMPROVED_BACKTEST" "Backtest /run/custom (improved)"

    IMPROVED_SHARPE=$(echo "$IMPROVED_BACKTEST"   | jq -r '.sharpe_ratio')
    IMPROVED_DRAWDOWN=$(echo "$IMPROVED_BACKTEST" | jq -r '.max_drawdown_pct')
    IMPROVED_WIN_RATE=$(echo "$IMPROVED_BACKTEST" | jq -r '.win_rate_pct')
    IMPROVED_RETURN=$(echo "$IMPROVED_BACKTEST"   | jq -r '.total_return_pct')

    echo "✓ Improved backtest completed"


    # -------------------------------------------------------------------------
    # Final comparison — side by side so it's easy to see if things improved
    # -------------------------------------------------------------------------
    echo ""
    echo "============================================="
    echo "   Performance Comparison"
    echo "============================================="
    echo ""
    printf "  %-20s %-15s %-15s\n" "Metric"       "Original"       "Improved"
    printf "  %-20s %-15s %-15s\n" "------"       "--------"       "--------"
    printf "  %-20s %-15s %-15s\n" "Sharpe Ratio" "$SHARPE"        "$IMPROVED_SHARPE"
    printf "  %-20s %-15s %-15s\n" "Max Drawdown" "$DRAWDOWN%"     "$IMPROVED_DRAWDOWN%"
    printf "  %-20s %-15s %-15s\n" "Win Rate"     "$WIN_RATE%"     "$IMPROVED_WIN_RATE%"
    printf "  %-20s %-15s %-15s\n" "Total Return" "$TOTAL_RETURN%" "$IMPROVED_RETURN%"
    echo ""

else
    # Strategy performed well on the first try — no improvement loop needed
    echo ""
    echo "  Sharpe ratio of $SHARPE is above 1.0 — strategy performed well!"
    echo "  No mentor analysis or improvement needed."
fi


echo ""
echo "============================================="
echo "   All steps completed successfully ✓"
echo "============================================="
echo ""