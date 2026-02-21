import logging
from core.hf_client import hf_client
from core.database import get_supabase

logger = logging.getLogger(__name__)

MENTOR_SYSTEM_PROMPT = """You are ForexGPT Mentor, an expert forex trading educator.
Your role is to explain forex concepts clearly and step-by-step to students.
Always structure your answers with:
1. A direct answer to the question
2. A step-by-step explanation
3. A practical example
4. A key takeaway

Be educational, clear, and encouraging. Never give financial advice."""

CODEGEN_SYSTEM_PROMPT = """You are a professional Python developer specialising in forex trading systems.
When given a trading strategy description, generate clean, well-documented Python code.
Always include:
- Clear function names and docstrings
- Input validation
- Error handling with try/except
- Inline comments explaining the logic
- A usage example at the bottom

Output only valid Python code. No explanations outside the code."""


async def ask_mentor(question: str, context: str | None, user_id: str | None) -> dict:
    user_message = question
    if context:
        user_message = f"Previous context:\n{context}\n\nNew question:\n{question}"

    try:
        answer = await hf_client.call_base_model(MENTOR_SYSTEM_PROMPT, user_message)
        logger.info("Mentor response generated.")
    except Exception as e:
        logger.error(f"Mentor HF call failed: {e}")
        answer = "I'm sorry, I couldn't process your question right now. Please try again."

    conversation_id = None
    if user_id:
        try:
            db = get_supabase()
            record = db.table("conversations").insert({
                "user_id": user_id,
                "question": question,
                "answer": answer,
            }).execute()
            conversation_id = record.data[0]["id"]
        except Exception as e:
            logger.warning(f"Could not save conversation to DB: {e}")

    return {"answer": answer, "conversation_id": conversation_id}


async def generate_code(strategy_description: str, user_id: str | None) -> dict:
    try:
        code = await hf_client.call_base_model(CODEGEN_SYSTEM_PROMPT, strategy_description)
        logger.info("Code generation response received.")
    except Exception as e:
        logger.error(f"Code gen HF call failed: {e}")
        code = "# Code generation temporarily unavailable. Please try again."

    return {"code": code, "language": "python"}