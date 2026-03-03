"""
TEST FILE: mentor_service.py
HOW TO RUN: python test_mentor_service.py  (from project root)
NEEDS: .env with MISTRAL_API_KEY, MISTRAL_MODEL_ID, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

TESTS:
    1.  ask_question              -- new conversation, real Mistral API
    2.  ask_question              -- follow-up using conversation_id
    3.  ask_question              -- bad conversation_id starts fresh
    4.  list_user_conversations   -- reads from Supabase
    5.  get_conversation_history  -- reads from Supabase
    6.  get_conversation_history  -- wrong user returns None or []
    7.  delete_conversation       -- archives in Supabase
    8.  delete_conversation       -- non-existent returns False
    9.  _generate_response        -- direct Mistral call
    10. Full end-to-end           -- ask, follow-up, list, history, delete
"""
import asyncio, os, sys
from dotenv import load_dotenv
load_dotenv()

G="\033[92m"; R="\033[91m"; Y="\033[93m"; C="\033[96m"; X="\033[0m"; B="\033[1m"
def ok(m):   print(f"  {G}PASS{X}  {m}")
def fl(m):   print(f"  {R}FAIL{X}  {m}")
def nfo(m):  print(f"  {Y}INFO{X}  {m}")
def sec(t):  print(f"\n{B}{C}{'='*60}{X}\n{B}{C}  {t}{X}\n{C}{'='*60}{X}")
P=0; F=0

def ck(cond, label, d=""):
    global P, F
    if cond: ok(label); P += 1
    else: fl(f"{label}  |  {d}"); F += 1

UID   = "00000000-0000-0000-0000-000000000001"
WUID  = "00000000-0000-0000-0000-000000000002"

def build():
    from mistralai import Mistral
    from services.mentor_service import MentorService
    key = os.getenv("MISTRAL_API_KEY")
    if not key: print(f"{R}ERROR: MISTRAL_API_KEY missing{X}"); sys.exit(1)
    return MentorService(
        mistral_client=Mistral(api_key=key),
        model_id=os.getenv("MISTRAL_MODEL_ID", "mistral-small-latest")
    )

async def t_new():
    sec("TEST 1 -- ask_question: new conversation")
    s = build(); nfo("Calling Mistral API...")
    try:
        r = await s.ask_question(user_id=UID, message="What is the Sharpe ratio? One sentence only.")
        ck("response"        in r, "response field present")
        ck("conversation_id" in r, "conversation_id field present")
        ck("message_count"   in r, "message_count field present")
        ck(isinstance(r["response"], str) and len(r["response"]) > 5, "response non-empty string")
        ck(r["message_count"] == 2, "message_count is 2")
        nfo(f"conversation_id: {r['conversation_id']}")
        nfo(f"response: {r['response'][:120]}...")
        return r["conversation_id"]
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1; return None

async def t_followup(cid):
    sec("TEST 2 -- ask_question: follow-up message")
    if not cid: nfo("Skipping -- no conv_id from TEST 1"); return
    s = build(); nfo(f"Continuing: {cid}")
    try:
        r = await s.ask_question(user_id=UID, message="Give me a one-line Python formula for it.", conversation_id=cid)
        ck(r["conversation_id"] == cid, "same conversation_id returned")
        ck(r["message_count"] >= 4, "message_count >= 4 (history loaded)")
        nfo(f"message_count: {r['message_count']}")
        nfo(f"response: {r['response'][:120]}...")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

async def t_bad_cid():
    sec("TEST 3 -- ask_question: bad conversation_id starts fresh")
    s = build(); fake = "00000000-dead-beef-0000-000000000000"
    nfo(f"Passing fake conv_id: {fake}")
    try:
        r = await s.ask_question(user_id=UID, message="What is a pip in forex?", conversation_id=fake)
        ck("conversation_id" in r, "new conversation_id generated")
        ck(r["message_count"] == 2, "fresh conversation -- count is 2")
        nfo(f"New conv_id: {r['conversation_id']}")
        s.delete_conversation(r["conversation_id"], UID)
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

def t_list():
    sec("TEST 4 -- list_user_conversations: reads from Supabase")
    s = build()
    try:
        cs = s.list_user_conversations(user_id=UID, limit=10)
        ck(isinstance(cs, list), "returns a list")
        nfo(f"Found {len(cs)} conversations")
        if cs:
            ck("conversation_id" in cs[0], "conversation_id key present")
            ck("started_at"      in cs[0], "started_at key present")
            ck("message_count"   in cs[0], "message_count key present")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

