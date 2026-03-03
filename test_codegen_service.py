"""
=============================================================================
TEST FILE: codegen_service.py
HOW TO RUN: python test_codegen_service.py   (run from project root)
NEEDS: .env with MISTRAL_API_KEY, MISTRAL_MODEL_ID,
       SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

UNIT TESTS  (no API / no DB):
    1.  _build_user_message  -- initial generation scenario
    2.  _build_user_message  -- debugging scenario (previous_code + error_message)
    3.  _build_user_message  -- modification scenario (previous_code only)
    4.  _parse_response      -- extracts code from triple-backtick python block
    5.  _parse_response      -- extracts code from generic triple-backtick block
    6.  _parse_response      -- no code block, full response treated as code

INTEGRATION TESTS  (real Mistral API + real Supabase):
    7.  generate_code        -- initial generation, new conversation
    8.  generate_code        -- debugging scenario using conversation_id
    9.  generate_code        -- modification scenario using conversation_id
    10. generate_code        -- bad conversation_id starts a fresh conversation
    11. list_generated_codes -- reads from Supabase
    12. get_generated_code   -- fetch by code_id
    13. get_generated_code   -- wrong user_id returns None
    14. get_conversation_history -- reads from Supabase
    15. Full end-to-end      -- generate, modify, list, get, history
=============================================================================
"""

import asyncio, os, sys
from dotenv import load_dotenv
load_dotenv()

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
X = "\033[0m";  B = "\033[1m"

def ok(m):   print(f"  {G}PASS{X}  {m}")
def fl(m):   print(f"  {R}FAIL{X}  {m}")
def nfo(m):  print(f"  {Y}INFO{X}  {m}")
def sec(t):  print(f"\n{B}{C}{'='*60}{X}\n{B}{C}  {t}{X}\n{C}{'='*60}{X}")

P = 0
F = 0

def ck(cond, label, detail=""):
    global P, F
    if cond:
        ok(label); P += 1
    else:
        fl(f"{label}  |  {detail}"); F += 1


# ---------------------------------------------------------------------------
# constants used across tests
# ---------------------------------------------------------------------------
UID   = "00000000-0000-0000-0000-000000000001"
WUID  = "00000000-0000-0000-0000-000000000002"

STRATEGY = "Create an RSI mean reversion strategy. Buy when RSI < 30, sell when RSI > 70."

SAMPLE_CODE = """
import pandas as pd
import numpy as np

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def generate_signals(df):
    df['rsi'] = calculate_rsi(df['close'])
    df['signal'] = 0
    df.loc[df['rsi'] < 30, 'signal'] = 1
    df.loc[df['rsi'] > 70, 'signal'] = -1
    return df
"""


def build():
    from mistralai import Mistral
    from services.codegen_service import CodeGenService
    key = os.getenv("MISTRAL_API_KEY")
    if not key:
        print(f"{R}ERROR: MISTRAL_API_KEY not found in .env{X}")
        sys.exit(1)
    return CodeGenService(
        mistral_client=Mistral(api_key=key),
        model_id=os.getenv("MISTRAL_MODEL_ID", "mistral-small-latest"),
    )


# ===========================================================================
# UNIT TESTS
# ===========================================================================

def test_build_initial():
    sec("UNIT 1 -- _build_user_message: initial generation")
    from services.codegen_service import CodeGenService
    s = CodeGenService.__new__(CodeGenService)
    s.system_prompt = ""
    msg = s._build_user_message(STRATEGY, None, None)
    ck("RSI" in msg,                            "strategy description included")
    ck("pandas" in msg,                         "requirements included")
    ck("previous" not in msg.lower(),           "no previous-code reference")
    ck("error" not in msg.lower(),              "no error reference")


def test_build_debug():
    sec("UNIT 2 -- _build_user_message: debugging scenario")
    from services.codegen_service import CodeGenService
    s = CodeGenService.__new__(CodeGenService)
    s.system_prompt = ""
    msg = s._build_user_message("Fix the KeyError", SAMPLE_CODE, "KeyError: 'close'")
    ck("KeyError" in msg,                       "error message included")
    ck("close" in msg,                          "error detail included")
    ck("rsi" in msg.lower() or "def " in msg,   "previous code included")
    ck("corrected" in msg.lower() or "fix" in msg.lower(), "fix instruction present")


def test_build_modify():
    sec("UNIT 3 -- _build_user_message: modification scenario")
    from services.codegen_service import CodeGenService
    s = CodeGenService.__new__(CodeGenService)
    s.system_prompt = ""
    msg = s._build_user_message("Add a 2% stop loss", SAMPLE_CODE, None)
    ck("stop loss" in msg.lower(),              "modification request in message")
    ck("def " in msg,                           "previous code included")
    ck("KeyError" not in msg,                   "no error reference in modification")


