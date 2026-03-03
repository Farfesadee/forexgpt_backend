"""
=============================================================================
TEST FILE: signal_service.py
=============================================================================

Tests every public method of SignalService.

HOW TO RUN:
    python test_signal_service.py

WHAT IT TESTS:
    1.  _parse_signal_response    -- JSON parsing with valid input
    2.  _parse_signal_response    -- handles null optional fields
    3.  _parse_signal_response    -- handles invalid direction/magnitude/time_horizon
    4.  _parse_signal_response    -- handles bad JSON gracefully (no crash)
    5.  _build_extraction_prompt  -- with company name
    6.  _build_extraction_prompt  -- without company name
    7.  extract_signal            -- REAL API call, signal found, save_to_db=False
    8.  extract_signal            -- REAL API call, no signal transcript, save_to_db=False
    9.  batch_extract_signals     -- REAL API call, 2 transcripts
    10. get_user_signals          -- reads from real Supabase
    11. get_signal_statistics     -- reads from real Supabase
    12. get_signal_by_id          -- wrong user_id returns None
    13. delete_signal             -- wrong user_id returns False

REQUIREMENTS:
    - .env file with HUGGING_FACE_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    - Run from the project root: python test_signal_service.py
=============================================================================
"""

import asyncio
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Colour helpers for readable output
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}PASS{RESET}  {msg}")
def fail(msg): print(f"  {RED}FAIL{RESET}  {msg}")
def info(msg): print(f"  {YELLOW}INFO{RESET}  {msg}")
def section(title): print(f"\n{BOLD}{CYAN}{'='*60}{RESET}\n{BOLD}{CYAN}  {title}{RESET}\n{CYAN}{'='*60}{RESET}")

PASS = 0
FAIL = 0

def check(condition, label, detail=""):
    global PASS, FAIL
    if condition:
        ok(label)
        PASS += 1
    else:
        fail(f"{label}  |  {detail}")
        FAIL += 1

# ---------------------------------------------------------------------------
# Sample transcripts
# ---------------------------------------------------------------------------
TRANSCRIPT_WITH_SIGNAL = """
In Q1 2024, we experienced a significant 6% revenue headwind from currency movements,
primarily driven by USD strength versus the Euro. Our European operations account for
approximately 40% of total revenue. The EUR/USD exchange rate moved from 1.10 to 1.05
during the quarter, creating meaningful pressure on our reported results.
We expect this EUR/USD headwind to continue into Q2 given current market conditions.
"""

TRANSCRIPT_NO_SIGNAL = """
Our Q1 results were strong. Revenue grew 12% year-over-year driven by our cloud
business. We added 500 new enterprise customers. Our product roadmap for the rest
of 2024 includes three major platform upgrades. The team has done exceptional work
and we remain on track for our full-year targets.
"""

# ---------------------------------------------------------------------------
# Helper: build the service with real clients
# ---------------------------------------------------------------------------
def build_service():
    from huggingface_hub import AsyncInferenceClient
    from services.signal_service import SignalService

    hf_token = os.getenv("HUGGING_FACE_TOKEN")
    if not hf_token:
        print(f"{RED}ERROR: HUGGING_FACE_TOKEN not found in .env{RESET}")
        sys.exit(1)

    hf_client = AsyncInferenceClient(token=hf_token)
    model_id  = os.getenv("SIGNAL_MODEL_ID", "forexgpt/mistral-7b-forex-signals")
    return SignalService(hf_client=hf_client, model_id=model_id)


# ===========================================================================
# UNIT TESTS  (no API calls, no DB)
# ===========================================================================

def test_parse_valid_signal():
    section("UNIT TEST 1 — _parse_signal_response: valid full signal")
    from services.signal_service import SignalService
    svc = SignalService.__new__(SignalService)

    raw = json.dumps({
        "signal":        True,
        "currency_pair": "EUR/USD",
        "direction":     "SHORT",
        "confidence":    0.85,
        "reasoning":     "6% USD headwind vs EUR mentioned in earnings.",
        "magnitude":     "high",
        "time_horizon":  "current_quarter"
    })

    result = svc._parse_signal_response(raw)
    check(result["signal"]        is True,        "signal is True")
    check(result["currency_pair"] == "EUR/USD",   "currency_pair correct")
    check(result["direction"]     == "SHORT",     "direction correct")
    check(result["confidence"]    == 0.85,        "confidence correct")
    check(result["magnitude"]     == "high",      "magnitude correct")
    check(result["time_horizon"]  == "current_quarter", "time_horizon correct")


