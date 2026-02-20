import random


def determine_signal(prompt: str):
    prompt = prompt.lower()

    if any(word in prompt for word in ["bullish", "buy", "long", "uptrend"]):
        return "BUY"

    if any(word in prompt for word in ["bearish", "sell", "short", "downtrend"]):
        return "SELL"

    return random.choice(["BUY", "SELL"])


def generate_confidence():
    return round(random.uniform(0.65, 0.95), 2)


def generate_signal(request):
    """
    Generates a structured forex trading signal
    based on keyword-driven sentiment analysis.
    """
    signal = determine_signal(request.prompt)
    confidence = generate_confidence()

    return {
        "pair": request.pair,
        "timeframe": request.timeframe,
        "signal": signal,
        "confidence": confidence,
        "reasoning": "Signal generated using keyword-based sentiment logic."
    }