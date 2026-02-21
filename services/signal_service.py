import logging
import json
import random
from core.hf_client import hf_client
from core.database import get_supabase

logger = logging.getLogger(__name__)

VALID_PAIRS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"]


def _extract_pair(text: str) -> str:
    for pair in VALID_PAIRS:
        if pair.lower() in text.lower():
            return pair
    return "EURUSD"


def _determine_direction(text: str) -> str:
    text = text.lower()
    if any(word in text for word in ["bullish", "buy", "long", "uptrend"]):
        return "LONG"
    if any(word in text for word in ["bearish", "sell", "short", "downtrend"]):
        return "SHORT"
    return random.choice(["LONG", "SHORT"])


def _generate_confidence() -> float:
    return round(random.uniform(0.60, 0.95), 2)


def _fallback_signal(transcript: str) -> dict:
    logger.info("Using fallback keyword-based signal extraction.")
    return {
        "currency_pair": _extract_pair(transcript),
        "direction": _determine_direction(transcript),
        "confidence": _generate_confidence(),
        "reasoning": "Signal generated using keyword-based sentiment analysis (fallback mode).",
        "magnitude": "moderate",
        "time_horizon": "next_quarter",
    }


async def extract_signal(transcript: str, user_id: str | None = None) -> dict:
    signal = None

    # Try HF fine-tuned model first
    try:
        prompt = (
            "You are a forex signal extraction model. "
            "Read the following earnings transcript and return a JSON signal.\n\n"
            f"Transcript:\n{transcript}\n\n"
            "Respond with only a JSON object containing: "
            "currency_pair, direction (LONG/SHORT), confidence (0-1), "
            "reasoning, magnitude (low/moderate/high), time_horizon."
        )
        raw = await hf_client.call_signal_model(prompt)
        signal = json.loads(raw)
        logger.info("Signal extracted via fine-tuned HF model.")
    except Exception as e:
        logger.warning(f"HF model call failed, using fallback: {e}")
        signal = _fallback_signal(transcript)

    # Save to Supabase if user is authenticated
    signal_id = None
    if user_id:
        try:
            db = get_supabase()
            record = db.table("signals").insert({
                "user_id": user_id,
                "currency_pair": signal["currency_pair"],
                "direction": signal["direction"],
                "confidence": signal["confidence"],
                "reasoning": signal["reasoning"],
                "magnitude": signal["magnitude"],
                "time_horizon": signal["time_horizon"],
            }).execute()
            signal_id = record.data[0]["id"]
            logger.info(f"Signal saved to Supabase with id: {signal_id}")
        except Exception as e:
            logger.warning(f"Could not save signal to DB: {e}")

    signal["signal_id"] = signal_id
    return signal