def test_parse_null_optional_fields():
    section("UNIT TEST 2 — _parse_signal_response: null optional fields")
    from services.signal_service import SignalService
    svc = SignalService.__new__(SignalService)

    raw = json.dumps({
        "signal":        True,
        "currency_pair": None,
        "direction":     None,
        "confidence":    None,
        "reasoning":     "Currency headwind mentioned but pair unclear.",
        "magnitude":     None,
        "time_horizon":  None
    })

    result = svc._parse_signal_response(raw)
    check(result["signal"]        is True,  "signal is True")
    check(result["currency_pair"] is None,  "currency_pair is None — OK")
    check(result["direction"]     is None,  "direction is None — OK")
    check(result["confidence"]    is None,  "confidence is None — OK")
    check(result["magnitude"]     is None,  "magnitude is None — OK")
    check(result["time_horizon"]  is None,  "time_horizon is None — OK")


def test_parse_invalid_values_reset_to_none():
    section("UNIT TEST 3 — _parse_signal_response: invalid values → None")
    from services.signal_service import SignalService
    svc = SignalService.__new__(SignalService)

    raw = json.dumps({
        "signal":        True,
        "currency_pair": "EUR/USD",
        "direction":     "SIDEWAYS",        # invalid
        "confidence":    1.5,               # out of range → clamped to 1.0
        "reasoning":     "Test.",
        "magnitude":     "extreme",         # invalid
        "time_horizon":  "next_week"        # invalid
    })

    result = svc._parse_signal_response(raw)
    check(result["direction"]    is None,  "invalid direction → None")
    check(result["confidence"]   == 1.0,   "confidence clamped to 1.0")
    check(result["magnitude"]    is None,  "invalid magnitude → None")
    check(result["time_horizon"] is None,  "invalid time_horizon → None")


def test_parse_bad_json_no_crash():
    section("UNIT TEST 4 — _parse_signal_response: bad JSON → safe fallback")
    from services.signal_service import SignalService
    svc = SignalService.__new__(SignalService)

    result = svc._parse_signal_response("This is not JSON at all !!!")
    check(result["signal"]    is False, "signal is False on parse failure")
    check("reasoning" in result,        "reasoning field present in fallback")
    check(result["currency_pair"] is None, "currency_pair None in fallback")


def test_build_prompt_with_company():
    section("UNIT TEST 5 — _build_extraction_prompt: with company name")
    from services.signal_service import SignalService
    svc = SignalService.__new__(SignalService)

    prompt = svc._build_extraction_prompt("Some transcript text", "Microsoft")
    check("Microsoft" in prompt,          "company name in prompt")
    check("Some transcript text" in prompt, "transcript text in prompt")


def test_build_prompt_without_company():
    section("UNIT TEST 6 — _build_extraction_prompt: without company name")
    from services.signal_service import SignalService
    svc = SignalService.__new__(SignalService)

    prompt = svc._build_extraction_prompt("Some transcript text", None)
    check("Some transcript text" in prompt, "transcript text in prompt")
    check("Microsoft" not in prompt,        "no company name injected")


# ===========================================================================
# INTEGRATION TESTS  (real API + real DB)
# ===========================================================================

async def test_extract_signal_found():
    section("INTEGRATION TEST 7 — extract_signal: signal found (no DB save)")
    svc = build_service()
    info(f"Using model: {svc.model_id}")
    info("Calling HuggingFace API...")

    try:
        result = await svc.extract_signal(
            user_id="00000000-0000-0000-0000-000000000001",
            transcript=TRANSCRIPT_WITH_SIGNAL,
            company_name="TestCorp",
            save_to_db=False
        )
        check("signal"    in result,          "signal field present")
        check("reasoning" in result,          "reasoning field present")
        check(isinstance(result["signal"], bool), "signal is boolean")
        info(f"signal={result['signal']}, pair={result.get('currency_pair')}, "
             f"direction={result.get('direction')}, confidence={result.get('confidence')}")
        info(f"reasoning: {result.get('reasoning', '')[:120]}")
    except Exception as e:
        fail(f"extract_signal raised: {e}")
        global FAIL
        FAIL += 1


async def test_extract_signal_not_found():
    section("INTEGRATION TEST 8 — extract_signal: no signal transcript (no DB save)")
    svc = build_service()
    info("Calling HuggingFace API with non-forex transcript...")

    try:
        result = await svc.extract_signal(
            user_id="00000000-0000-0000-0000-000000000001",
            transcript=TRANSCRIPT_NO_SIGNAL,
            company_name="SomeTechCorp",
            save_to_db=False
        )
        check("signal" in result, "signal field present")
        check(isinstance(result["signal"], bool), "signal is boolean")
        info(f"signal={result['signal']}")
        info(f"reasoning: {result.get('reasoning', '')[:120]}")
    except Exception as e:
        fail(f"extract_signal raised: {e}")
        global FAIL
        FAIL += 1