def test_parse_python_block():
    sec("UNIT 4 -- _parse_response: python code block")
    from services.codegen_service import CodeGenService
    s = CodeGenService.__new__(CodeGenService)
    raw = "Here is the code:\n```python\nimport pandas as pd\ndf = pd.DataFrame()\n```\nThis uses pandas."
    code, explanation = s._parse_response(raw)
    ck("import pandas" in code,                 "code extracted correctly")
    ck("```" not in code,                       "no backticks in extracted code")
    ck("This uses pandas" in explanation,       "explanation extracted")


def test_parse_generic_block():
    sec("UNIT 5 -- _parse_response: generic code block")
    from services.codegen_service import CodeGenService
    s = CodeGenService.__new__(CodeGenService)
    raw = "Result:\n```\nx = 1 + 1\nprint(x)\n```\nSimple addition."
    code, explanation = s._parse_response(raw)
    ck("x = 1 + 1" in code,                    "code extracted correctly")
    ck("```" not in code,                       "no backticks in code")
    ck("Simple addition" in explanation,        "explanation extracted")


def test_parse_no_block():
    sec("UNIT 6 -- _parse_response: no code block")
    from services.codegen_service import CodeGenService
    s = CodeGenService.__new__(CodeGenService)
    raw = "x = 1\ny = 2\nprint(x + y)"
    code, explanation = s._parse_response(raw)
    ck("x = 1" in code,                        "full response treated as code")
    ck("Generated trading" in explanation,      "default explanation used")


# ===========================================================================
# INTEGRATION TESTS
# ===========================================================================

async def test_generate_initial():
    sec("INTEGRATION 7 -- generate_code: initial generation")
    s = build()
    nfo("Calling Mistral API for code generation...")
    try:
        r = await s.generate_code(user_id=UID, strategy_description=STRATEGY)
        ck("code"            in r,                          "code field present")
        ck("explanation"     in r,                          "explanation field present")
        ck("conversation_id" in r,                          "conversation_id field present")
        ck(r.get("language") == "python",                   "language is python")
        ck(isinstance(r["code"], str) and len(r["code"]) > 10, "code is non-empty")
        nfo(f"conversation_id: {r['conversation_id']}")
        nfo(f"code snippet:    {r['code'][:100]}...")
        nfo(f"explanation:     {r['explanation'][:100]}...")
        return r["conversation_id"], r["code"], r.get("code_id")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1
        return None, None, None


async def test_generate_debug(cid, code):
    sec("INTEGRATION 8 -- generate_code: debugging scenario")
    if not cid:
        nfo("Skipping -- no conv_id from TEST 7"); return
    s = build()
    nfo("Calling Mistral API with an error to debug...")
    try:
        r = await s.generate_code(
            user_id=UID,
            strategy_description="The code crashes. There is a KeyError on the close column. Fix it.",
            conversation_id=cid,
            previous_code=code,
            error_message="KeyError: 'close'",
        )
        ck("code"            in r,                  "code field present")
        ck("explanation"     in r,                  "explanation field present")
        ck(r["conversation_id"] == cid,             "same conversation_id returned")
        ck(isinstance(r["code"], str),              "code is a string")
        nfo(f"Fixed code snippet: {r['code'][:100]}...")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


async def test_generate_modify(cid, code):
    sec("INTEGRATION 9 -- generate_code: modification scenario")
    if not cid:
        nfo("Skipping -- no conv_id from TEST 7"); return
    s = build()
    nfo("Calling Mistral API with a modification request...")
    try:
        r = await s.generate_code(
            user_id=UID,
            strategy_description="Add a 2% stop loss below the entry price.",
            conversation_id=cid,
            previous_code=code,
        )
        ck("code"            in r,                  "code field present")
        ck(r["conversation_id"] == cid,             "same conversation_id returned")
        ck(isinstance(r["code"], str),              "code is a string")
        nfo(f"Modified code snippet: {r['code'][:100]}...")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


async def test_generate_bad_conv():
    sec("INTEGRATION 10 -- generate_code: bad conv_id starts fresh")
    s = build()
    fake = "00000000-dead-beef-0000-000000000000"
    nfo(f"Passing fake conversation_id: {fake}")
    try:
        r = await s.generate_code(
            user_id=UID,
            strategy_description="Simple MACD crossover strategy.",
            conversation_id=fake,
        )
        ck("conversation_id" in r,                  "new conversation_id generated")
        ck("code"            in r,                  "code field present")
        ck(r["conversation_id"] != fake,            "different conv_id from the fake one")
        nfo(f"New conv_id: {r['conversation_id']}")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