def t_history(cid):
    sec("TEST 5 -- get_conversation_history: reads from Supabase")
    if not cid: nfo("Skipping -- no conv_id"); return
    s = build()
    try:
        h = s.get_conversation_history(conversation_id=cid, user_id=UID)
        ck(h is not None, "history is not None")
        ck(isinstance(h, list), "history is a list")
        ck(len(h) >= 2, "at least 2 messages")
        if h: ck("role" in h[0] and "content" in h[0], "role and content keys present")
        nfo(f"History has {len(h)} messages")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

def t_wrong_user(cid):
    sec("TEST 6 -- get_conversation_history: wrong user returns None or []")
    if not cid: nfo("Skipping -- no conv_id"); return
    s = build()
    try:
        h = s.get_conversation_history(conversation_id=cid, user_id=WUID)
        ck(h is None or h == [], "wrong user gets None or [] -- correct")
        nfo(f"Result: {h}")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

def t_delete(cid):
    sec("TEST 7 -- delete_conversation: archives in Supabase")
    if not cid: nfo("Skipping -- no conv_id"); return
    s = build()
    try:
        r = s.delete_conversation(conversation_id=cid, user_id=UID)
        ck(r is True, "delete returns True")
        ck(cid in s._archived_conversations, "conv_id in archived set")
        nfo(f"Archived: {cid}")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

def t_delete_missing():
    sec("TEST 8 -- delete_conversation: non-existent returns False")
    s = build()
    try:
        r = s.delete_conversation("00000000-dead-0000-0000-000000000000", UID)
        ck(r is False, "returns False for non-existent conversation")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

async def t_generate_direct():
    sec("TEST 9 -- _generate_response: direct Mistral call")
    s = build(); nfo("Calling Mistral directly...")
    try:
        r = await s._generate_response([
            {"role": "system", "content": "You are a forex expert. Be very concise."},
            {"role": "user",   "content": "What does pip stand for in forex? One sentence only."}
        ])
        ck(isinstance(r, str) and len(r) > 5, "returns non-empty string")
        nfo(f"Response: {r[:150]}")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

async def t_end_to_end():
    sec("TEST 10 -- Full end-to-end: ask, follow-up, list, history, delete")
    s = build(); nfo("Running full lifecycle...")
    try:
        r1 = await s.ask_question(user_id=UID, message="What is leverage in forex? Be brief.")
        cid = r1["conversation_id"]
        ck(bool(cid), "Step 1: conversation created")
        nfo(f"Step 1: {r1['response'][:80]}...")

        r2 = await s.ask_question(user_id=UID, message="What is the max leverage in the EU?", conversation_id=cid)
        ck(r2["conversation_id"] == cid, "Step 2: same conversation_id")
        ck(r2["message_count"] >= 4, "Step 2: message_count >= 4")
        nfo(f"Step 2: {r2['response'][:80]}...")

        cs = s.list_user_conversations(user_id=UID)
        ck(isinstance(cs, list), "Step 3: list returns list")
        nfo(f"Step 3: {len(cs)} conversations")

        h = s.get_conversation_history(cid, UID)
        ck(len(h) >= 4, "Step 4: history has >= 4 messages")

        d = s.delete_conversation(cid, UID)
        ck(d is True, "Step 5: delete returns True")
        nfo("End-to-end complete")
    except Exception as e:
        fl(f"raised: {e}"); global F; F += 1

async def main():
    print(f"\n{B}{'='*60}\n  ForexGPT -- Mentor Service Test Suite\n{'='*60}{X}")
    cid = await t_new()
    await t_followup(cid)
    await t_bad_cid()
    t_list()
    t_history(cid)
    t_wrong_user(cid)
    t_delete(cid)
    t_delete_missing()
    await t_generate_direct()
    await t_end_to_end()
    tot = P + F; col = G if F == 0 else R; st = "ALL PASSED" if F == 0 else f"{F} FAILED"
    print(f"\n{B}{'='*60}\n  RESULTS: {P}/{tot} passed  {col}{st}{X}\n{B}{'='*60}{X}\n")

if __name__ == "__main__":
    asyncio.run(main())