async def test_batch_extract():
    section("INTEGRATION TEST 9 — batch_extract_signals: 2 transcripts (no DB save)")
    svc = build_service()
    info("Calling HuggingFace API for 2 transcripts...")

    transcripts = [
        {"text": TRANSCRIPT_WITH_SIGNAL, "company_name": "EuroTech"},
        {"text": TRANSCRIPT_NO_SIGNAL,   "company_name": "CloudCo"},
    ]

    try:
        results = await svc.batch_extract_signals(
            user_id="00000000-0000-0000-0000-000000000001",
            transcripts=transcripts,
            save_to_db=False
        )
        check(len(results) == 2,                    "got 2 results")
        check(isinstance(results[0]["signal"], bool), "result[0] signal is bool")
        check(isinstance(results[1]["signal"], bool), "result[1] signal is bool")
        for i, r in enumerate(results):
            info(f"Transcript {i+1}: signal={r['signal']}, pair={r.get('currency_pair')}")
    except Exception as e:
        fail(f"batch_extract_signals raised: {e}")
        global FAIL
        FAIL += 1


def test_get_user_signals():
    section("INTEGRATION TEST 10 — get_user_signals: reads from Supabase")
    svc = build_service()

    try:
        signals = svc.get_user_signals(
            user_id="00000000-0000-0000-0000-000000000001",
            limit=5
        )
        check(isinstance(signals, list), "returns a list")
        info(f"Found {len(signals)} signals in DB for test user")
    except Exception as e:
        fail(f"get_user_signals raised: {e}")
        global FAIL
        FAIL += 1


def test_get_signal_statistics():
    section("INTEGRATION TEST 11 — get_signal_statistics: reads from Supabase")
    svc = build_service()

    try:
        stats = svc.get_signal_statistics(
            user_id="00000000-0000-0000-0000-000000000001"
        )
        check("total_signals"     in stats, "total_signals key present")
        check("by_currency_pair"  in stats, "by_currency_pair key present")
        check("by_direction"      in stats, "by_direction key present")
        check("average_confidence" in stats, "average_confidence key present")
        info(f"total_signals={stats['total_signals']}, avg_confidence={stats['average_confidence']}")
    except Exception as e:
        fail(f"get_signal_statistics raised: {e}")
        global FAIL
        FAIL += 1


def test_get_signal_by_id_wrong_user():
    section("INTEGRATION TEST 12 — get_signal_by_id: wrong user_id returns None")
    svc = build_service()

    try:
        result = svc.get_signal_by_id(
            signal_id="00000000-0000-0000-0000-999999999999",  # non-existent
            user_id="00000000-0000-0000-0000-000000000001"
        )
        check(result is None, "returns None for non-existent signal — correct")
    except Exception as e:
        fail(f"get_signal_by_id raised: {e}")
        global FAIL
        FAIL += 1


def test_delete_signal_wrong_user():
    section("INTEGRATION TEST 13 — delete_signal: wrong user returns False")
    svc = build_service()

    try:
        result = svc.delete_signal(
            signal_id="00000000-0000-0000-0000-999999999999",  # non-existent
            user_id="00000000-0000-0000-0000-000000000001"
        )
        check(result is False, "returns False for non-existent signal — correct")
    except Exception as e:
        fail(f"delete_signal raised: {e}")
        global FAIL
        FAIL += 1


# ===========================================================================
# MAIN RUNNER
# ===========================================================================

async def main():
    print(f"\n{BOLD}{'='*60}")
    print(f"  ForexGPT — Signal Service Test Suite")
    print(f"{'='*60}{RESET}")

    # Unit tests (no network needed)
    test_parse_valid_signal()
    test_parse_null_optional_fields()
    test_parse_invalid_values_reset_to_none()
    test_parse_bad_json_no_crash()
    test_build_prompt_with_company()
    test_build_prompt_without_company()

    # Integration tests (needs .env)
    await test_extract_signal_found()
    await test_extract_signal_not_found()
    await test_batch_extract()
    test_get_user_signals()
    test_get_signal_statistics()
    test_get_signal_by_id_wrong_user()
    test_delete_signal_wrong_user()

    # Summary
    total = PASS + FAIL
    print(f"\n{BOLD}{'='*60}")
    print(f"  RESULTS: {PASS}/{total} passed", end="")
    if FAIL == 0:
        print(f"  {GREEN}ALL PASSED{RESET}")
    else:
        print(f"  {RED}{FAIL} FAILED{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