def test_list_codes():
    sec("INTEGRATION 11 -- list_generated_codes: reads from Supabase")
    s = build()
    try:
        codes = s.list_generated_codes(user_id=UID, limit=5)
        ck(isinstance(codes, list),                 "returns a list")
        nfo(f"Found {len(codes)} codes in DB")
        if codes:
            ck("id"          in codes[0],           "id key present")
            ck("description" in codes[0],           "description key present")
            ck("created_at"  in codes[0],           "created_at key present")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


def test_get_code(code_id):
    sec("INTEGRATION 12 -- get_generated_code: fetch by code_id")
    if not code_id:
        nfo("Skipping -- no code_id from TEST 7"); return
    s = build()
    try:
        r = s.get_generated_code(code_id=code_id, user_id=UID)
        ck(r is not None,                           "returns a result (not None)")
        if r:
            ck("code"        in r,                  "code key present")
            ck("description" in r,                  "description key present")
            nfo(f"code_id: {r.get('id')}, desc: {str(r.get('description',''))[:60]}")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


def test_get_code_wrong_user(code_id):
    sec("INTEGRATION 13 -- get_generated_code: wrong user_id returns None")
    if not code_id:
        nfo("Skipping -- no code_id from TEST 7"); return
    s = build()
    try:
        r = s.get_generated_code(code_id=code_id, user_id=WUID)
        ck(r is None,                               "wrong user gets None -- correct")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


def test_conversation_history(cid):
    sec("INTEGRATION 14 -- get_conversation_history: reads from Supabase")
    if not cid:
        nfo("Skipping -- no conv_id from TEST 7"); return
    s = build()
    try:
        h = s.get_conversation_history(conversation_id=cid, user_id=UID)
        ck(isinstance(h, list),                     "returns a list")
        ck(len(h) >= 2,                             "at least 2 messages in history")
        if h:
            ck("role"    in h[0],                   "role key present")
            ck("content" in h[0],                   "content key present")
        nfo(f"History has {len(h)} messages")
    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


async def test_end_to_end():
    sec("TEST 15 -- Full end-to-end: generate, modify, list, get, history")
    s = build()
    nfo("Running full lifecycle...")
    try:
        # Step 1 — generate initial code
        r1 = await s.generate_code(
            user_id=UID,
            strategy_description="Simple Bollinger Band breakout strategy.",
        )
        cid     = r1["conversation_id"]
        code    = r1["code"]
        code_id = r1.get("code_id")
        ck(bool(cid),  "Step 1: conversation created")
        ck(bool(code), "Step 1: code generated")
        nfo(f"Step 1 code: {code[:80]}...")

        # Step 2 — modify the code
        r2 = await s.generate_code(
            user_id=UID,
            strategy_description="Add a 1% trailing stop loss.",
            conversation_id=cid,
            previous_code=code,
        )
        ck(r2["conversation_id"] == cid, "Step 2: same conversation_id")
        ck(isinstance(r2["code"], str),  "Step 2: modified code returned")
        nfo(f"Step 2 code: {r2['code'][:80]}...")

        # Step 3 — list codes
        codes = s.list_generated_codes(user_id=UID, limit=5)
        ck(isinstance(codes, list), "Step 3: list_generated_codes returns list")
        nfo(f"Step 3: {len(codes)} codes found")

        # Step 4 — fetch by id
        if code_id:
            rc = s.get_generated_code(code_id=code_id, user_id=UID)
            ck(rc is not None, "Step 4: get_generated_code returns result")

        # Step 5 — conversation history
        h = s.get_conversation_history(cid, UID)
        ck(isinstance(h, list) and len(h) >= 2, "Step 5: history has messages")

        nfo("End-to-end complete")

    except Exception as e:
        fl(f"raised: {e}")
        global F; F += 1


# ===========================================================================
# MAIN RUNNER
# ===========================================================================

async def main():
    print(f"\n{B}{'='*60}\n  ForexGPT -- CodeGen Service Test Suite\n{'='*60}{X}")

    # Unit tests (no API / no DB)
    test_build_initial()
    test_build_debug()
    test_build_modify()
    test_parse_python_block()
    test_parse_generic_block()
    test_parse_no_block()

    # Integration tests (needs .env + running Supabase)
    cid, code, code_id = await test_generate_initial()
    await test_generate_debug(cid, code)
    await test_generate_modify(cid, code)
    await test_generate_bad_conv()
    test_list_codes()
    test_get_code(code_id)
    test_get_code_wrong_user(code_id)
    test_conversation_history(cid)
    await test_end_to_end()

    total  = P + F
    colour = G if F == 0 else R
    status = "ALL PASSED" if F == 0 else f"{F} FAILED"
    print(f"\n{B}{'='*60}\n  RESULTS: {P}/{total} passed  {colour}{status}{X}\n{B}{'='*60}{X}\n")


if __name__ == "__main__":
    asyncio.run(main())
