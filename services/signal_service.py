import random
import re

VALID_PAIRS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"]
VALID_TIMEFRAMES = ["1M", "5M", "15M", "1H", "4H", "1D"]

def extract_pair(prompt: str):
    for pair in VALID_PAIRS:
        if pair.lower() in prompt.lower():
            return pair
    return "EURUSD"

def extract_timeframe(prompt: str):
    for tf in VALID_TIMEFRAMES:
        if tf.lower() in prompt.lower():
            return tf
    return "1H"

def determine_signal(prompt: str):
    prompt = prompt.lower()
    
    if any(word in prompt for word in ["bullish", "buy", "long"]):
        return "BUY"
    if any(word in prompt for word in ["bearish", "sell", "short"]):
        return "SELL"
    
    return random.choice(["BUY", "SELL"])

def generate_confidence():
    return round(random.uniform(0.6, 0.95), 2)

def generate_signal(prompt: str):
    pair = extract_pair(prompt)
    timeframe = extract_timeframe(prompt)
    signal = determine_signal(prompt)
    confidence = generate_confidence()

    reasoning = f"Signal generated based on detected sentiment and keywords in prompt."

    return {
        "pair": pair,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": confidence,
        "reasoning": reasoning
    }